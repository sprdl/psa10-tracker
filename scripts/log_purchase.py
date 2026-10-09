#!/usr/bin/env python3
"""
Record (or remove) a purchase in data/holdings.json from a GitHub issue.

Runs inside GitHub Actions (.github/workflows/purchases.yml) when you submit the
site's "Bought it" or "Remove" form, so nothing runs on your Mac:

    python3 scripts/log_purchase.py "$GITHUB_EVENT_PATH"

- Label `bought`: parses the issue form (URL, price, date, condition, grading
  fee, notes), adds a holding with id "p<issue#>" (re-submitting an edited
  issue replaces that same holding), commits, pushes, redeploys the site, then
  comments and closes the issue.
- Label `remove-purchase`: removes the holding with the given id, same steps. Ids starting with
  "s" remove a sealed product (with its pulls), "u" one pull.
- Label `sealed`: a box / set / pack(s) bought at MSRP (store, Pokémon Center, lottery) → store["sealed"],
  id "s<issue#>". Sealed product is never bought on the second market, so there's no market price.
- Label `pull`: a valuable card pulled from one of those → that product's "pulls", id "u<issue#>".
- Label `sold`: a single ("p…") or a sealed product ("s…", with no pulls; optionally only some of its quantity) was
  sold: it leaves "holdings"/"sealed" and a record "x<issue#>" goes into store["sold"] with what it cost, what it
  sold for, the fees (typed, or estimated with the site's cost model) and the dates. Removing an "x…" id undoes the sale.
- Label `grading-info`: sets when a raw card (a pull "u…" or a raw purchase "p…") was sent to PSA, the PSA
  service tier and the owner's own chance of a PSA10; a pull's status can be changed too. Blank fields remove the value.
  Several ids at once ("p73, p74, u52", the site's PSA submission planner) get the same date, service and status;
  there a blank chance keeps each card's own.
- Label `sealed-link`: sets (or replaces) the SNKRDUNK link of an existing sealed product.
  A sealed product's name and picture come from its SNKRDUNK page, like a single's. This Action never
  opens SNKRDUNK (no automated access): the next price check reads the page in the user's browser
  (scripts/sealed_info.py, FULL-CHECK step 8h) and fills them in.
- If the form can't be read (e.g. a price of "abc"), it comments what's wrong
  and leaves the issue open. Editing the issue re-runs this.

Test locally without touching git or GitHub:

    python3 scripts/log_purchase.py event.json --dry-run
"""

import json
import os
import re
import subprocess
import sys
import time
import unicodedata
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOLDINGS = ROOT / "data" / "holdings.json"
JST = timezone(timedelta(hours=9))
URL_RE = re.compile(r"https?://(?:www\.)?snkrdunk\.com/(?:en/)?apparels/(\d+)")
DEFAULT_GRADING_FEE = 9980      # PSA Japan Standard, per card, tax incl.
DEFAULT_SHIPPING_FEES = 2450    # insurance & shipping ¥1,900 + handling fee ¥550 (total with grading ¥12,430)


class FormError(Exception):
    pass


# ---------- parsing ----------

def parse_form(body):
    """GitHub issue forms render as '### Label\\n\\nvalue' blocks."""
    fields, cur = {}, None
    for line in (body or "").splitlines():
        m = re.match(r"^###\s+(.*)$", line)
        if m:
            cur = m.group(1).strip().lower()
            fields[cur] = []
        elif cur is not None:
            fields[cur].append(line)
    out = {}
    for k, v in fields.items():
        val = "\n".join(v).strip()
        out[k] = "" if val == "_No response_" else val
    return out


def field(form, *prefixes):
    for k, v in form.items():
        if any(k.startswith(p) for p in prefixes):
            return v
    return ""


def parse_yen(s, label, required=True):
    t = unicodedata.normalize("NFKC", s or "").strip().lower()
    t = t.replace("¥", "").replace("円", "").replace(",", "").replace(" ", "").replace("jpy", "")
    if not t:
        if required:
            raise FormError(f"{label} is empty.")
        return None
    mult = 1
    if t.endswith("k"):
        mult, t = 1000, t[:-1]
    elif t.endswith("万"):
        mult, t = 10000, t[:-1]
    try:
        v = round(float(t) * mult)
    except ValueError:
        raise FormError(f"{label} \"{s}\" isn't a number. Use something like 65000 or ¥65,000.")
    if v <= 0 or v > 50_000_000:
        raise FormError(f"{label} {v:,} looks wrong.")
    return v


def parse_date(s):
    t = unicodedata.normalize("NFKC", s or "").strip().replace("/", "-").replace(".", "-")
    today = datetime.now(JST).date()
    if not t:
        return today.isoformat()
    try:
        d = datetime.strptime(t, "%Y-%m-%d").date()
    except ValueError:
        raise FormError(f"Date \"{s}\" isn't in YYYY-MM-DD form (e.g. {today.isoformat()}).")
    if d > today + timedelta(days=1):
        raise FormError(f"Date {d} is in the future.")
    return d.isoformat()


def latest_cards():
    try:
        m = json.loads((ROOT / "data" / "manifest.json").read_text(encoding="utf-8"))
        snaps = sorted([s for s in m.get("snapshots", []) if s.get("collected_at_jst")], key=lambda s: s["collected_at_jst"])
        d = json.loads((ROOT / "data" / "snapshots" / snaps[-1]["file"]).read_text(encoding="utf-8"))
        return d.get("cards", [])
    except Exception:
        return []


def build_holding(issue):
    form = parse_form(issue.get("body"))
    m = URL_RE.search(field(form, "snkrdunk url", "card url", "url"))
    if not m:
        raise FormError("No SNKRDUNK product URL found (it should look like https://snkrdunk.com/apparels/123456).")
    url = f"https://snkrdunk.com/apparels/{m.group(1)}"
    card = next((c for c in latest_cards() if c.get("url", "").rstrip("/") == url), None)
    title_name = re.sub(r"\s*\(raw[^)]*\)\s*$", "", re.sub(r"^\s*bought:?\s*", "", issue.get("title") or "", flags=re.I)).strip()
    h = {
        "id": f"p{issue['number']}",
        "card_url": url,
        "card_name_ja": (card or {}).get("card_name_ja") or title_name or url,
        # the dropdown can't always be prefilled, so the site also marks a raw purchase in the title
        "condition": "raw_to_grade" if ("raw" in field(form, "condition").lower() or "(raw" in (issue.get("title") or "").lower()) else "psa10",
        "purchase_price_jpy": parse_yen(field(form, "price"), "Price paid"),
        "purchase_date": parse_date(field(form, "date")),
    }
    if card and card.get("image_url"):
        h["image_url"] = card["image_url"]
    if h["condition"] == "raw_to_grade":
        fee = parse_yen(field(form, "grading fee"), "Grading fee", required=False)
        h["grading_fee_jpy"] = fee if fee is not None else DEFAULT_GRADING_FEE
        h["shipping_insurance_jpy"] = DEFAULT_SHIPPING_FEES
    notes = field(form, "notes")
    if notes:
        h["notes"] = notes[:300]
    return h, card is not None


def sname(item):
    return item.get("name") or item.get("snkrdunk_name") or item.get("id", "sealed product")


SEALED_KINDS = (("single pack", "pack"), ("pack", "pack"), ("box", "box"), ("set", "set"), ("deck", "set"))
PULL_STATUS = (("sending", "grading"), ("psa10", "psa10"), ("came back psa 10", "psa10"), ("lower", "graded_other"), ("raw", "raw"))


def parse_qty(s):
    t = unicodedata.normalize("NFKC", s or "").strip()
    if not t:
        return 1
    if not t.isdigit() or not 1 <= int(t) <= 999:
        raise FormError(f"Quantity \"{s}\" should be a whole number like 1 or 10.")
    return int(t)


def build_sealed(issue, dry=False):
    form = parse_form(issue.get("body"))
    name = field(form, "product").strip()
    u = URL_RE.search(field(form, "snkrdunk") or "")
    if not name and not u:
        raise FormError("Paste the product's SNKRDUNK link (or at least type its name).")
    kind_txt = field(form, "type").lower()
    kind = next((k for key, k in SEALED_KINDS if key in kind_txt), "other")
    set_code = unicodedata.normalize("NFKC", field(form, "set code")).strip()
    item = {"id": f"s{issue['number']}", "kind": kind, "name": name[:120],
            **({"url": f"https://snkrdunk.com/apparels/{u.group(1)}"} if u else {}), "qty": parse_qty(field(form, "quantity")),
            "price_jpy": parse_yen(field(form, "price paid"), "Price paid"), "date": parse_date(field(form, "date")), "pulls": []}
    if set_code:
        item["set_code"] = set_code[:20]
    where, notes = field(form, "where"), field(form, "notes")
    if where:
        item["where"] = where[:80]
    if notes:
        item["notes"] = notes[:300]
    return item


def build_pull(issue, sealed):
    form = parse_form(issue.get("body"))
    m = re.search(r"\bs\d+\b", field(form, "sealed product id", "from", "sealed") or "")
    if not m:
        raise FormError("No sealed product id found (it looks like s12). Use the + Add pull link under the product on the site.")
    parent = next((x for x in sealed if x.get("id") == m.group(0)), None)
    if not parent:
        raise FormError(f"There's no sealed product with id {m.group(0)} (maybe it was removed).")
    card_txt = field(form, "card")
    u = URL_RE.search(card_txt or "")
    if not card_txt.strip():
        raise FormError("Card is empty: paste its SNKRDUNK link or type its name.")
    pull = {"id": f"u{issue['number']}"}
    if u:
        url = f"https://snkrdunk.com/apparels/{u.group(1)}"
        card = next((c for c in latest_cards() if c.get("url", "").rstrip("/") == url), None)
        pull["card_url"] = url
        pull["card_name_ja"] = (card or {}).get("card_name_ja") or re.sub(r"^\s*pull:?\s*", "", issue.get("title") or "", flags=re.I).strip() or url
        if card and card.get("image_url"):
            pull["image_url"] = card["image_url"]
    else:
        pull["card_name_ja"] = card_txt.strip()[:120]
    st = field(form, "status").lower()
    pull["status"] = next((k for key, k in PULL_STATUS if key in st), "raw")
    est = parse_yen(field(form, "value"), "Value estimate", required=False)
    if est is not None:
        pull["value_jpy"] = est
    pull["date"] = parse_date(field(form, "date"))
    notes = field(form, "notes")
    if notes:
        pull["notes"] = notes[:300]
    return parent, pull


GRADE_TIERS = (("standard", "standard"), ("priority", "priority"), ("express", "express"))


def optional_date(s):
    return parse_date(s) if (s or "").strip() else None


def apply_grading_info(issue, store):
    """One card ("u52") or several ("p73, p74, u52", from the site's PSA submission planner). With several ids an
    empty chance keeps each card's own estimate instead of clearing it; date, service and status apply to all."""
    form = parse_form(issue.get("body"))
    ids = list(dict.fromkeys(re.findall(r"\b[pu]\d+\b", field(form, "card id", "id") or "")))
    if not ids:
        raise FormError("No card id found (it looks like u52 or p63). Use the Grading info link next to the card on the site.")
    items = []
    for gid in ids:
        item = next((h for h in store.get("holdings", []) if h.get("id") == gid), None)
        if gid.startswith("u"):
            item = next((p for x in store.get("sealed", []) for p in x.get("pulls", []) if p.get("id") == gid), None)
        if not item:
            raise FormError(f"There's no card with id {gid} (maybe it was removed).")
        items.append((gid, item))
    multi = len(items) > 1
    sent = optional_date(field(form, "date sent", "sent"))
    tier = next((k for key, k in GRADE_TIERS if key in field(form, "psa service", "service").lower()), None)
    chance_txt = field(form, "your chance", "chance").replace("%", "").strip()
    chance = None
    if chance_txt:
        try:
            chance = float(chance_txt.replace(",", "."))
        except ValueError:
            raise FormError(f"Chance of a PSA10 \"{chance_txt}\" isn't a number between 1 and 100.")
        if not 1 <= chance <= 100:
            raise FormError("Chance of a PSA10 must be between 1 and 100 (%).")
    st = field(form, "status").lower()
    for gid, item in items:
        for key, val in (("sent", sent), ("tier", tier), ("gem_rate_pct", int(chance) if chance is not None and chance.is_integer() else chance)):
            if key == "gem_rate_pct" and val is None and multi:
                continue   # several cards: an empty chance keeps each card's own
            if val is None:
                item.pop(key, None)
            else:
                item[key] = val
        if gid.startswith("u") and st and "keep as is" not in st:
            item["status"] = next((k for key, k in PULL_STATUS if key in st), item.get("status", "raw"))
    bits = [x for x in (f"sent {sent}" if sent else "", f"{tier} service" if tier else "", f"your PSA10 chance {int(chance) if chance.is_integer() else chance}%" if chance is not None else "") if x]
    if multi:
        names = ", ".join(f"**{gid}** ({item.get('card_name_ja', gid)})" for gid, item in items)
        return (f"Saved grading info for {len(items)} cards: {names}: {', '.join(bits) if bits else 'date and service cleared'}. The site updates in about a minute.",
                f"holdings: grading info for {', '.join(ids)} (#{issue['number']})")
    gid, item = items[0]
    name = item.get("card_name_ja", gid)
    return (f"Saved grading info for **{gid}** ({name}): {', '.join(bits) if bits else 'nothing set (cleared)'}. The site updates in about a minute.",
            f"holdings: grading info for {gid} (#{issue['number']})")


SELL_FEE, SELL_SHIP = 0.095, 1000   # same cost model as sellNet() in assets/app.js


def estimate_fees(price):
    return round(price * SELL_FEE + (300 if price >= 30000 else 200) + SELL_SHIP)


def apply_sold(issue, store):
    form = parse_form(issue.get("body"))
    m = re.search(r"\b[ps]\d+\b", field(form, "item id", "id") or "")
    if not m:
        raise FormError("No item id found (it looks like p63 or s46). Use the Sold it link next to the item on the site.")
    iid = m.group(0)
    price = parse_yen(field(form, "sold for", "price"), "Sold for")
    sold_date = parse_date(field(form, "date sold", "date"))
    fees_in = parse_yen(field(form, "fees"), "Fees", required=False)
    notes = field(form, "notes")
    sold = store.setdefault("sold", [])
    rec = {"id": f"x{issue['number']}", "sold_price_jpy": price, "sold_date": sold_date}
    if iid.startswith("p"):
        hs = store.setdefault("holdings", [])
        h = next((x for x in hs if x.get("id") == iid), None)
        if not h:
            raise FormError(f"There's no card with id {iid} (maybe it was already sold or removed).")
        cost = h.get("purchase_price_jpy", 0) + (h.get("grading_fee_jpy", 0) + h.get("shipping_insurance_jpy", 0) if h.get("condition") == "raw_to_grade" else 0)
        rec.update({"kind": "single", "item_id": iid, "name": h.get("card_name_ja", iid), "card_url": h.get("card_url"), "image_url": h.get("image_url"),
                    "condition": h.get("condition"), "cost_jpy": cost, "bought": h.get("purchase_date"), "orig": h})
        store["holdings"] = [x for x in hs if x.get("id") != iid]
        label = rec["name"]
    else:
        items = store.setdefault("sealed", [])
        sd = next((x for x in items if x.get("id") == iid), None)
        if not sd:
            raise FormError(f"There's no sealed product with id {iid} (maybe it was already sold or removed).")
        if sd.get("pulls"):
            raise FormError(f"{iid} has pulls logged, so it counts as opened. Only unopened sealed products can be recorded as sold.")
        n = sd.get("qty", 1) or 1
        q_txt = field(form, "quantity").strip()
        q = n
        if q_txt:
            try:
                q = int(float(q_txt))
            except ValueError:
                raise FormError(f"Quantity \"{q_txt}\" isn't a whole number.")
            if not 1 <= q <= n:
                raise FormError(f"Quantity must be between 1 and {n} (what you hold).")
        cost = round(sd.get("price_jpy", 0) * q / n)
        name = sd.get("name") or sd.get("snkrdunk_name") or sd.get("id")
        orig = {k: v for k, v in sd.items() if k != "pulls"}
        rec.update({"kind": "sealed", "item_id": iid, "name": name, "url": sd.get("url"), "image": sd.get("image"), "qty": q,
                    "cost_jpy": cost, "bought": sd.get("date"), "orig": {**orig, "qty": q, "price_jpy": cost}})
        if q == n:
            store["sealed"] = [x for x in items if x.get("id") != iid]
        else:
            sd["qty"] = n - q
            sd["price_jpy"] = sd.get("price_jpy", 0) - cost
        label = f"{q} × {name}" if q > 1 else name
    rec["fees_jpy"] = fees_in if fees_in is not None else estimate_fees(price)
    rec["fees_estimated"] = fees_in is None
    if notes:
        rec["notes"] = notes[:300]
    sold.append(rec)
    profit = price - rec["fees_jpy"] - rec["cost_jpy"]
    return (f"Recorded the sale of **{label}**: ¥{price:,} on {sold_date}, fees & shipping ¥{rec['fees_jpy']:,}{' (estimated)' if rec['fees_estimated'] else ''}, "
            f"cost ¥{rec['cost_jpy']:,}, profit **{'+' if profit >= 0 else '−'}¥{abs(profit):,}**. It moved from Holdings to Sold; the site updates in about a minute.",
            f"holdings: sold {label} (#{issue['number']})")


def undo_sold(xid, store):
    sold = store.setdefault("sold", [])
    rec = next((x for x in sold if x.get("id") == xid), None)
    if not rec:
        raise FormError(f"There's no sale with id {xid} (maybe it was already undone).")
    orig = rec.get("orig") or {}
    if rec.get("kind") == "single":
        store.setdefault("holdings", []).append(orig)
    else:
        items = store.setdefault("sealed", [])
        cur = next((x for x in items if x.get("id") == orig.get("id")), None)
        if cur:
            cur["qty"] = (cur.get("qty", 1) or 1) + (orig.get("qty", 1) or 1)
            cur["price_jpy"] = cur.get("price_jpy", 0) + orig.get("price_jpy", 0)
        else:
            items.append({**orig, "pulls": []})
    store["sold"] = [x for x in sold if x.get("id") != xid]
    return (f"Undid the sale **{xid}** ({rec.get('name')}): it is back in your holdings. The site updates in about a minute.",
            f"holdings: undo sale {xid} (#{{n}})")


def removal_id(issue):
    form = parse_form(issue.get("body"))
    m = re.search(r"\b[psux]\d+\b", field(form, "purchase id", "id") or "")
    if not m:
        raise FormError("No purchase id found (it looks like p12, s12, u12 or x12). Use the Remove link next to it on the site.")
    return m.group(0)


# ---------- side effects ----------

def load_holdings():
    return json.loads(HOLDINGS.read_text(encoding="utf-8")) if HOLDINGS.exists() else {"holdings": []}


def save_holdings(store):
    HOLDINGS.write_text(json.dumps(store, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def git(*args):
    subprocess.run(["git", *args], cwd=ROOT, check=True)


def commit_and_push(message):
    git("config", "user.name", "github-actions[bot]")
    git("config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")
    git("add", "data/holdings.json")
    if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=ROOT).returncode == 0:
        return False
    git("commit", "-q", "-m", message)
    for _ in range(3):  # a price check may have pushed in the meantime
        if subprocess.run(["git", "push", "-q", "origin", "HEAD:main"], cwd=ROOT).returncode == 0:
            return True
        git("pull", "-q", "--rebase", "origin", "main")
    raise RuntimeError("git push failed three times")


def gh(method, path, body=None):
    repo, token = os.environ["GITHUB_REPOSITORY"], os.environ["GH_TOKEN"]
    req = urllib.request.Request(f"https://api.github.com/repos/{repo}{path}", method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                                          "Content-Type": "application/json", "User-Agent": "psa10-tracker"})
    with urllib.request.urlopen(req, timeout=20) as r:
        raw = r.read()
        return json.loads(raw) if raw else {}


def finish(issue, msg, ok, dry):
    print(msg)
    if dry:
        return
    n = issue["number"]
    gh("POST", f"/issues/{n}/comments", {"body": msg})
    if ok:
        gh("PATCH", f"/issues/{n}", {"state": "closed", "state_reason": "completed"})


def apply(issue, labels, store, dry=False):
    """Apply this issue's change to `store` (fresh from disk). Returns (comment, commit message)."""
    hs = store.setdefault("holdings", [])
    sealed = store.setdefault("sealed", [])
    if "grading-info" in labels:
        return apply_grading_info(issue, store)
    if "sold" in labels:
        return apply_sold(issue, store)
    if "sealed-link" in labels:
        form = parse_form(issue.get("body"))
        m = re.search(r"\bs\d+\b", field(form, "sealed product id", "id") or "")
        u = URL_RE.search(field(form, "snkrdunk") or "")
        if not m:
            raise FormError("No sealed product id found (it looks like s12). Use the SNKRDUNK link button on the site.")
        if not u:
            raise FormError("No SNKRDUNK product link found (it looks like https://snkrdunk.com/apparels/881421).")
        item = next((x for x in sealed if x.get("id") == m.group(0)), None)
        if not item:
            raise FormError(f"There's no sealed product with id {m.group(0)}.")
        item["url"] = f"https://snkrdunk.com/apparels/{u.group(1)}"
        for k in ("image", "snkrdunk_name"):
            item.pop(k, None)   # the next price check reads them from the new page
        return (f"Linked **{item['id']}** ({sname(item)}) to {item['url']}. Its name and picture come with the next price check.",
                f"holdings: SNKRDUNK link for sealed {item['id']} (#{issue['number']})")
    if "sealed" in labels:
        item = build_sealed(issue, dry)
        old = next((x for x in sealed if x.get("id") == item["id"]), None)
        if old:
            item["pulls"] = old.get("pulls", [])   # an edited form keeps the pulls already logged
            if item.get("url") == old.get("url"):   # same SNKRDUNK page: keep what the price check read
                for k in ("image", "snkrdunk_name"):
                    if old.get(k):
                        item[k] = old[k]
        store["sealed"] = [x for x in sealed if x.get("id") != item["id"]] + [item]
        kinds = {"box": "box", "set": "set", "pack": "pack", "other": "item"}
        label = item["name"] or f"the SNKRDUNK product {item['url'].rsplit('/', 1)[-1]}"
        return (f"{'Updated' if old else 'Logged'} sealed product **{item['id']}**: {item['qty']} × {label} ({kinds[item['kind']]}), "
                f"¥{item['price_jpy']:,} on {item['date']}. Add the good pulls with **+ Add pull** under it on the Holdings page. The site updates in about a minute."
                +(" Its name and picture come from SNKRDUNK with the next price check." if item.get("url") else ""),
                f"holdings: {'update' if old else 'add'} sealed {label} (#{issue['number']})")
    if "pull" in labels:
        parent, pull = build_pull(issue, sealed)
        for x in sealed:   # an edited form replaces the same pull, wherever it was
            x["pulls"] = [p for p in x.get("pulls", []) if p.get("id") != pull["id"]]
        parent.setdefault("pulls", []).append(pull)
        return (f"Logged pull **{pull['id']}**: {pull['card_name_ja']} from {sname(parent)} ({parent['id']}). The site updates in about a minute."
                + ("" if pull.get("card_url") or pull.get("value_jpy") else "\n\nTip: paste the card's SNKRDUNK link (or a value estimate) so the site can value it."),
                f"holdings: pull {pull['card_name_ja']} from {parent['id']} (#{issue['number']})")
    if "remove-purchase" in labels:
        pid = removal_id(issue)
        if pid.startswith("x"):
            msg, commit = undo_sold(pid, store)
            return msg, commit.replace("{n}", str(issue["number"]))
        if pid.startswith("s"):
            gone = [x for x in sealed if x.get("id") == pid]
            if not gone:
                raise FormError(f"There's no sealed product with id {pid} (maybe it was already removed).")
            store["sealed"] = [x for x in sealed if x.get("id") != pid]
            n = len(gone[0].get("pulls", []))
            return (f"Removed sealed product **{pid}** ({sname(gone[0])}){f' and its {n} pull(s)' if n else ''}. The site updates in about a minute.",
                    f"holdings: remove sealed {pid} {sname(gone[0])} (#{issue['number']})")
        if pid.startswith("u"):
            for x in sealed:
                hit = [p for p in x.get("pulls", []) if p.get("id") == pid]
                if hit:
                    x["pulls"] = [p for p in x["pulls"] if p.get("id") != pid]
                    return (f"Removed pull **{pid}** ({hit[0].get('card_name_ja')}) from {sname(x)}. The site updates in about a minute.",
                            f"holdings: remove pull {pid} (#{issue['number']})")
            raise FormError(f"There's no pull with id {pid} (maybe it was already removed).")
        gone = [h for h in hs if h.get("id") == pid]
        if not gone:
            raise FormError(f"There's no purchase with id {pid} (maybe it was already removed).")
        store["holdings"] = [h for h in hs if h.get("id") != pid]
        name = gone[0].get("card_name_ja", pid)
        return (f"Removed purchase **{pid}** ({name}, ¥{gone[0].get('purchase_price_jpy', 0):,} on {gone[0].get('purchase_date')}). The site updates in about a minute.",
                f"holdings: remove {pid} {name} (#{issue['number']})")
    h, tracked = build_holding(issue)
    replaced = any(x.get("id") == h["id"] for x in hs)
    store["holdings"] = [x for x in hs if x.get("id") != h["id"]] + [h]
    cost = h["purchase_price_jpy"] + (h.get("grading_fee_jpy", 0) + h.get("shipping_insurance_jpy", 0))
    msg = (f"{'Updated' if replaced else 'Logged'} purchase **{h['id']}**: {h['card_name_ja']}, "
           f"¥{h['purchase_price_jpy']:,} on {h['purchase_date']}"
           + (f" + ¥{h['grading_fee_jpy'] + h['shipping_insurance_jpy']:,} grading & shipping (total ¥{cost:,})" if h["condition"] == "raw_to_grade" else " (PSA10 slab)")
           + ". The site updates in about a minute."
           + ("" if tracked else "\n\nNote: this card isn't on the tracker, so it shows without a current price or P&L."))
    return msg, f"holdings: {'update' if replaced else 'add'} {h['card_name_ja']} (#{issue['number']})"


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry = "--dry-run" in sys.argv
    if not args:
        sys.exit(__doc__)
    event = json.loads(Path(args[0]).read_text(encoding="utf-8"))
    issue = event["issue"]
    from issue_labels import labels_of
    labels = labels_of(issue)  # infers the label from the title if GitHub dropped it
    if not labels & {"bought", "remove-purchase", "sealed", "pull", "sealed-link", "grading-info", "sold"}:
        print("Not a purchase issue; nothing to do.")
        return

    try:
        store = load_holdings()
        msg, commit_msg = apply(issue, labels, store, dry)
    except FormError as e:
        finish(issue, f"Couldn't record this: {e}\n\nEdit the issue to fix it and it will be retried automatically.", False, dry)
        return  # not a failed run: the comment on the issue says what to fix

    if dry:
        print(json.dumps(store, ensure_ascii=False, indent=2))
        print(msg)
        return

    git("config", "user.name", "github-actions[bot]")
    git("config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")
    # Several forms submitted at once run in parallel (and a price check may push too).
    # Each attempt starts from the latest main and re-applies this one change, so they never conflict.
    changed = False
    for attempt in range(6):
        git("fetch", "-q", "origin", "main")
        git("reset", "-q", "--hard", "origin/main")
        store = load_holdings()
        try:
            msg, commit_msg = apply(issue, labels, store, dry)
        except FormError as e:  # e.g. a removal that another run already did
            finish(issue, f"Couldn't record this: {e}", False, dry)
            return
        save_holdings(store)
        git("add", "data/holdings.json")
        if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=ROOT).returncode == 0:
            break  # already recorded (e.g. a re-run)
        git("commit", "-q", "-m", commit_msg)
        if subprocess.run(["git", "push", "-q", "origin", "HEAD:main"], cwd=ROOT).returncode == 0:
            changed = True
            break
        time.sleep(3 + attempt * 2)
    else:
        raise RuntimeError("git push failed six times")
    if changed:
        # Pushes made with the Actions token don't start other workflows, so start the Pages deploy explicitly.
        gh("POST", "/actions/workflows/deploy.yml/dispatches", {"ref": "main"})
    finish(issue, msg, True, dry)


if __name__ == "__main__":
    main()

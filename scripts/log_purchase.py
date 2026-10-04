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
- Label `sealed-photo`: sets (or replaces) the picture of an existing sealed product.
  A picture (dragged into the form, or an image link) is downloaded and committed as
  assets/sealed/<id>.<ext>, so the site never depends on the original link.
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
    title_name = re.sub(r"^\s*bought:?\s*", "", issue.get("title") or "", flags=re.I).strip()
    h = {
        "id": f"p{issue['number']}",
        "card_url": url,
        "card_name_ja": (card or {}).get("card_name_ja") or title_name or url,
        "condition": "raw_to_grade" if "raw" in field(form, "condition").lower() else "psa10",
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


IMG_MAX = 8 * 1024 * 1024
IMG_TYPES = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "image/gif": "gif", "image/heic": "heic"}
PENDING = {}    # repo-relative path -> bytes, written and committed with holdings.json
_IMG_CACHE = {}


def image_url(text):
    t = text or ""
    for rx in (r"!\[[^\]]*\]\((https?://[^)\s]+)\)", r"<img[^>]+src=\"(https?://[^\"]+)\"", r"(https?://\S+)"):
        m = re.search(rx, t)
        if m:
            return m.group(1)
    return None


def shrink(data, ext):
    """Phone photos are several MB: keep at most 900 px on the long side as JPEG (needs Pillow, which
    the workflow installs; without it the original is kept)."""
    try:
        import io
        from PIL import Image, ImageOps
        im = ImageOps.exif_transpose(Image.open(io.BytesIO(data)))
        if max(im.size) <= 900 and len(data) <= 400_000:
            return data, ext
        im.thumbnail((900, 900))
        out = io.BytesIO()
        im.convert("RGB").save(out, "JPEG", quality=85, optimize=True)
        return out.getvalue(), "jpg"
    except Exception:  # noqa: BLE001  (no Pillow, or a format it can't read)
        return data, ext


def fetch_image(url):
    """Download an image (GitHub upload or any public link). Returns (bytes, ext); raises FormError."""
    if url in _IMG_CACHE:
        return _IMG_CACHE[url]
    last = None
    for auth in (False, True):   # public links need no token; GitHub uploads sometimes do
        hdr = {"User-Agent": "psa10-tracker", "Accept": "image/*"}
        if auth:
            if not os.environ.get("GH_TOKEN") or "github" not in url:
                break
            hdr["Authorization"] = f"Bearer {os.environ['GH_TOKEN']}"
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=hdr), timeout=30) as r:
                ctype = (r.headers.get("Content-Type") or "").split(";")[0].strip().lower()
                data = r.read(IMG_MAX + 1)
            if len(data) > IMG_MAX:
                raise FormError("The picture is over 8 MB; use a smaller one.")
            ext = IMG_TYPES.get(ctype)
            if not ext:
                last = f"the link isn't an image ({ctype or 'unknown type'})"
                continue
            data, ext = shrink(data, ext)
            _IMG_CACHE[url] = (data, ext)
            return data, ext
        except FormError:
            raise
        except Exception as e:  # noqa: BLE001
            last = str(e)
    raise FormError(f"Couldn't download the picture: {last}. Drag the photo into the form, or paste a direct image link.")


def attach_image(item, text, dry):
    url = image_url(text)
    if not url:
        return False
    if dry:
        item["image"] = f"assets/sealed/{item['id']}.jpg"
        return True
    data, ext = fetch_image(url)
    path = f"assets/sealed/{item['id']}.{ext}"
    for old in list(PENDING):
        if old.startswith(f"assets/sealed/{item['id']}."):
            del PENDING[old]
    PENDING[path] = data
    item["image"] = path
    return True


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
    if not name:
        raise FormError("Product name is empty.")
    kind_txt = field(form, "type").lower()
    kind = next((k for key, k in SEALED_KINDS if key in kind_txt), "other")
    set_code = unicodedata.normalize("NFKC", field(form, "set code")).strip()
    item = {"id": f"s{issue['number']}", "kind": kind, "name": name[:120], "qty": parse_qty(field(form, "quantity")),
            "price_jpy": parse_yen(field(form, "price paid"), "Price paid"), "date": parse_date(field(form, "date")), "pulls": []}
    if set_code:
        item["set_code"] = set_code[:20]
    where, notes = field(form, "where"), field(form, "notes")
    attach_image(item, field(form, "picture"), dry)
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


def removal_id(issue):
    form = parse_form(issue.get("body"))
    m = re.search(r"\b[psu]\d+\b", field(form, "purchase id", "id") or "")
    if not m:
        raise FormError("No purchase id found (it looks like p12, s12 or u12). Use the Remove link next to it on the site.")
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
    if "sealed-photo" in labels:
        form = parse_form(issue.get("body"))
        m = re.search(r"\bs\d+\b", field(form, "sealed product id", "id") or "")
        if not m:
            raise FormError("No sealed product id found (it looks like s12). Use the Add picture link on the site.")
        item = next((x for x in sealed if x.get("id") == m.group(0)), None)
        if not item:
            raise FormError(f"There's no sealed product with id {m.group(0)}.")
        if not attach_image(item, field(form, "picture"), dry):
            raise FormError("No picture found: drag a photo into the Picture box, or paste an image link.")
        return (f"Picture added to **{item['id']}** ({item['name']}). The site updates in about a minute.",
                f"holdings: picture for sealed {item['id']} (#{issue['number']})")
    if "sealed" in labels:
        item = build_sealed(issue, dry)
        old = next((x for x in sealed if x.get("id") == item["id"]), None)
        if old:
            item["pulls"] = old.get("pulls", [])   # an edited form keeps the pulls already logged
            if "image" not in item and old.get("image"):
                item["image"] = old["image"]
        store["sealed"] = [x for x in sealed if x.get("id") != item["id"]] + [item]
        kinds = {"box": "box", "set": "set", "pack": "pack", "other": "item"}
        return (f"{'Updated' if old else 'Logged'} sealed product **{item['id']}**: {item['qty']} × {item['name']} ({kinds[item['kind']]}), "
                f"¥{item['price_jpy']:,} on {item['date']}. Add the good pulls with **+ Add pull** under it on the Holdings page. The site updates in about a minute.",
                f"holdings: {'update' if old else 'add'} sealed {item['name']} (#{issue['number']})")
    if "pull" in labels:
        parent, pull = build_pull(issue, sealed)
        for x in sealed:   # an edited form replaces the same pull, wherever it was
            x["pulls"] = [p for p in x.get("pulls", []) if p.get("id") != pull["id"]]
        parent.setdefault("pulls", []).append(pull)
        return (f"Logged pull **{pull['id']}**: {pull['card_name_ja']} from {parent['name']} ({parent['id']}). The site updates in about a minute."
                + ("" if pull.get("card_url") or pull.get("value_jpy") else "\n\nTip: paste the card's SNKRDUNK link (or a value estimate) so the site can value it."),
                f"holdings: pull {pull['card_name_ja']} from {parent['id']} (#{issue['number']})")
    if "remove-purchase" in labels:
        pid = removal_id(issue)
        if pid.startswith("s"):
            gone = [x for x in sealed if x.get("id") == pid]
            if not gone:
                raise FormError(f"There's no sealed product with id {pid} (maybe it was already removed).")
            store["sealed"] = [x for x in sealed if x.get("id") != pid]
            n = len(gone[0].get("pulls", []))
            return (f"Removed sealed product **{pid}** ({gone[0]['name']}){f' and its {n} pull(s)' if n else ''}. The site updates in about a minute.",
                    f"holdings: remove sealed {pid} {gone[0]['name']} (#{issue['number']})")
        if pid.startswith("u"):
            for x in sealed:
                hit = [p for p in x.get("pulls", []) if p.get("id") == pid]
                if hit:
                    x["pulls"] = [p for p in x["pulls"] if p.get("id") != pid]
                    return (f"Removed pull **{pid}** ({hit[0].get('card_name_ja')}) from {x['name']}. The site updates in about a minute.",
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
    labels = {l["name"] for l in issue.get("labels", [])}
    if not labels & {"bought", "remove-purchase", "sealed", "pull", "sealed-photo"}:
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
        for path, data in PENDING.items():   # pictures of sealed products
            f = ROOT / path
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(data)
            git("add", path)
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

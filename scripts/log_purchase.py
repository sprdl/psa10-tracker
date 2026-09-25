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
- Label `remove-purchase`: removes the holding with the given id, same steps.
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
import unicodedata
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOLDINGS = ROOT / "data" / "holdings.json"
JST = timezone(timedelta(hours=9))
URL_RE = re.compile(r"https?://(?:www\.)?snkrdunk\.com/(?:en/)?apparels/(\d+)")
DEFAULT_GRADING_FEE = 9980


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
        h["shipping_insurance_jpy"] = 2000
    notes = field(form, "notes")
    if notes:
        h["notes"] = notes[:300]
    return h, card is not None


def removal_id(issue):
    form = parse_form(issue.get("body"))
    m = re.search(r"\bp\d+\b", field(form, "purchase id", "id") or "")
    if not m:
        raise FormError("No purchase id found (it looks like p12). Use the Remove link next to the purchase on the site.")
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


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry = "--dry-run" in sys.argv
    if not args:
        sys.exit(__doc__)
    event = json.loads(Path(args[0]).read_text(encoding="utf-8"))
    issue = event["issue"]
    labels = {l["name"] for l in issue.get("labels", [])}
    store = load_holdings()
    hs = store.setdefault("holdings", [])

    try:
        if "remove-purchase" in labels:
            pid = removal_id(issue)
            gone = [h for h in hs if h.get("id") == pid]
            if not gone:
                raise FormError(f"There's no purchase with id {pid} (maybe it was already removed).")
            store["holdings"] = [h for h in hs if h.get("id") != pid]
            name = gone[0].get("card_name_ja", pid)
            commit_msg = f"holdings: remove {pid} {name} (#{issue['number']})"
            msg = f"Removed purchase **{pid}** ({name}, ¥{gone[0].get('purchase_price_jpy', 0):,} on {gone[0].get('purchase_date')}). The site updates in about a minute."
        elif "bought" in labels:
            h, tracked = build_holding(issue)
            replaced = any(x.get("id") == h["id"] for x in hs)
            store["holdings"] = [x for x in hs if x.get("id") != h["id"]] + [h]
            cost = h["purchase_price_jpy"] + (h.get("grading_fee_jpy", 0) + h.get("shipping_insurance_jpy", 0))
            commit_msg = f"holdings: {'update' if replaced else 'add'} {h['card_name_ja']} (#{issue['number']})"
            msg = (f"{'Updated' if replaced else 'Logged'} purchase **{h['id']}**: {h['card_name_ja']}, "
                   f"¥{h['purchase_price_jpy']:,} on {h['purchase_date']}"
                   + (f" + ¥{h['grading_fee_jpy'] + h['shipping_insurance_jpy']:,} grading & shipping (total ¥{cost:,})" if h["condition"] == "raw_to_grade" else " (PSA10 slab)")
                   + ". The site updates in about a minute."
                   + ("" if tracked else "\n\nNote: this card isn't on the tracker, so it shows without a current price or P&L."))
        else:
            print("Not a purchase issue; nothing to do.")
            return
    except FormError as e:
        finish(issue, f"Couldn't record this: {e}\n\nEdit the issue to fix it and it will be retried automatically.", False, dry)
        return  # not a failed run: the comment on the issue says what to fix

    if dry:
        print(json.dumps(store, ensure_ascii=False, indent=2))
        print(msg)
        return
    save_holdings(store)
    commit_and_push(commit_msg)
    # Pushes made with the Actions token don't start other workflows, so start the Pages deploy explicitly.
    gh("POST", "/actions/workflows/deploy.yml/dispatches", {"ref": "main"})
    finish(issue, msg, True, dry)


if __name__ == "__main__":
    main()

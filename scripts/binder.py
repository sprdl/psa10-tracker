#!/usr/bin/env python3
"""
The Binder: raw cards from the physical binder, priced as A-rank raw copies once a week (Mondays, JST).

    python3 scripts/binder.py due                 # the SNKRDUNK ids the full check reads today (empty unless Monday)
    python3 scripts/binder.py missing             # binder cards that still have no SNKRDUNK id (FULL-CHECK step 2c)
    python3 scripts/binder.py set-id <card id> <snkrdunk id> [--image URL]
    python3 scripts/binder.py status              # one line per card: price, previous price, change

data/binder.json (written by this script and by full_update.py, shown on the site's Binder page):
  {"about": "...", "updated": "2026-10-19T…", "cards": [{
      "id": "sv2a-168", "name_ja": "…", "name_en": "…", "set": "sv2a", "number": "168", "total": "165",
      "rarity": "AR" | null, "qty": 1, "condition": "A", "snkrdunk_id": "123456" | null, "image_url": "…" | null,
      "price": 1800, "date": "2026-10-19", "basis": "sales" | "ask", "ask": 1700, "sales": [1800, …],
      "prev_price": 1700, "prev_date": "2026-10-12"}]}
`price` is per copy; the site multiplies by qty. `prev_price` is the reading before the latest one, so the
Binder page can show ▲/▼ without a history file. A card whose page has no for-sale listing, or a read that
failed, keeps its last price and date (one bad read doesn't blank the page).

Price rule (decided 2026-10-08, scripts/raw_price.py): the median of the last 5 one-copy A-rank sales from the
past 30 days, never below the lowest A-rank ask; fewer than 3 such sales: the lowest ask. A card can carry
"condition": "psa10" or another note later, but today every binder card is read as A-rank raw.

How the reading happens: on Mondays, plan.py adds the binder's SNKRDUNK ids to HELD (the same in-page
script and the same H lines as bought-but-untracked cards, FULL-CHECK step 2b), and full_update.py hands the
H lines to save(). On other days nothing is read: due() is empty. Binder cards are owned (raw), so they have no
limit, no Buy signal and no sell tiers.
"""
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

JST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parent.parent
PATH = ROOT / "data" / "binder.json"


def load(root=ROOT):
    p = root / "data" / "binder.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"cards": []}


def write(data, root=ROOT):
    p = root / "data" / "binder.json"
    p.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return p


def due_ids(root=ROOT, now=None):
    """SNKRDUNK ids to read today: Mondays (JST) only, cards with an id that weren't read today yet."""
    now = now or datetime.now(JST)
    if now.weekday() != 0:
        return []
    today = now.strftime("%Y-%m-%d")
    out = []
    for c in load(root).get("cards", []):
        sid = c.get("snkrdunk_id")
        if sid and c.get("date") != today and sid not in out:
            out.append(str(sid))
    return out


def missing_ids(root=ROOT):
    return [c for c in load(root).get("cards", []) if not c.get("snkrdunk_id")]


def label(c):
    return f"{c.get('name_en') or c.get('name_ja') or '?'} ({c.get('set')} {c.get('number')}/{c.get('total')})"


def save(found, root=ROOT, push=True, now=None):
    """Apply today's H lines (decoded by holdings_prices.decode: {snkrdunk id: {price, ask, sales, …} | {error}}).
    push=True commits and pushes, push="commit" only commits (full_update.py pushes once at the end), False writes only."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from raw_price import raw_price
    now = now or datetime.now(JST)
    today = now.strftime("%Y-%m-%d")
    data = load(root)
    cards = data.get("cards", [])
    ids = {str(c["snkrdunk_id"]) for c in cards if c.get("snkrdunk_id")}
    if not ids & set(found):
        return None
    read = kept = 0
    notes = []
    for c in cards:
        sid = str(c.get("snkrdunk_id") or "")
        e = found.get(sid)
        if not sid or e is None:
            continue
        if "error" in e:
            kept += 1
            notes.append(f"{label(c)}: {e['error']}; kept the {c.get('date')} price")
            continue
        price, basis = raw_price(e.get("ask"), e.get("sales") or [])
        if price is None:
            kept += 1
            notes.append(f"{label(c)}: no for-sale A-rank listing and no recent sales; kept the {c.get('date')} price")
            continue
        if c.get("date") != today:     # a second reading the same day replaces today's, it isn't a new "previous"
            c["prev_price"], c["prev_date"] = c.get("price"), c.get("date")
        c.update(price=price, date=today, basis=basis, ask=e.get("ask"), sales=e.get("sales") or [])
        if e.get("image_url"):
            c["image_url"] = e["image_url"]
        read += 1
    data["updated"] = now.replace(microsecond=0).isoformat()
    path = write(data, root)
    total, prev = worth(cards)
    print(f"binder: {read} priced, {kept} kept from before, {len(missing_ids(root))} without an id"
          + (f"; worth now ¥{total:,}" + (f" ({(total - prev) / prev * 100:+.1f}% vs the last reading)" if prev else "") if total else ""))
    for n in notes:
        print(f"binder: {n}")
    if not push:
        return path
    cmds = [["git", "add", str(path)], ["git", "commit", "-q", "-m", "binder: weekly A-rank raw prices"]]
    if push is True:
        cmds.append(["git", "push", "-q"])
    for cmd in cmds:
        r = subprocess.run(cmd, cwd=root, text=True, capture_output=True)
        if r.returncode != 0 and "nothing to commit" not in (r.stdout + r.stderr):
            print(f"binder: {' '.join(cmd)} failed: {(r.stderr or r.stdout).strip()}")
            return path
    print("binder: pushed." if push is True else "binder: committed (pushed with the snapshot).")
    return path


def worth(cards):
    """(worth now, worth at the previous reading) over the cards that have both prices."""
    now = prev = 0
    for c in cards:
        if c.get("price") is not None and c.get("prev_price") is not None:
            now += c["price"] * (c.get("qty") or 1)
            prev += c["prev_price"] * (c.get("qty") or 1)
    total = sum(c["price"] * (c.get("qty") or 1) for c in cards if c.get("price") is not None)
    return total, (prev + (total - now)) if prev else 0


def print_due(root=ROOT, now=None):
    """The follow-up block full_update.py prints after a publish (and --followups)."""
    now = now or datetime.now(JST)
    miss = missing_ids(root)
    ids = due_ids(root, now)
    if miss:
        print(f"\nBINDER IDS NEEDED (FULL-CHECK step 2c, pricecheck/steps/2c-binder-ids.md): {len(miss)} binder cards have no SNKRDUNK id yet, so they are not priced:")
        for c in miss:
            print(f"  {c['id']}  {label(c)}")
    if now.weekday() == 0:
        print(f"BINDER: Monday price reading {'included in step 2b (' + str(len(ids)) + ' cards)' if ids else 'already done today or nothing to read'}.")
    else:
        print("BINDER: prices are read on Mondays only.")


def due_count(root=ROOT):
    return len(missing_ids(root))


def main():
    args = sys.argv[1:]
    cmd = args[0] if args else "status"
    if cmd == "due":
        print(json.dumps([[i, "card"] for i in due_ids()]))
    elif cmd == "missing":
        for c in missing_ids():
            print(f"{c['id']}\t{label(c)}")
    elif cmd == "set-id" and len(args) >= 3:
        data = load()
        hit = [c for c in data["cards"] if c["id"] == args[1]]
        if not hit:
            sys.exit(f"no binder card with id {args[1]}")
        hit[0]["snkrdunk_id"] = args[2]
        if "--image" in args:
            hit[0]["image_url"] = args[args.index("--image") + 1]
        write(data)
        print(f"{label(hit[0])}: SNKRDUNK id {args[2]}")
    elif cmd == "status":
        for c in load().get("cards", []):
            p, q = c.get("price"), c.get("prev_price")
            ch = f"{(p - q) / q * 100:+.1f}%" if p is not None and q else "–"
            print(f"{c['id']:<10} {label(c):<48} x{c.get('qty', 1)}  ¥{p if p is not None else '—'}  prev {q if q is not None else '—'}  {ch}")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Current SNKRDUNK prices for what's on the Holdings page but not in the tracked-card list.

    python3 scripts/holdings_prices.py --due           # [id, kind] pairs the full check reads today
    python3 scripts/holdings_prices.py - [--no-push] <<'EOF'      # H / HE lines from pricecheck/scripts/snkrdunk_held.js
    H 455596 card 31000
    H 881421 sealed 7600
    HE 896992 card page%20did%20not%20load
    EOF

What gets read (one product page each, FULL check only, never the quick check):
  card    a bought single (condition raw_to_grade) or a pull (status raw / grading) whose card is NOT
          tracked: its raw A-rank lowest ask. Tracked cards already carry raw A-rank and PSA10 prices
          in the snapshot; bought-as-PSA10 cards and PSA10 pulls are valued from PSA10 prices elsewhere.
  sealed  a sealed product (box / set / pack) with a SNKRDUNK link and NO pulls: the lowest ask of the
          product page, per unit (the site multiplies by qty). Logging a pull opens the product, so it
          drops out of this list and its stored price is deleted on the next run.

data/holdings_prices.json holds only the latest reading per product id:
  {"updated": "...", "prices": {"881421": {"kind": "sealed", "price": 7600, "date": "2026-10-07"}}}
`price` is null when the page has no for-sale listing. A failed read keeps the previous price (and its
date) so one bad run doesn't blank the Holdings page.
"""
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import unquote

JST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parent.parent
PATH = ROOT / "data" / "holdings_prices.json"
RAW_STATUS = ("raw", "grading")


def sid_of(url):
    return (url or "").rstrip("/").split("/")[-1]


def needed(root=ROOT, tracked=None):
    """{snkrdunk id: kind} for everything that needs a price reading today."""
    hp = root / "data" / "holdings.json"
    data = json.loads(hp.read_text(encoding="utf-8")) if hp.exists() else {}
    if tracked is None:
        sys.path.insert(0, str(root / "pricecheck"))
        import plan
        tracked = {c["snkrdunk_id"] for c in plan.load_cards(root)}
    out = {}
    for h in data.get("holdings", []):
        sid = sid_of(h.get("card_url"))
        if sid and sid not in tracked and h.get("condition") != "psa10":
            out[sid] = "card"
    for s in data.get("sealed", []):
        pulls = s.get("pulls") or []
        for p in pulls:
            sid = sid_of(p.get("card_url"))
            if sid and sid not in tracked and p.get("status", "raw") in RAW_STATUS:
                out[sid] = "card"
        sid = sid_of(s.get("url"))
        if sid and not pulls:          # opened (any pull logged) = no longer sealed, no longer tracked
            out[sid] = "sealed"
    return out


def decode(lines):
    out = {}
    for ln in lines:
        p = ln.strip().split(" ")
        if len(p) >= 4 and p[0] == "H":
            out[p[1]] = {"kind": p[2], "price": int(p[3]) if p[3].isdigit() else None}
        elif len(p) >= 3 and p[0] == "HE":
            out[p[1]] = {"error": unquote(" ".join(p[2:]))}
    return out


def save(found, root=ROOT, push=True, dry=False):
    """Rewrite data/holdings_prices.json for today's needed ids; drop everything else."""
    path = root / "data" / "holdings_prices.json"
    old = (json.loads(path.read_text(encoding="utf-8")).get("prices") or {}) if path.exists() else {}
    today = datetime.now(JST).strftime("%Y-%m-%d")
    prices, notes = {}, []
    for sid, kind in needed(root).items():
        e = found.get(sid)
        if e and "error" not in e:
            prices[sid] = {"kind": kind, "price": e["price"], "date": today}
        elif sid in old and old[sid].get("kind") == kind:
            prices[sid] = old[sid]
            notes.append(f"{sid}: {(e or {}).get('error', 'not read this run')}; kept {old[sid].get('date')} price")
        elif e:
            notes.append(f"{sid}: {e['error']}")
    dropped = sorted(set(old) - set(prices))
    for n in notes:
        print(f"holdings prices: {n}")
    if dropped:
        print("holdings prices: no longer tracked, removed: " + ", ".join(dropped))
    if not prices and not old:
        return
    if dry:
        print(f"holdings prices: {len(prices)} (dry run, nothing written)")
        return
    out = {"updated": datetime.now(JST).replace(microsecond=0).isoformat(), "prices": prices}
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"holdings prices: {sum(1 for v in prices.values() if v['price'] is not None)}/{len(prices)} priced")
    if not push:
        return
    for cmd in (["git", "add", str(path)], ["git", "commit", "-q", "-m", "holdings: SNKRDUNK prices for bought cards and sealed items"], ["git", "push", "-q"]):
        r = subprocess.run(cmd, cwd=root, text=True, capture_output=True)
        if r.returncode != 0 and "nothing to commit" not in (r.stdout + r.stderr):
            print(f"holdings prices: {' '.join(cmd)} failed: {(r.stderr or r.stdout).strip()}")
            return
    print("holdings prices: pushed.")


def main():
    args = sys.argv[1:]
    if "--due" in args:
        print(json.dumps([[k, v] for k, v in needed().items()]))
        return
    files = [a for a in args if not a.startswith("--")]
    text = sys.stdin.read() if not files or files[0] == "-" else Path(files[0]).read_text(encoding="utf-8")
    save(decode(text.splitlines()), push="--no-push" not in args)


if __name__ == "__main__":
    main()

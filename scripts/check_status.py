#!/usr/bin/env python3
"""
Tiny status line for the price-check skill (and for you): which snapshot is live,
when the last FULL check ran, and whether one has run yet today (JST).

    python3 scripts/check_status.py
    → {"latest": "20260925-1515.json", "latest_mode": "full",
       "last_full_jst": "2026-09-25T15:15:03+09:00", "full_today": true,
       "suggested_mode": "quick"}

suggested_mode is "full" if no full check has run today (JST), or if a card has a PSA10 market but no
tiers or verdict yet (eval_due: only a full check evaluates them, FULL-CHECK step 8b); else "quick".
A second line, quick_ids = [...], lists the SNKRDUNK ids a quick check reads.
Manifest entries without a check_mode are treated as full checks.
"""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

JST = timezone(timedelta(hours=9))
root = Path(__file__).resolve().parent.parent
m = json.loads((root / "data" / "manifest.json").read_text(encoding="utf-8"))
snaps = sorted([s for s in m.get("snapshots", []) if s.get("collected_at_jst")], key=lambda s: s["collected_at_jst"])
fulls = [s for s in snaps if s.get("check_mode", "full") == "full"]
today = datetime.now(JST).strftime("%Y-%m-%d")
last_full = fulls[-1]["collected_at_jst"] if fulls else None
full_today = bool(last_full and datetime.fromisoformat(last_full).astimezone(JST).strftime("%Y-%m-%d") == today)
# Cards with a PSA10 market but no tiers need a full check (its step 8b evaluates them); a quick check can't.
eval_due = []
if snaps:
    _d = json.loads((root / "data" / "snapshots" / snaps[-1]["file"]).read_text(encoding="utf-8"))
    for c in _d.get("cards", []):
        a = c.get("analysis") or {}
        if ((c.get("grades") or {}).get("psa10") or {}).get("lowest_price") and not a.get("tiers") \
                and not (a.get("verdict") or {}).get("tag"):
            eval_due.append(c.get("url", "").rstrip("/").split("/")[-1])
print(json.dumps({
    "latest": snaps[-1]["file"] if snaps else None,
    "latest_mode": snaps[-1].get("check_mode", "full") if snaps else None,
    "last_full_jst": last_full,
    "full_today": full_today,
    "suggested_mode": "quick" if full_today and not eval_due else "full",
    "eval_due": eval_due,   # non-empty: run a full check so step 8b evaluates these
}, ensure_ascii=False))
# The cards a quick check reads (every card in the latest snapshot), as a ready-made JS array.
if snaps:
    latest = json.loads((root / "data" / "snapshots" / snaps[-1]["file"]).read_text(encoding="utf-8"))
    rp = root / "data" / "removed_cards.json"   # removed with the site's Remove card button: not read any more
    gone = set((json.loads(rp.read_text(encoding="utf-8")).get("removed") or {}).keys()) if rp.exists() else set()
    ids = [c.get("url", "").rstrip("/").split("/")[-1] for c in latest.get("cards", []) if c.get("url")]
    ids = [i for i in ids if i not in gone]
    print("quick_ids = " + json.dumps(ids))

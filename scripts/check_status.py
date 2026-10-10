#!/usr/bin/env python3
"""
Tiny status line for the price-check skill (and for you): which snapshot is live,
when the last FULL check ran, and whether one has run yet today (JST).

    python3 scripts/check_status.py
    → {"latest": "20260925-1515.json", "latest_mode": "full",
       "last_full_jst": "2026-09-25T15:15:03+09:00", "full_today": true,
       "suggested_mode": "quick"}

suggested_mode is "full" if no full check has run today (JST), else "quick". Since 2026-10-10 a quick check
also adds requested cards and evaluates new ones (scripts/eval_queue.py), so neither forces a full check.
eval_due lists the cards the run must evaluate (queued new/restored cards first, see eval_queue.py).
A second line, quick_ids = [...], lists the SNKRDUNK ids a quick check reads: every card in the latest
snapshot plus tracked cards that haven't been published yet (just added), minus removed cards.
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
import sys
sys.path.insert(0, str(root / "scripts"))
import eval_queue  # noqa: E402
eval_due = [d["url"].rstrip("/").split("/")[-1] for d in eval_queue.due(root)[0]]
print(json.dumps({
    "latest": snaps[-1]["file"] if snaps else None,
    "latest_mode": snaps[-1].get("check_mode", "full") if snaps else None,
    "last_full_jst": last_full,
    "full_today": full_today,
    "suggested_mode": "quick" if full_today else "full",
    "eval_due": eval_due,   # evaluated in this run, quick or full (FULL-CHECK 8b / quick check Q5)
}, ensure_ascii=False))
# The cards a quick check reads (every card in the latest snapshot), as a ready-made JS array.
if snaps:
    latest = json.loads((root / "data" / "snapshots" / snaps[-1]["file"]).read_text(encoding="utf-8"))
    rp = root / "data" / "removed_cards.json"   # removed with the site's Remove card button: not read any more
    gone = set((json.loads(rp.read_text(encoding="utf-8")).get("removed") or {}).keys()) if rp.exists() else set()
    ids = [c.get("url", "").rstrip("/").split("/")[-1] for c in latest.get("cards", []) if c.get("url")]
    tp = root / "data" / "tracked_cards.json"   # just added by a request, not in a snapshot yet
    for t in (json.loads(tp.read_text(encoding="utf-8")).get("cards", []) if tp.exists() else []):
        if t.get("snkrdunk_id") and t["snkrdunk_id"] not in ids:
            ids.append(t["snkrdunk_id"])
    ids = [i for i in ids if i not in gone]
    print("quick_ids = " + json.dumps(ids))

#!/usr/bin/env python3
"""
Tiny status line for the price-check skill (and for you): which snapshot is live,
when the last FULL check ran, and whether one has run yet today (JST).

    python3 scripts/check_status.py
    → {"latest": "20260925-1515.json", "latest_mode": "full",
       "last_full_jst": "2026-09-25T15:15:03+09:00", "full_today": true,
       "suggested_mode": "quick"}

suggested_mode is "full" if no full check has run today (JST), else "quick".
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
print(json.dumps({
    "latest": snaps[-1]["file"] if snaps else None,
    "latest_mode": snaps[-1].get("check_mode", "full") if snaps else None,
    "last_full_jst": last_full,
    "full_today": full_today,
    "suggested_mode": "quick" if full_today else "full",
}, ensure_ascii=False))

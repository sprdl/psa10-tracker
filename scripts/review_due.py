#!/usr/bin/env python3
"""
List tracked cards whose tiers are due for a fresh evaluation (FULL-CHECK step 8d), most due first.

    python3 scripts/review_due.py [--all]

A card is due when it has tiers and a PSA10 market and at least one of:
  - its tiers are over 30 days old (data/history.json "tiers" → since),
  - the pokeca-chart PSA10 index has moved 10%+ since they were set,
  - its Definitely-buy is a long shot: under 10% within 90 days on the limit-odds model, and the
    tiers are at least 7 days old (a fresh evaluation that keeps a long-shot line on purpose isn't
    re-flagged straight away),
  - it is under 9 months old (data/value_model.json release month) and its tiers are 14+ days old,
    because young cards keep falling against the market (age curve, 2026-10-02 backtest).
The same rules drive the site's "Review due" line (assets/app.js tierReview). Without --all it
prints at most 2 cards: the number step 8d evaluates per full check.
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JST = timezone(timedelta(hours=9))
sys.path.insert(0, str(ROOT / "scripts"))
import odds_model  # noqa: E402

MAX_AGE_DAYS, MAX_MOVE, LONGSHOT, LONGSHOT_MIN_DAYS, YOUNG_MONTHS, YOUNG_MIN_DAYS = 30, 10, 0.10, 7, 9, 14


def ts(s):
    d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    return d if d.tzinfo else d.replace(tzinfo=JST)


def main():
    m = json.loads((ROOT / "data" / "manifest.json").read_text(encoding="utf-8"))
    latest = sorted(m["snapshots"], key=lambda s: s["collected_at_jst"])[-1]["file"]
    snap = json.loads((ROOT / "data" / "snapshots" / latest).read_text(encoding="utf-8"))
    hist = json.loads((ROOT / "data" / "history.json").read_text(encoding="utf-8"))
    tiers_state = hist.get("tiers", {})
    now = ts(snap["collected_at_jst"])
    idx = ((snap.get("pokeca_chart_index") or {}).get("psa10") or {}).get("latest_index_value_jpy")
    model = odds_model.load_model(ROOT)
    vp = ROOT / "data" / "value_model.json"
    release = json.loads(vp.read_text(encoding="utf-8")).get("release", {}) if vp.exists() else {}
    due = []
    for c in snap.get("cards", []):
        a = c.get("analysis") or {}
        t = a.get("tiers")
        ask = ((c.get("grades") or {}).get("psa10") or {}).get("lowest_price")
        st = tiers_state.get(c["url"])
        if not t or not ask or not st:
            continue
        days = (now - ts(st["since"])).total_seconds() / 86400
        reasons, score = [], 0
        if days > MAX_AGE_DAYS:
            reasons.append(f"tiers {days:.0f} days old"); score += days / MAX_AGE_DAYS
        if idx and st.get("i"):
            mv = (idx / st["i"] - 1) * 100
            if abs(mv) >= MAX_MOVE:
                reasons.append(f"market {mv:+.0f}% since"); score += abs(mv) / MAX_MOVE
        o = odds_model.odds(model, c.get("card_name_ja", ""), ask, t.get("definitely_buy")) if model else None
        if o and o[1] < LONGSHOT and days >= LONGSHOT_MIN_DAYS:
            reasons.append(f"Definitely-buy ¥{t['definitely_buy']:,} is a long shot ({o[1]:.0%} in 90 days)"); score += 1
        name = c.get("card_name_ja", "")
        code = (name.split("[", 1)[1].split("]", 1)[0] if "[" in name else "").lower().strip()
        rel = release.get(code)
        if rel:
            age = (now.year * 12 + now.month) - (int(rel[:4]) * 12 + int(rel[5:7]))
            if age < YOUNG_MONTHS and days >= YOUNG_MIN_DAYS:
                reasons.append(f"young card ({age} months), tiers {days:.0f} days old"); score += 0.8
        if reasons:
            due.append((score, c["url"], name, ask, reasons))
    due.sort(key=lambda x: -x[0])
    if not due:
        print("No tiers due for review.")
        return
    shown = due if "--all" in sys.argv else due[:2]
    for _, url, name, ask, reasons in shown:
        print(f"{url}  ask ¥{ask:,}  {name}\n    due: {'; '.join(reasons)}")
    if len(due) > len(shown):
        print(f"({len(due) - len(shown)} more due; the next full checks continue with them)")


if __name__ == "__main__":
    main()

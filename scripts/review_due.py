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

    python3 scripts/review_due.py --text [--all]

Lists cards whose WRITTEN verdict no longer matches the price (FULL-CHECK step 8g): the lowest ask
has moved 5%+ from the price the verdict was written at (analysis.representative_price, else
verdict_price_ref), and the card isn't already due for a full review above (that rewrites it anyway).
Biggest move first, at most 3 per run. The refresh keeps the tiers and rewrites only the verdict.
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
TEXT_DRIFT, TEXT_PER_RUN, REVIEW_PER_RUN = 5.0, 3, 2   # % move that makes the written verdict stale


def ts(s):
    d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    return d if d.tzinfo else d.replace(tzinfo=JST)


def compute(root=ROOT):
    """(review-due list, text-due list). review: (score, url, name, ask, reasons); text: (abs drift, url, name, ask, ref, drift)."""
    m = json.loads((root / "data" / "manifest.json").read_text(encoding="utf-8"))
    latest = sorted(m["snapshots"], key=lambda s: s["collected_at_jst"])[-1]["file"]
    snap = json.loads((root / "data" / "snapshots" / latest).read_text(encoding="utf-8"))
    hist = json.loads((root / "data" / "history.json").read_text(encoding="utf-8"))
    tiers_state = hist.get("tiers", {})
    now = ts(snap["collected_at_jst"])
    idx = ((snap.get("pokeca_chart_index") or {}).get("psa10") or {}).get("latest_index_value_jpy")
    model = odds_model.load_model(root)
    vp = root / "data" / "value_model.json"
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
    review_urls = {d[1] for d in due[:REVIEW_PER_RUN]}
    text = []
    for c in snap.get("cards", []):
        a = c.get("analysis") or {}
        v = a.get("verdict") or {}
        ask = ((c.get("grades") or {}).get("psa10") or {}).get("lowest_price")
        ref = a.get("representative_price") or a.get("verdict_price_ref")
        if not v.get("reasoning") or v.get("tag") == "defer" or not ask or not ref or c["url"] in review_urls:
            continue
        drift = (ask / ref - 1) * 100
        if abs(drift) >= TEXT_DRIFT:
            text.append((abs(drift), c["url"], c.get("card_name_ja", ""), ask, ref, drift))
    text.sort(key=lambda x: -x[0])
    return due, text


def print_text_due(root=ROOT, show_all=False):
    """The REFRESH VERDICTS block printed at the end of full_update.py."""
    try:
        _, text = compute(root)
    except Exception as e:  # never break a price check over this
        print(f"\nREFRESH VERDICTS: could not work out the due cards ({e}).")
        return
    if not text:
        print("\nREFRESH VERDICTS: none (every written verdict is within 5% of today's ask).")
        return
    shown = text if show_all else text[:TEXT_PER_RUN]
    print("\nREFRESH VERDICTS NOW (FULL-CHECK step 8g) — the written verdict no longer matches the price; rewrite it (tiers stay):")
    for _, url, name, ask, ref, drift in shown:
        print(f"  {url}  ask ¥{ask:,} vs written at ¥{ref:,} ({drift:+.1f}%)  {name}")
    if len(text) > len(shown):
        print(f"  ({len(text) - len(shown)} more; the next full checks continue with them)")


def main():
    if "--text" in sys.argv:
        print_text_due(ROOT, "--all" in sys.argv)
        return
    due, _ = compute(ROOT)
    if not due:
        print("No tiers due for review.")
        return
    shown = due if "--all" in sys.argv else due[:REVIEW_PER_RUN]
    for _, url, name, ask, reasons in shown:
        print(f"{url}  ask ¥{ask:,}  {name}\n    due: {'; '.join(reasons)}")
    if len(due) > len(shown):
        print(f"({len(due) - len(shown)} more due; the next full checks continue with them)")


if __name__ == "__main__":
    main()

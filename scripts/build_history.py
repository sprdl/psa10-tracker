#!/usr/bin/env python3
"""
Rebuild data/history.json: a compact per-card price series across every snapshot.

The site's price-history charts used to download every snapshot file (≈70 KB
each) the first time a card was expanded, which grows without bound with
several checks a day. This index is what the site reads instead: one small file,
a few hundred bytes per snapshot.

    python3 scripts/build_history.py          # rebuild (add_snapshot / apply_analysis call this)

Per snapshot: {"d": collected_at_jst, "m": check_mode, "i": pokeca PSA10 index, "p": {url: [price, confirmed]},
               "h": {url: [PSA10 sales/day, raw A sales/day]}}

"h" is how fast the card trades on SNKRDUNK: the number of recent completed sales in
the snapshot (up to 20, one-copy sales) divided by the days since the oldest of them.
Timestamps are either dates ("2026/09/14", taken as noon JST) or relative ("18時間前").

Top-level "tiers": {url: {"since": review date, "i": pokeca PSA10 index then}} — when each
card's current tiers were last set or reviewed: the later of the snapshot where the
tier numbers last changed and the newest verdict prediction's "made" time (a
re-evaluation that keeps the same tiers still counts as a review). The site uses it
to flag tiers that are old or were set before a big market move.
where price follows the site's own rule (analysis.representative_price if set,
else the PSA10 lowest ask; cards with no PSA10 ask are left out) and confirmed
is 1 when price_source is sales_confirmed.
"""
import json, re
from datetime import datetime, timedelta, timezone
from pathlib import Path

JST = timezone(timedelta(hours=9))
REL = {"秒": 1 / 86400, "分": 1 / 1440, "時間": 1 / 24, "日": 1, "週間": 7, "ヶ月": 30, "か月": 30}


def sale_age_days(when, ref):
    """Days between a SNKRDUNK sale timestamp and the snapshot time (None if unreadable)."""
    w = (when or "").strip()
    if w in ("たった今", "今"):
        return 0.0
    m = re.match(r"(\d+)\s*(秒|分|時間|日|週間|ヶ月|か月)前", w)
    if m:
        return (int(m.group(1)) + 0.5) * REL[m.group(2)]  # "1日前" means 1-2 days ago: take the middle
    m = re.match(r"(\d{4})/(\d{1,2})/(\d{1,2})", w)
    if m:
        t = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), 12, tzinfo=JST)
        return max(0.0, (ref - t).total_seconds() / 86400)
    return None


def sales_per_day(sales, ref):
    ages = [a for a in (sale_age_days(s.get("when"), ref) for s in sales or []) if a is not None]
    if len(ages) < 2:
        return None
    return round(len(ages) / max(max(ages), 0.25), 2)

ROOT = Path(__file__).resolve().parent.parent


def build(root: Path = ROOT) -> Path:
    manifest = json.loads((root / "data" / "manifest.json").read_text(encoding="utf-8"))
    snaps = sorted([s for s in manifest.get("snapshots", []) if s.get("collected_at_jst")],
                   key=lambda s: s["collected_at_jst"])
    series = []
    tier_state = {}  # url -> [tiers tuple, changed_at, index_then, reviewed_at]
    for s in snaps:
        path = root / "data" / "snapshots" / s["file"]
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        points = {}
        idx = (((d.get("pokeca_chart_index") or {}).get("psa10") or {}).get("latest_index_value_jpy"))
        when = d.get("collected_at_jst", s["collected_at_jst"])
        for c in d.get("cards", []):
            an = c.get("analysis") or {}
            t = an.get("tiers")
            if t:
                key = (t.get("definitely_buy"), t.get("buy_upper"), t.get("ceiling"))
                made = max([pr.get("made", "") for pr in ((an.get("verdict") or {}).get("predictions") or [])] or [""])
                st = tier_state.get(c.get("url"))
                if not st or st[0] != key:
                    tier_state[c.get("url")] = st = [key, when, idx, when]
                if made and made > st[3]:
                    st[3] = made
            else:
                tier_state.pop(c.get("url"), None)
            psa10 = (c.get("grades") or {}).get("psa10") or {}
            if psa10.get("lowest_price") is None:
                continue
            a = c.get("analysis") or {}
            price = a.get("representative_price", psa10["lowest_price"])
            if price is None:
                continue
            points[c.get("url")] = [price, 1 if a.get("price_source") == "sales_confirmed" else 0]
        heat = {}
        try:
            ref = datetime.fromisoformat(when)
            if ref.tzinfo is None:
                ref = ref.replace(tzinfo=JST)
        except ValueError:
            ref = None
        if ref:
            for c in d.get("cards", []):
                g = c.get("grades") or {}
                a = sales_per_day((g.get("psa10") or {}).get("recent_completed_sales"), ref)
                b = sales_per_day((g.get("raw_a_grade") or {}).get("recent_completed_sales"), ref)
                if a is not None or b is not None:
                    heat[c.get("url")] = [a, b]
        entry = {"d": when, "m": s.get("check_mode", "full"), "p": points}
        if heat:
            entry["h"] = heat
        if idx:
            entry["i"] = idx
        series.append(entry)

    def index_at(ts):
        v = None
        for e in series:
            if e["d"] <= ts and e.get("i"):
                v = e["i"]
        return v

    tiers = {}
    for url, (_, changed, idx0, reviewed) in tier_state.items():
        since = max(changed, reviewed)
        tiers[url] = {"since": since, "i": index_at(since) or idx0}
    out = root / "data" / "history.json"
    out.write_text(json.dumps({"snapshots": series, "tiers": tiers}, ensure_ascii=False, separators=(",", ":")) + "\n",
                   encoding="utf-8")
    # The track record (data/calls.json) is derived from the same snapshots.
    try:
        import build_calls
        build_calls.build(root)
    except Exception as e:  # never block publishing a price check over it
        print(f"warning: couldn't rebuild data/calls.json: {e}")
    return out


if __name__ == "__main__":
    p = build()
    print(f"Rebuilt {p.relative_to(ROOT)} ({p.stat().st_size:,} bytes)")

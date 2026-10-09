#!/usr/bin/env python3
"""
Rebuild data/history.json: a compact per-card price series across every snapshot, and
data/sales.json: every PSA10 sale seen by the checks, once each.

The site's price-history charts used to download every snapshot file (≈70 KB
each) the first time a card was expanded, which grows without bound with
several checks a day. This index is what the site reads instead: one small file,
a few hundred bytes per snapshot.

    python3 scripts/build_history.py          # rebuild (add_snapshot / apply_analysis call this)

Per snapshot: {"d": collected_at_jst, "m": check_mode, "i": pokeca PSA10 index, "p": {url: [price, confirmed]},
               "h": {url: [PSA10 sales/day, raw A sales/day]},
               "r": {url: [PSA10 lowest ask, raw A lowest ask, PSA10 sales median, raw A sales median, raw A-rank price]},
               "f": {url: favorites}                          on the last check of each JST day, only when it changed,
               "q": {url: [PSA10 listings within 15%, PSA10 listings sampled (max 20)]}   only from a fresh listings read,
               "n": {url: [PSA10 population, gem rate %]}     only from a fresh population read, and only when changed}
"r" feeds the card page's SNKRDUNK slab-premium line (PSA10 ÷ raw A-rank); its 5th value, the raw A-rank price
(scripts/raw_price.py), values raw copies over time on the Holdings page. "f", "q" and "n" feed the card page's
supply-and-demand charts; a reader carries the last value of "f" and "n" forward.

Thinning: entries older than FULL_DAYS (30) days before the latest check keep only the last check of each JST
day (its "q" / "n" filled from earlier checks that day when it has none), so the file grows by about one entry
a day instead of three or four. The track record (build_calls.py) and the event study read the snapshots at
full resolution (entries()), not this file.

"h" is how fast the card trades on SNKRDUNK: the number of recent completed sales in
the snapshot (up to 20, one-copy sales) divided by the days since the oldest of them.
Timestamps are either dates ("2026/09/14", taken as noon JST) or relative ("18時間前").

Top-level "tiers": {url: {"since": review date, "i": pokeca PSA10 index then}} — when each
card's current tiers were last set or reviewed: the later of the snapshot where the
tier numbers last changed and the newest verdict prediction's "made" time (a
re-evaluation that keeps the same tiers still counts as a review). The site uses it
to flag tiers that are old or were set before a big market move.
Top-level "tier_log": {url: [[since, definitely_buy, buy_upper, ceiling], ...]} — every set of tiers a card has had,
from when it first appeared (the Holdings page compares a purchase with the tiers of its day).
where price follows the site's own rule (analysis.representative_price if set,
else the PSA10 lowest ask; cards with no PSA10 ask are left out) and confirmed
is 1 when price_source is sales_confirmed.

data/sales.json: {"updated", "cards": {url: [[hour, price], ...]}}, hour = hours since 1970-01-01 UTC (the middle of
the window the sale's SNKRDUNK timestamp allows). Each check shows the last 20 one-copy PSA10 sales, oldest first;
consecutive lists overlap, so each new list is aligned with the previous one (same prices in the same order, at
times that fit both timestamps) and only the sales after the overlap are added. The site draws them on the
card's History tab with a rolling median.
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

def sales_median(sales, ref):
    """Median one-copy sale price: the last 7 days' sales if there are 3+, else the 5 most recent."""
    rows = [(s.get("price"), sale_age_days(s.get("when"), ref)) for s in sales or [] if s.get("price")]
    recent = sorted(p for p, a in rows if a is not None and a <= 7)
    pick = recent if len(recent) >= 3 else sorted(p for p, _ in rows[-5:]) if len(rows) >= 3 else []
    if not pick:
        return None
    n = len(pick)
    return pick[n // 2] if n % 2 else int((pick[n // 2 - 1] + pick[n // 2]) / 2 + 0.5)   # JS Math.round, not banker's rounding


import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parent))
from raw_price import raw_price  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


FULL_DAYS = 30            # newer entries keep every check; older ones one per JST day
UNIT_S = {"秒": 1, "分": 60, "時間": 3600, "日": 86400, "週間": 7 * 86400, "ヶ月": 30 * 86400, "か月": 30 * 86400}


def _ts(s):
    d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    return d if d.tzinfo else d.replace(tzinfo=JST)


def _jst_day(s):
    return _ts(s).astimezone(JST).date().isoformat()


def sale_window(when, ref):
    """(earliest, latest) time a SNKRDUNK sale timestamp allows, or None. "3時間前" = 3 to 4 hours before ref."""
    w = (when or "").strip()
    if w in ("たった今", "今"):
        return ref - timedelta(minutes=1), ref
    m = re.match(r"(\d+)\s*(秒|分|時間|日|週間|ヶ月|か月)前", w)
    if m:
        n, u = int(m.group(1)), UNIT_S[m.group(2)]
        return ref - timedelta(seconds=(n + 1) * u), ref - timedelta(seconds=n * u)
    m = re.match(r"(\d{4})/(\d{1,2})/(\d{1,2})", w)
    if m:
        d0 = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=JST)
        return d0, min(ref, d0 + timedelta(days=1))
    return None


def _same_sale(a, b, slack=timedelta(hours=1)):
    """a, b = (price, window or None): same price and time windows that overlap."""
    if a[0] != b[0]:
        return False
    if a[1] is None or b[1] is None:
        return True
    return a[1][0] - slack <= b[1][1] and b[1][0] - slack <= a[1][1]


def new_sales(prev, cur):
    """The sales in cur (oldest first) that come after its overlap with prev."""
    if not prev:
        return cur
    for k in range(min(len(prev), len(cur)), 0, -1):
        if all(_same_sale(prev[len(prev) - k + i], cur[i]) for i in range(k)):
            return cur[k:]
    return cur


def _fresh_listings(g):
    lst = g.get("top20_cheapest_listings")
    return isinstance(lst, list) and lst and g.get("lowest_price") is not None and not g.get("listings_as_of")


def entries(root: Path = ROOT):
    """Full-resolution entries (one per snapshot, oldest first) plus the tier state, tier log and PSA10 sales."""
    manifest = json.loads((root / "data" / "manifest.json").read_text(encoding="utf-8"))
    snaps = sorted([s for s in manifest.get("snapshots", []) if s.get("collected_at_jst")],
                   key=lambda s: s["collected_at_jst"])
    series = []
    tier_state = {}  # url -> [tiers tuple, changed_at, index_then, reviewed_at]
    tier_log = {}    # url -> [[since, db, bu, ceil], ...]
    last_sales, sales = {}, {}   # url -> [(price, window)] of the previous check / url -> [(time, price)]
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
                    log = tier_log.setdefault(c.get("url"), [])
                    if not log or tuple(log[-1][1:]) != key:
                        log.append([when, *key])
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
        heat, prem, favs, depth, pop = {}, {}, {}, {}, {}
        try:
            ref = datetime.fromisoformat(when)
            if ref.tzinfo is None:
                ref = ref.replace(tzinfo=JST)
        except ValueError:
            ref = None
        if ref:
            for c in d.get("cards", []):
                url = c.get("url")
                g = c.get("grades") or {}
                a = sales_per_day((g.get("psa10") or {}).get("recent_completed_sales"), ref)
                b = sales_per_day((g.get("raw_a_grade") or {}).get("recent_completed_sales"), ref)
                if a is not None or b is not None:
                    heat[url] = [a, b]
                pl = (g.get("psa10") or {}).get("lowest_price")
                rl = (g.get("raw_a_grade") or {}).get("lowest_price")
                ps = sales_median((g.get("psa10") or {}).get("recent_completed_sales"), ref)
                rs = sales_median((g.get("raw_a_grade") or {}).get("recent_completed_sales"), ref)
                # 5th value: the raw A-rank price (scripts/raw_price.py), used to value raw pulls over time
                raw_sales = [x.get("price") for x in reversed((g.get("raw_a_grade") or {}).get("recent_completed_sales") or [])
                             if x.get("price") and (lambda a: a is not None and a <= 30)(sale_age_days(x.get("when"), ref))]
                rp = raw_price(rl, raw_sales)[0]
                if (pl and rl) or (ps and rs) or rp:
                    prem[url] = [pl, rl, ps, rs, rp]
                if isinstance(c.get("favorite_count"), int):
                    favs[url] = c["favorite_count"]
                g10 = g.get("psa10") or {}
                if _fresh_listings(g10):
                    depth[url] = [g10.get("count_within_15pct") or 0, len(g10["top20_cheapest_listings"])]
                if c.get("psa10_population") is not None and not c.get("population_as_of"):
                    pop[url] = [c["psa10_population"], c.get("psa10_gem_rate_pct")]
                cur = [(x.get("price"), sale_window(x.get("when"), ref)) for x in g10.get("recent_completed_sales") or [] if x.get("price")]
                if cur:
                    for price, win in new_sales(last_sales.get(url), cur):
                        if win:
                            mid = win[0] + (win[1] - win[0]) / 2
                            sales.setdefault(url, []).append((min(mid, ref), price))
                    last_sales[url] = cur
        entry = {"d": when, "m": s.get("check_mode", "full"), "p": points}
        for k, v in (("h", heat), ("r", prem), ("f", favs), ("q", depth), ("n", pop)):
            if v:
                entry[k] = v
        if idx:
            entry["i"] = idx
        series.append(entry)
    return series, tier_state, tier_log, sales


def thin(series, keep_days=FULL_DAYS):
    """Keep every entry from the last keep_days; before that, the last check of each JST day."""
    if not series:
        return series
    cutoff = _ts(series[-1]["d"]) - timedelta(days=keep_days)
    out, pending = [], {}   # pending: "q" / "n" of dropped checks of the same day
    for i, e in enumerate(series):
        nxt = series[i + 1] if i + 1 < len(series) else None
        if _ts(e["d"]) < cutoff and nxt and _jst_day(nxt["d"]) == _jst_day(e["d"]):
            for k in ("q", "n"):
                pending.setdefault(k, {}).update(e.get(k) or {})
            continue
        if pending:
            e = dict(e)
            for k, v in pending.items():
                merged = {**v, **(e.get(k) or {})}
                if merged:
                    e[k] = merged
            pending = {}
        out.append(e)
    return out


def daily_only(series, key="f"):
    """Keep `key` only on the last entry of each JST day (filled from earlier checks that day)."""
    out, day_vals = [], {}
    for i, e in enumerate(series):
        day = _jst_day(e["d"])
        day_vals.update(e.get(key) or {})
        e = {k: v for k, v in e.items() if k != key}
        nxt = series[i + 1] if i + 1 < len(series) else None
        if not nxt or _jst_day(nxt["d"]) != day:
            if day_vals:
                e[key] = day_vals
            day_vals = {}
        out.append(e)
    return out


def changes_only(series, keys=("f", "n")):
    """Drop a card's value from an entry when it equals the last value stored for it."""
    last = {k: {} for k in keys}
    out = []
    for e in series:
        e = dict(e)
        for k in keys:
            if k not in e:
                continue
            keep = {u: v for u, v in e[k].items() if last[k].get(u) != v}
            last[k].update(e[k])
            if keep:
                e[k] = keep
            else:
                del e[k]
        out.append(e)
    return out


def build(root: Path = ROOT) -> Path:
    series, tier_state, tier_log, sales = entries(root)

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
    out.write_text(json.dumps({"snapshots": changes_only(daily_only(thin(series))), "tiers": tiers, "tier_log": tier_log},
                              ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    sales_out = {url: [[int(t.timestamp() // 3600), p] for t, p in sorted(v)] for url, v in sales.items()}
    (root / "data" / "sales.json").write_text(json.dumps({
        "about": "Every PSA10 one-copy sale the price checks saw on SNKRDUNK, once each (scripts/build_history.py): "
                 "[hour, price], hour = hours since 1970-01-01 UTC, the middle of the window the sale's timestamp allows.",
        "updated": series[-1]["d"] if series else None, "cards": sales_out},
        ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    # "You vs the model" (data/predict.json): make this week's questions, resolve open ones.
    try:
        import predict
        made, resolved, _ = predict.update(root)
        if made or resolved:
            print(f"predict: {'new questions for this week' if made else ''}{' · ' if made and resolved else ''}{f'{resolved} resolved' if resolved else ''}")
    except Exception as e:  # never block publishing a price check over it
        print(f"warning: couldn't update data/predict.json: {e}")
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

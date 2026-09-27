#!/usr/bin/env python3
"""
Which tracked cards stand out right now, and why — the cards a full check writes an analysis for.

    python3 scripts/outliers.py            # top candidates (score >= 1), at most 3
    python3 scripts/outliers.py --all      # every card with any finding

Same findings and thresholds as the site's "What stands out" panel (insightsFor in assets/app.js):
  vs. market   the card's price change minus the My-tier index change (pokeca PSA10 index before
               the My-tier series exists) over 7 days (>= 8 pts) or 30 days (>= 12 pts)
  ask vs sales lowest ask vs the median of the last week's one-copy sales (>= 8%)
  big move     price change since the previous check (>= 8%)
  trading      PSA10 sales per day vs a week ago (>= 50%, when either is >= 1/day)
  near limit   lowest ask within 5% above your limit
Score = size / threshold (weighted like the site), so 1.0 = just at the threshold.
Each printed line carries the numbers the analysis needs; the full check reads it, looks at the
card's data, and saves a short analysis with scripts/set_insight.py.
"""
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

JST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parent.parent
T = {"gap7": 8, "gap30": 12, "move": 8, "askVsSales": 8, "heat": 50}
REL = {"秒": 1 / 86400, "分": 1 / 1440, "時間": 1 / 24, "日": 1, "週間": 7, "ヶ月": 30, "か月": 30}


def load(p, default=None):
    p = ROOT / p
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


def ts(s):
    return datetime.fromisoformat(s)


def sale_age(when, ref):
    w = str(when or "").strip()
    if w in ("たった今", "今"):
        return 0
    m = re.match(r"^(\d+)\s*(秒|分|時間|日|週間|ヶ月|か月)前", w)
    if m:
        return (int(m[1]) + 0.5) * REL[m[2]]
    m = re.match(r"^(\d{4})/(\d{1,2})/(\d{1,2})", w)
    if m:
        d = datetime(int(m[1]), int(m[2]), int(m[3]), 12, tzinfo=JST)
        return max(0.0, (ref - d).total_seconds() / 86400)
    return None


def median(a):
    s = sorted(a)
    n = len(s)
    return None if not n else (s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2)


def main():
    show_all = "--all" in sys.argv
    man = load("data/manifest.json")
    snaps = sorted([s for s in man["snapshots"] if s.get("collected_at_jst")], key=lambda s: s["collected_at_jst"])
    cur = load("data/snapshots/" + snaps[-1]["file"])
    prev = load("data/snapshots/" + snaps[-2]["file"]) if len(snaps) > 1 else None
    hist = load("data/history.json", {"snapshots": []})["snapshots"]
    ci = (load("data/custom_index.json", {}) or {}).get("series", [])
    limits = (load("data/limits.json", {}) or {}).get("limits", {})
    now_s = cur["collected_at_jst"]
    now = ts(now_s)

    def price_at(url, t):
        v = None
        for e in hist:
            if e["d"] <= t and e.get("p", {}).get(url):
                v = (e["d"], e["p"][url][0])
        return v

    def market_move(frm, to):
        a = b = None
        for e in ci:
            if e["d"] <= frm[:10]:
                a = e
            if e["d"] <= to[:10]:
                b = e
        if a and b:
            return (b["level"] / a["level"] - 1) * 100, "My-tier index"
        pa = pb = None
        for e in hist:
            if e["d"] <= frm and e.get("i"):
                pa = e["i"]
            if e["d"] <= to and e.get("i"):
                pb = e["i"]
        return ((pb / pa - 1) * 100, "PSA10 index") if pa and pb else (None, None)

    def gap(url, days):
        c = price_at(url, now_s)
        p = price_at(url, (now - timedelta(days=days)).isoformat())
        if not c or not p or not p[1]:
            return None
        m, name = market_move(p[0], now_s)
        if m is None:
            return None
        cp = (c[1] / p[1] - 1) * 100
        return {"card": cp, "market": m, "gap": cp - m, "name": name, "old": p[1], "now": c[1]}

    def heat(url, days_ago):
        cut = (now - timedelta(days=days_ago)).isoformat()
        v = None
        for e in hist:
            if e["d"] <= cut and e.get("h", {}).get(url) and e["h"][url][0] is not None:
                v = e["h"][url][0]
        return v

    prev_by = {c["url"]: c for c in (prev or {}).get("cards", [])}
    rows = []
    for c in cur["cards"]:
        g = (c.get("grades") or {}).get("psa10") or {}
        ask = g.get("lowest_price")
        if ask is None:
            continue
        url = c["url"]
        sid = url.rstrip("/").split("/")[-1]
        name = re.sub(r"\s*\[.*$", "", c["card_name_ja"]).strip()
        f = []
        g7, g30 = gap(url, 7), gap(url, 30)
        pick = None
        if g30 and abs(g30["gap"]) >= T["gap30"] and (not g7 or abs(g30["gap"]) / T["gap30"] > abs(g7["gap"]) / T["gap7"]):
            pick = (g30, 30)
        elif g7 and abs(g7["gap"]) >= T["gap7"]:
            pick = (g7, 7)
        if pick:
            x, d = pick
            f.append((abs(x["gap"]) / T["gap7" if d == 7 else "gap30"],
                      f"{d}d price {x['card']:+.1f}% (¥{x['old']:,}→¥{x['now']:,}) vs {x['name']} {x['market']:+.1f}% = {x['gap']:+.1f} pts"))
        sales = [(s["price"], sale_age(s["when"], now)) for s in g.get("recent_completed_sales") or []]
        sales = [(p, a) for p, a in sales if a is not None]
        recent = [p for p, a in sales if a <= 7]
        before = [p for p, a in sales if a > 7]
        ref = median(recent) if len(recent) >= 3 else (median([p for p, _ in sales[-5:]]) if len(sales) >= 5 else None)
        if ref:
            dv = (ask / ref - 1) * 100
            if abs(dv) >= T["askVsSales"]:
                f.append((abs(dv) / T["askVsSales"] * 0.9, f"lowest ask ¥{ask:,} is {dv:+.0f}% vs recent sales median ¥{ref:,.0f}"))
        if len(recent) >= 3 and len(before) >= 3:
            f_sales = f"sales median last 7d ¥{median(recent):,.0f} ({len(recent)}) vs before ¥{median(before):,.0f} ({len(before)})"
        else:
            f_sales = f"{len(recent)} sales in the last 7 days"
        pc = prev_by.get(url)
        if pc:
            pa = ((pc.get("analysis") or {}).get("representative_price")) or ((pc.get("grades") or {}).get("psa10") or {}).get("lowest_price")
            pn = (c.get("analysis") or {}).get("representative_price") or ask
            if pa:
                mv = (pn / pa - 1) * 100
                if abs(mv) >= T["move"]:
                    f.append((abs(mv) / T["move"] * 0.8, f"{mv:+.0f}% since the previous check (¥{pa:,}→¥{pn:,})"))
        hn, hp = heat(url, 0), heat(url, 7)
        if hn is not None and hp and max(hn, hp) >= 1:
            hc = (hn / hp - 1) * 100
            if abs(hc) >= T["heat"]:
                f.append((abs(hc) / T["heat"] * 0.7, f"PSA10 sales/day {hn:.1f} vs {hp:.1f} a week ago ({hc:+.0f}%)"))
        lim = (limits.get(url) or {}).get("price")
        if lim and ask > lim and (ask / lim - 1) * 100 <= 5:
            f.append((1.2, f"lowest ask within {(ask / lim - 1) * 100:.1f}% of your limit ¥{lim:,}"))
        if not f:
            continue
        f.sort(reverse=True)
        depth = f"{g.get('count_within_15pct', '?')}/{len(g.get('top20_cheapest_listings') or []) or 20} listings within 15%"
        tiers = (c.get("analysis") or {}).get("tiers") or {}
        tier = f"tiers {tiers.get('definitely_buy')}/{tiers.get('buy_upper')}/{tiers.get('ceiling')}" if tiers else "no tiers"
        rows.append((f[0][0], sid, name, [t for _, t in f], f"ask ¥{ask:,} · {tier} · limit {('¥%s' % format(lim, ',')) if lim else 'none'} · {depth} · {f_sales} · sales/day {hn if hn is not None else '—'}"))
    rows.sort(reverse=True)
    top = [r for r in rows if show_all or r[0] >= 1][: None if show_all else 3]
    if not top:
        print("No card stands out enough for a written analysis this run.")
    for score, sid, name, fs, ctx in top:
        print(f"{sid} {name} · score {score:.1f}\n  findings: " + " | ".join(fs) + f"\n  context: {ctx}")


if __name__ == "__main__":
    main()

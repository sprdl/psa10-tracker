#!/usr/bin/env python3
"""
Hype exposure per tracked card → data/hype.json (the site's "Hype exposure" panel).

    python3 scripts/hype.py --ref - <<'EOF'      # HREF lines from __oddsBuilder('hype') (monthly, FULL-CHECK 5b)
    HREF sv8a%20217%2F187 69255:68248:74.3:250926:260926
    EOF
    python3 scripts/hype.py --seed               # tracked cards found in the reference pool (first build only)
    python3 scripts/hype.py --show               # print the tracked cards' readings

Daily readings come from the full check's pokeca_premium.js lines (g token), saved by premium.save().

What it measures (project doc crash-resilience-study-2026-10-03): two things that, in every market fall
since 2021, separated the cards that held up from the ones that fell hardest:
  1. gain  = the card's PSA10 price change over the last 12 months MINUS the market's (My-tier index) —
             how much of a hype run it is still carrying;
  2. trade = how actively it trades (pokeca-chart PSA10 volume over the last 120 days, per month).
Each is ranked against a pool of ~280 PSA10s (reference rebuilt monthly); exposure = the average of the
two ranks, re-ranked in the pool (0–100). High = top third, Low = bottom third.

Backtest (rolling, every month 2021-09…2026-07, next 3 months, vs the market; skip-month measures):
in the 14 three-month stretches where the market fell >5%, the most exposed third did −5.3% and the
least exposed +5.4% (most exposed worse in 13 of 14); in the 18 rising stretches, +3.0% vs −3.6% (most
exposed better in 78%). So exposure is how hard a card swings WITH the market, not whether it's a buy.

Measure (identical in pricecheck/scripts/pokeca_premium.js and scripts/odds_model_builder.js):
  now  = median PSA10 price of the 30 days to the latest point
  base = median PSA10 price 335–395 days before it (none if the history starts later than 485 days back:
         launch prices would read as a shed hype run)
  vol  = sum of PSA10 point volumes in the last 120 days ÷ 4
"""
import bisect
import json
import math
import re
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import unquote

JST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parent.parent
PATH = ROOT / "data" / "hype.json"
EVIDENCE = {"fall": {"windows": 14, "high": -5.3, "low": 5.4, "high_worse": 13},
            "rise": {"windows": 18, "high": 3.0, "low": -3.6, "high_better_pct": 78},
            "doc": "crash-resilience-study-2026-10-03"}


def _d6(s):
    return date(2000 + int(s[:2]), int(s[2:4]), int(s[4:6]))


def parse_g(g):
    """'base:now:vol:yymmdd:yymmdd' -> dict (base None when the card is under a year old)."""
    if not g or g == "-":
        return None
    b, n, v, bd, nd = g.split(":")
    return {"base": None if b in ("-", "null", "") else float(b), "now": float(n), "vol": float(v),
            "base_d": _d6(bd).isoformat(), "d": _d6(nd).isoformat()}


def market_levels(root=ROOT):
    ci = json.loads((root / "data" / "custom_index.json").read_text(encoding="utf-8"))
    pts = sorted((p["d"], p["level"]) for p in ci.get("series", []) if p.get("level"))
    return [p[0] for p in pts], [p[1] for p in pts]


def level_at(lv, d):
    ds, ls = lv
    i = bisect.bisect_right(ds, d) - 1
    return ls[i] if i >= 0 else None


def measure(h, lv):
    """log gain vs the market and log trade for one reading."""
    gain = None
    if h and h["base"]:
        a, b = level_at(lv, h["base_d"]), level_at(lv, h["d"])
        if a and b:
            gain = math.log(h["now"] / h["base"]) - math.log(b / a)
    return gain, math.log1p(h["vol"]) if h else None


def pct(sorted_vals, x):
    if x is None or not sorted_vals:
        return None
    lo, hi = bisect.bisect_left(sorted_vals, x), bisect.bisect_right(sorted_vals, x)
    return round(100 * (lo + hi) / 2 / len(sorted_vals), 1)


def load():
    return json.loads(PATH.read_text(encoding="utf-8")) if PATH.exists() else {}


def build_ref(lines, root=ROOT):
    lv = market_levels(root)
    gains, trades, both = [], [], []
    for ln in lines:
        p = ln.strip().split(" ")
        if len(p) < 3 or p[0] != "HREF":
            continue
        g, t = measure(parse_g(p[2]), lv)
        if t is not None:
            trades.append(t)
        if g is not None:
            gains.append(g)
            both.append((g, t))
    gains.sort(); trades.sort()
    scores = sorted((pct(gains, g) + pct(trades, t)) / 2 for g, t in both)
    return {"built": datetime.now(JST).date().isoformat(), "n": len(both), "gain": [round(x, 4) for x in gains],
            "trade": [round(x, 4) for x in trades], "score": scores}


def score(h, ref, lv):
    g, t = measure(h, lv)
    pg, pt = pct(ref["gain"], g), pct(ref["trade"], t)
    out = {"now": h["now"], "base": h["base"], "base_d": h["base_d"], "d": h["d"], "vol": h["vol"],
           "gain_pct": None if g is None else round(math.expm1(g) * 100, 1), "gain_rank": pg, "trade_rank": pt}
    if pg is not None and pt is not None:
        s = pct(ref["score"], (pg + pt) / 2)
        out.update(score=s, level="high" if s >= 66.7 else "low" if s <= 33.3 else "medium")
    return out


def save(readings, root=ROOT, push=True, note=""):
    """readings: {snkrdunk id: parsed g dict}."""
    data = load()
    ref = data.get("ref")
    if not ref:
        print("hype: no reference pool yet (run scripts/hype.py --ref); skipped.")
        return
    lv = market_levels(root)
    cards = data.setdefault("cards", {})
    for sid, h in readings.items():
        if h:
            cards[f"https://snkrdunk.com/apparels/{sid}"] = score(h, ref, lv)
    data["updated"] = datetime.now(JST).replace(microsecond=0).isoformat()
    data["evidence"] = EVIDENCE
    data["about"] = __doc__.split("What it measures")[1].split("Measure (identical")[0].strip()
    PATH.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    hi = [s for s, h in readings.items() if h and cards.get(f"https://snkrdunk.com/apparels/{s}", {}).get("level") == "high"]
    print(f"hype: {sum(1 for h in readings.values() if h)} card(s) scored{note}" + (f" · high exposure: {', '.join(hi)}" if hi else ""))
    if push:
        for cmd in (["git", "add", str(PATH)], ["git", "commit", "-q", "-m", "hype: exposure readings"], ["git", "push", "-q"]):
            r = subprocess.run(cmd, cwd=root, text=True, capture_output=True)
            if r.returncode != 0 and "nothing to commit" not in (r.stdout + r.stderr):
                print(f"hype: {' '.join(cmd)} failed: {(r.stderr or r.stdout).strip()}")
                return
        print("hype: pushed.")


def tracked(root=ROOT):
    """{lowercased card code: snkrdunk id} for the cards in the latest snapshot."""
    m = json.loads((root / "data" / "manifest.json").read_text(encoding="utf-8"))
    snap = json.loads((root / "data" / "snapshots" / sorted(m["snapshots"], key=lambda s: s["collected_at_jst"])[-1]["file"]).read_text(encoding="utf-8"))
    out = {}
    for c in snap.get("cards", []):
        mm = re.search(r"\[([^\]]+)\]", c.get("card_name_ja", ""))
        if mm:
            out[mm.group(1).lower()] = c["url"].rstrip("/").split("/")[-1]
    return out


def main():
    args = sys.argv[1:]
    push = "--no-push" not in args
    if "--show" in args:
        for url, e in sorted(load().get("cards", {}).items(), key=lambda kv: -(kv[1].get("score") or -1)):
            print(url.split("/")[-1], e.get("level"), e.get("score"), f"gain {e.get('gain_pct')}% rank {e.get('gain_rank')}", f"trade rank {e.get('trade_rank')}")
        return
    if "--ref" in args or "--seed" in args:
        if push:
            subprocess.run(["git", "pull", "--ff-only", "--quiet"], cwd=ROOT)
        files = [a for a in args if not a.startswith("--")]
        if "--ref" in args:
            lines = (sys.stdin.read() if not files or files[0] == "-" else Path(files[0]).read_text(encoding="utf-8")).splitlines()
            data = load()
            data["ref"] = build_ref(lines)
            data["ref_lines"] = [l.strip() for l in lines if l.startswith("HREF")]   # kept for --seed
            PATH.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
            print(f"hype: reference pool {data['ref']['n']} cards (+{len(data['ref']['trade']) - data['ref']['n']} too young for the 12-month part)")
        if "--seed" in args or "--ref" in args:
            tr = tracked()
            seen = {}
            for l in load().get("ref_lines", []):
                p = l.split(" ")
                sid = tr.get(unquote(p[1]).lower())
                if sid:
                    seen[sid] = parse_g(p[2])
            save(seen, push=push, note=" from the reference pool (the next full check reads every tracked card)")
        return
    print(__doc__)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Odds that the lowest PSA10 ask reaches a price within 30 / 90 days, from
data/odds_model.json (method and backtest in its "about"). Same maths as the
site (assets/app.js, touchOdds), so logged odds match what the site showed.

Every full price check logs the model's odds for each card's Definitely-buy and
Buy prices (and any saved limit) to data/odds_log.json; build_calls.py scores
them like the evaluation's stated odds, so the Track record shows how well
calibrated the model is.

    python3 scripts/odds_model.py            # print today's odds for every tracked card
"""
import json
import math
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODEL = ROOT / "data" / "odds_model.json"
LOG = ROOT / "data" / "odds_log.json"
JST = timezone(timedelta(hours=9))
LOG_EVERY_DAYS = 7


def load_model(root=ROOT):
    p = root / "data" / "odds_model.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def card_code(model, name):
    m = re.search(r"\[([^\]]+)\]", name or "")
    code = (m.group(1) if m else "").lower().strip()
    if code in model["cards"]:
        return code
    promo = re.match(r"^([a-z]+-p)\s+(\d+)$", code)
    if promo and f"{promo.group(2)}/{promo.group(1)}" in model["cards"]:
        return f"{promo.group(2)}/{promo.group(1)}"
    return None


def z_share(qs, z):
    if z <= qs[0]:
        return 0.0
    n = len(qs) - 1
    if z >= qs[n]:
        return 1.0
    i = 0
    while i < n and qs[i + 1] < z:
        i += 1
    f = (z - qs[i]) / ((qs[i + 1] - qs[i]) or 1)
    return (i + f) / n


def odds(model, name, ask, price):
    """(p30, p90) or None. price >= ask means it's already there."""
    if not model or not ask or not price or price >= ask:
        return None
    code = card_code(model, name)
    s30, s90 = (model["cards"][code][:2] if code else model["pool_sigma"])
    a = model["about"]
    x = math.log(price / ask)
    p30 = min(a.get("cap", 0.99), a["touch_factor_30"] * z_share(model["z_end30"], x / s30))
    p90 = max(p30, min(a.get("cap", 0.99), a["touch_factor_90"] * z_share(model["z_touch90"], x / s90)))
    return round(p30, 3), round(p90, 3)


def log_for_snapshot(data, root=ROOT):
    """Append the model's odds for each card's tier prices and saved limit. A (card, price) pair is
    logged at most once every LOG_EVERY_DAYS days, so overlapping near-identical forecasts don't swamp the score."""
    model = load_model(root)
    if not model or data.get("check_mode", "full") != "full":
        return 0
    made = data.get("collected_at_jst")
    lim_path = root / "data" / "limits.json"
    limits = json.loads(lim_path.read_text(encoding="utf-8")).get("limits", {}) if lim_path.exists() else {}
    log_path = root / "data" / "odds_log.json"
    log = json.loads(log_path.read_text(encoding="utf-8")) if log_path.exists() else {"entries": []}
    last = {}
    for e in log["entries"]:
        k = (e["url"], e["price"])
        last[k] = max(last.get(k, ""), e["made"])
    now = datetime.fromisoformat(made) if made else datetime.now(JST)
    added = 0
    for c in data.get("cards", []):
        ask = ((c.get("grades") or {}).get("psa10") or {}).get("lowest_price")
        t = (c.get("analysis") or {}).get("tiers") or {}
        targets = [(t.get("definitely_buy"), "definitely_buy"), (t.get("buy_upper"), "buy")]
        lim = (limits.get(c.get("url")) or {}).get("price")
        if lim:
            targets.append((lim, "limit"))
        for price, kind in targets:
            prev = last.get((c.get("url"), price))
            if not price or (prev and now - datetime.fromisoformat(prev) < timedelta(days=LOG_EVERY_DAYS)):
                continue
            o = odds(model, c.get("card_name_ja"), ask, price)
            if not o:
                continue
            log["entries"].append({"url": c.get("url"), "made": made, "ask": ask, "price": price, "kind": kind,
                                   "p30": o[0], "p90": o[1], "model": model.get("built")})
            last[(c.get("url"), price)] = made
            added += 1
    log_path.write_text(json.dumps(log, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    return added


if __name__ == "__main__":
    m = load_model()
    man = json.loads((ROOT / "data" / "manifest.json").read_text(encoding="utf-8"))
    last = sorted(man["snapshots"], key=lambda s: s["collected_at_jst"])[-1]["file"]
    d = json.loads((ROOT / "data" / "snapshots" / last).read_text(encoding="utf-8"))
    for c in d["cards"]:
        ask = ((c.get("grades") or {}).get("psa10") or {}).get("lowest_price")
        t = (c.get("analysis") or {}).get("tiers") or {}
        for k in ("definitely_buy", "buy_upper"):
            o = odds(m, c.get("card_name_ja"), ask, t.get(k))
            if o:
                print(f"{c['card_name_ja'][:24]:26} ask {ask:>7,} {k:15} {t[k]:>7,}  30d {o[0]:.0%}  90d {o[1]:.0%}  ({card_code(m, c['card_name_ja']) or 'pool'})")

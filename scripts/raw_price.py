#!/usr/bin/env python3
"""
The raw A-rank price (decided 2026-10-08), the same rule as rawPrice() in assets/app.js.

The cheapest raw listing is often a copy that won't grade (bad centering) and doesn't sell, while
PSA10-worthy copies sell higher (Mega Charizard X ex SAR on 2026-10-08: ask ¥72,000, sales ¥75–80k).
So the price is the median of the last 5 one-copy A-rank sales from the past 30 days, but never below
the lowest ask (you can't buy under it). Fewer than 3 such sales: the lowest ask. No listing: the median.

    from raw_price import raw_price
    raw_price(72000, [77000, 75000, 75000, 75000, 79999])   # -> (75000, "sales")
"""
from statistics import median

N, DAYS, MIN = 5, 30, 3


def raw_price(ask, recent_sales):
    """ask: lowest A-rank ask or None; recent_sales: prices from the last 30 days, newest first.
    Returns (price or None, "sales" | "ask")."""
    s = [p for p in (recent_sales or []) if p][:N]
    med = median(s) if len(s) >= MIN else None
    if med is None:
        return ask, "ask"
    if ask is None or med > ask:
        return round(med), "sales"
    return ask, "ask"

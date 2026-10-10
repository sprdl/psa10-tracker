#!/usr/bin/env python3
"""
Everything the repo already knows about ONE card, printed for the pokemon-tcg-card-evaluation skill, so an
evaluation inside a price check reuses this run's data instead of reading the pages again.

    python3 scripts/eval_context.py <snkrdunk_id | url>                 # the card's evaluation inputs
    python3 scripts/eval_context.py <id> --odds 52000 58000 68000       # + limit-odds for candidate prices

Prints (from the latest snapshot and data/*.json; nothing is fetched):
  CARD      name, url, tracked since, queue reason, ownership (paid, grading, date) and saved limit / sell target
  PSA10     lowest ask, depth (listings within 15%), as-of, recent one-copy sales, sales per day
  RAW A     lowest ask, recent sales, the raw A-rank price (scripts/raw_price.py rule) and where it came from
  SUPPLY    PSA10 population, gem rate, DIY replacement cost = (raw A-rank + ¥12,430) ÷ gem rate
  OWNED     cost basis (slab: paid; raw: (paid + grading & shipping) ÷ gem rate) and break-even after SNKRDUNK fees
  CONTEXT   slab premium vs its norm, hype exposure, card age (release month) and the age-curve drift
  HISTORY   our own tracked PSA10 price range since tracking began (not the peak: get that from SNKRDUNK's
            trade history or pokeca-chart, as the evaluation skill says)
  ANALYSIS  what the card has now (tiers, verdict, peak, sell tiers)
  MARKET    My-tier index level, 7- and 30-day change, correction rule / rally flag, pokeca-chart PSA10 index,
            event rule window
  ODDS      limit-odds model, 30/90 days, for --odds prices, else the current tiers, else a ladder below the ask
What it can't give (read it in the browser, as the evaluation skill says): the peak-month median and longer price
history, set/release details, and fresh depth for a card the run only read with a quick check.
"""
import json
import math
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from raw_price import raw_price  # noqa: E402
from build_history import sale_age_days, sales_per_day  # noqa: E402
import odds_model  # noqa: E402
import eval_queue  # noqa: E402

JST = timezone(timedelta(hours=9))
DIY_FEES = 12430          # PSA Japan Standard, one card: ¥9,980 + insurance & shipping ¥1,900 + handling ¥550
STANDARD_CAP = 150000     # declared value limit on Standard
FEE_RATE, SHIP = 0.095, 1000   # SNKRDUNK Regular rank, seller-paid shipping


def J(name):
    p = ROOT / "data" / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def yen(v):
    return "—" if v is None else f"¥{round(v):,}"


def pct(a, b):
    return f"{(a / b - 1) * 100:+.1f}%" if a and b else "n/a"


def recent(sales, ref, days=30):
    out = []
    for s in sales or []:
        a = sale_age_days(s.get("when"), ref)
        if a is not None and a <= days and s.get("price"):
            out.append((a, s["price"], s.get("when")))
    return sorted(out)   # newest first


def break_even(basis):
    transfer = 200 if basis < 30000 else 300
    return (basis + transfer + SHIP) / (1 - FEE_RATE)


def main():
    args = sys.argv[1:]
    if not args:
        sys.exit(__doc__)
    url = eval_queue.to_url(args[0])
    odds_prices = [int(x) for x in args[args.index("--odds") + 1:]] if "--odds" in args else []
    snap = eval_queue.latest_snapshot(ROOT)
    card = next((c for c in snap.get("cards", []) if c.get("url", "").rstrip("/") == url), None)
    if not card:
        sys.exit(f"{url} is not in the latest snapshot ({snap.get('collected_at_jst')}). Publish a check that reads it first.")
    ref = datetime.fromisoformat(snap["collected_at_jst"])
    name = card.get("card_name_ja", "")
    g10 = (card.get("grades") or {}).get("psa10") or {}
    ga = (card.get("grades") or {}).get("raw_a_grade") or {}
    print(f"Snapshot {snap.get('collected_at_jst')} ({snap.get('check_mode', 'full')} check)\n")

    # CARD
    print(f"CARD      {name}\n          {url}")
    tr = next((t for t in J("tracked_cards.json").get("cards", []) if t.get("url", "").rstrip("/") == url), None)
    if tr:
        print(f"          tracked since {tr.get('added')} ({tr.get('note', '')}); altema {tr.get('altema_url') or 'not found yet'}")
    q = eval_queue.load(ROOT)["queue"].get(url)
    if q:
        print(f"          evaluation queue: {q.get('why')} (since {q.get('since')})")
    held = [h for h in J("holdings.json").get("holdings", []) if h.get("card_url", "").rstrip("/") == url]
    for h in held:
        print(f"          OWNED {h.get('condition')}: paid {yen(h.get('purchase_price_jpy'))} on {h.get('purchase_date')}"
              f", grading & shipping {yen((h.get('grading_fee_jpy') or 0) + (h.get('shipping_insurance_jpy') or 0))}")
    lim = (J("limits.json").get("limits") or {}).get(url)
    if lim:
        print(f"          your limit {yen(lim.get('price'))} (set {str(lim.get('set'))[:10]})")
    tgt = (J("sell_targets.json").get("targets") or {}).get(url)
    if tgt:
        print(f"          your sell target {yen(tgt.get('price'))}")

    # PSA10
    ask = g10.get("lowest_price")
    s10 = recent(g10.get("recent_completed_sales"), ref)
    print(f"\nPSA10     lowest ask {yen(ask)}" + (f"  ({g10.get('error')})" if g10.get("error") else ""))
    if "count_within_15pct" in g10:
        print(f"          depth: {g10.get('count_within_15pct')} listing(s) within 15% of the lowest, "
              f"{len(g10.get('top20_cheapest_listings') or [])} read" + (f" (as of {g10['listings_as_of']})" if g10.get("listings_as_of") else ""))
    else:
        print("          depth: not read yet (a quick check only reads the tile): read the listings page if it matters")
    allsales = g10.get("recent_completed_sales") or []
    print(f"          sales (newest first, 1枚): " + (", ".join(f"{yen(s['price'])} {s.get('when')}" for s in allsales[::-1][:10]) or "none"))
    if s10:
        ps = sorted(p for _, p, _ in s10)
        spd = sales_per_day(allsales, ref)
        print(f"          last 30 days: {len(s10)} sale(s) read (SNKRDUNK shows the latest 20), {yen(ps[0])}–{yen(ps[-1])}, "
              f"median {yen(ps[len(ps) // 2])}" + (f"; about {spd:.1f} sales/day (Hot ≥5, Active ≥3, Slow ≥1.2)" if spd else ""))

    # RAW A
    ra = ga.get("lowest_price")
    sa = recent(ga.get("recent_completed_sales"), ref)
    rp, src = raw_price(ra, [p for _, p, _ in sa])
    print(f"\nRAW A     lowest ask {yen(ra)}; {len(sa)} one-copy sale(s) in 30 days"
          + (f" ({', '.join(yen(p) for _, p, _ in sa[:5])} newest first)" if sa else ""))
    print(f"          raw A-rank price {yen(rp)} (from the {src}; rule: median of the last 5 sales in 30 days, never below the ask)")

    # SUPPLY / DIY
    pop, gem = card.get("psa10_population"), card.get("psa10_gem_rate_pct")
    print(f"\nSUPPLY    PSA10 population {pop if pop is not None else 'n/a'}, gem rate {f'{gem}%' if gem else 'n/a'}"
          + (f" (as of {card['population_as_of']})" if card.get("population_as_of") else "")
          + (f"  [{card.get('population_error') or card.get('population_note')}]" if card.get("population_error") or card.get("population_note") else ""))
    if rp and gem:
        diy = (rp + DIY_FEES) / (gem / 100)
        print(f"          DIY replacement cost ({yen(rp)} + ¥12,430) ÷ {gem}% = {yen(diy)}"
              + (f"; PSA10 ask is {pct(ask, diy)} vs DIY" if ask else "")
              + ("  — over Standard's ¥150,000 declared-value cap: Standard doesn't apply" if (ask or 0) > STANDARD_CAP else ""))

    # OWNED
    for h in held:
        paid = h.get("purchase_price_jpy") or 0
        if h.get("condition") == "raw_to_grade":
            basis = (paid + (h.get("grading_fee_jpy") or 9980) + (h.get("shipping_insurance_jpy") or 2450)) / ((gem or 100) / 100)
            how = f"(paid + grading & shipping) ÷ gem rate {gem or 'n/a (fees added undivided)'}%"
        else:
            basis, how = paid, "price paid for the slab"
        be = break_even(basis)
        net = (ask * (1 - FEE_RATE) - (200 if ask < 30000 else 300) - SHIP) if ask else None
        print(f"\nOWNED     basis {yen(basis)} = {how}; break-even sale after fees {yen(be)} ({pct(be, basis)})"
              + (f"; selling at today's ask nets {yen(net)} ({'+' if net >= basis else ''}{yen(net - basis)} vs basis)" if net else ""))

    # CONTEXT
    pr = (J("premium.json").get("cards") or {}).get(url)
    hy = (J("hype.json").get("cards") or {}).get(url)
    print()
    if pr and not pr.get("error"):
        print(f"CONTEXT   slab premium (pokeca-chart PSA10 ÷ raw 美品) {pr.get('prem')}x vs its 6-month norm {pr.get('norm')}x ({pr.get('dev'):+}%), as of {pr.get('asof')}")
    else:
        print(f"CONTEXT   slab premium: {(pr or {}).get('error', 'not available')}")
    if hy and hy.get("level"):
        print(f"          hype exposure {hy.get('level')} (score {hy.get('score')}; 12-month gain vs market {hy.get('gain_pct')}%, "
              f"gain rank {hy.get('gain_rank')}, trade rank {hy.get('trade_rank')})")
    elif hy:
        print(f"          hype exposure: no reading yet (under 12 months of history; trade rank {hy.get('trade_rank')})")
    else:
        print("          hype exposure: no reading (card not on pokeca-chart's pool or too new)")
    vm = J("value_model.json")
    code = None
    m = re.search(r"\[([^\]]+)\]", name)
    if m:
        code = m.group(1).lower().strip()
    rel = (vm.get("release") or {}).get(code)
    if rel:
        y, mo = map(int, rel.split("-"))
        age = (ref.year - y) * 12 + ref.month - mo
        band = next((b for b in vm.get("age_curve", []) if b["from"] <= age < b["to"]), None)
        print(f"          released {rel} → {age} month(s) old" + (f"; age-curve drift {band['monthly'] * 100:+.1f}%/month vs the market" if band else ""))
    else:
        print("          release month unknown to the value model: look it up (age matters under 9 months)")

    # HISTORY (ours)
    pts = [(e["d"], e["p"][url][0]) for e in J("history.json").get("snapshots", []) if url in (e.get("p") or {}) and e["p"][url] and e["p"][url][0]]
    if pts:
        lo, hi = min(pts, key=lambda x: x[1]), max(pts, key=lambda x: x[1])
        print(f"\nHISTORY   tracked PSA10 price since {pts[0][0][:10]}: first {yen(pts[0][1])}, low {yen(lo[1])} ({lo[0][:10]}), high {yen(hi[1])} ({hi[0][:10]}), {len(pts)} checks")
    else:
        print("\nHISTORY   no tracked PSA10 price yet")

    # ANALYSIS now
    a = card.get("analysis") or {}
    t, v = a.get("tiers"), a.get("verdict") or {}
    print(f"\nANALYSIS  tiers {'/'.join(yen(t[k]) for k in ('definitely_buy', 'buy_upper', 'ceiling')) if t else 'none'}"
          f"; verdict {v.get('tag', 'none')}" + (f" written {str(v.get('written'))[:10]}" if v.get("written") else "")
          + (f"; peak {yen(a['peak'].get('price'))} {a['peak'].get('when')}" if a.get("peak") else "")
          + (f"; sell tiers TP {yen(a['sell_tiers'].get('take_profit_from'))} / sell {yen(a['sell_tiers'].get('sell_from'))}" if a.get("sell_tiers") else ""))

    # MARKET
    ser = sorted((p["d"], p["level"]) for p in J("custom_index.json").get("series", []) if p.get("level"))
    if ser:
        d0, lv = ser[-1]

        def back(days):
            cut = (datetime.fromisoformat(d0) - timedelta(days=days)).date().isoformat()
            o = [x for x in ser if x[0] <= cut]
            return o[-1][1] if o else None
        b7, b30 = back(7), back(30)
        c7 = (lv / b7 - 1) * 100 if b7 else None
        c30 = (lv / b30 - 1) * 100 if b30 else None
        print(f"\nMARKET    My-tier index {lv} on {d0}; 7d {f'{c7:+.1f}%' if c7 is not None else 'n/a'}, 30d {f'{c30:+.1f}%' if c30 is not None else 'n/a (under 30 days of data)'}")
        print(f"          correction rule {'ON (Buy only at or below Definitely-buy)' if c30 is not None and c30 < -10 else 'off'}; "
              f"rally flag {'ON (flag only: limits set before the rally fill less often)' if c7 is not None and c7 >= 10 else 'off'}")
    idx = ((snap.get("pokeca_chart_index") or {}).get("psa10") or {})
    if idx:
        print(f"          pokeca-chart PSA10 index {yen(idx.get('latest_index_value_jpy'))}, month {idx.get('month_change_pct')}%, year {idx.get('year_change_pct')}%, volume {idx.get('volume_trend')}")
    ev = subprocess.run([sys.executable, str(ROOT / "scripts" / "events.py"), "window"], cwd=ROOT, text=True, capture_output=True)
    print("          " + (ev.stdout.strip() or ev.stderr.strip()).replace("\n", "\n          "))

    # ODDS
    model = odds_model.load_model(ROOT)
    prices = odds_prices or ([t[k] for k in ("definitely_buy", "buy_upper") if t] if t else
                             ([round(ask * f, -2) for f in (0.95, 0.9, 0.85, 0.8, 0.75, 0.7)] if ask else []))
    if model and ask and prices:
        basis = odds_model.card_code(model, name) or "pool volatility (card not in the model)"
        print(f"\nODDS      lowest ask reaching the price (limit-odds model built {model.get('built')}, {basis}):")
        for p in prices:
            o = odds_model.odds(model, name, ask, p)
            print(f"          {yen(p):>10} ({pct(p, ask)}): " + (f"30d {o[0]:.0%}  90d {o[1]:.0%}" if o else "at or above the ask already"))
    elif not ask:
        print("\nODDS      no PSA10 ask: no odds (a card with no PSA10 market gets a `defer` verdict)")


if __name__ == "__main__":
    main()

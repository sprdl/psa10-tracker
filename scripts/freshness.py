#!/usr/bin/env python3
"""
Is everything the site shows still fresh? One line per data source that's older than its cadence.

    python3 scripts/freshness.py            # table of every source: age, cadence, which check refreshes it
    python3 scripts/freshness.py --stale    # only the stale ones (what full_update.py / quick_update.py print)

Where each part of the site comes from and how often it should be refreshed (2026-10-08 audit):

| Source (file)                         | Shown on the site as                      | Refreshed by                       | Cadence |
|---------------------------------------|-------------------------------------------|------------------------------------|---------|
| snapshot: lowest asks, sales, favs    | prices everywhere, signals, verdict chips | quick + full check (SNKRDUNK)      | several times a day |
| snapshot: listing depth / top-20      | Listings tab, depth tile                  | full check                         | daily |
| snapshot: pokeca_chart_index          | Market strip, KPI tiles, volume pill      | full check (pokeca_both.js)        | daily |
| snapshot: psa10_population / gem rate | Population tile, DIY tab                  | full check (altema)                | young cards daily, mature (8,000+) Mondays |
| custom_index.json (My-tier index)     | My-tier tile + chart, correction rule     | full check (MYTIER line)           | daily |
| premium.json (slab premium)           | DIY tab premium panel                     | full check (PREM lines)            | daily |
| hype.json readings                    | Hype exposure panel, High hype chip       | full check (PREM lines, g token)   | daily |
| hype.json ref pool                    | Hype exposure ranks                       | full check step 5b (monthly)       | monthly |
| holdings_prices.json                  | Holdings values for untracked/sealed      | full check (HELD lines)            | daily |
| scout.json                            | Scout page                                | full check (pokeca_scout.js)       | every 2 days |
| odds_model.json                       | limit odds, Tier check, predictions       | full check step 5b                 | monthly |
| value_model.json                      | Upside tab, combination finder            | full check step 5b                 | monthly |
| events.json                           | release calendar, event rule              | full check step 6b (Mondays)       | weekly |
| psa_backlog.json                      | Market page PSA backlog panel             | full check step 8i (WebFetch)      | every other Tuesday |
| mercari.json                          | Mercari row + alerts                      | full + quick (cards near limit)    | when due |
| stories / insights / verdicts / tiers | Story tab, analyses, verdict box          | full check steps 7b, 8b–8h         | when due (FOLLOW-UPS) |
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JST = timezone(timedelta(hours=9))
H = 3600


def _ts(s):
    if not s:
        return None
    s = str(s)
    if len(s) == 7:          # "2026-09" (value model)
        s += "-01"
    d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    return d if d.tzinfo else d.replace(tzinfo=JST)


def _load(root, name):
    p = root / "data" / name
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
    except Exception:
        return None


def checks(root=ROOT, now=None):
    """[(name, last update or None, max age in seconds, refreshed by)]"""
    now = now or datetime.now(JST)
    out = []
    m = _load(root, "manifest.json") or {}
    snaps = sorted([s for s in m.get("snapshots", []) if s.get("collected_at_jst")], key=lambda s: s["collected_at_jst"])
    last_full = None
    latest = None
    for s in reversed(snaps):
        d = _load(root, "snapshots/" + s["file"]) or {}
        if latest is None:
            latest = d
        if d.get("check_mode") != "quick":
            last_full = d
            break
    out.append(("SNKRDUNK prices (latest snapshot)", (latest or {}).get("collected_at_jst"), 26 * H, "quick or full check"))
    out.append(("full check: depth, pokeca index, volume", (last_full or {}).get("collected_at_jst"), 30 * H, "full check"))
    ci = _load(root, "custom_index.json") or {}
    ser = ci.get("series") or []
    out.append(("My-tier index", ser[-1]["d"] + "T00:00:00+09:00" if ser else None, 48 * H, "full check (MYTIER)"))
    for name, label in (("premium.json", "slab premium"), ("hype.json", "hype exposure readings"),
                        ("holdings_prices.json", "Holdings prices (untracked/sealed)")):
        d = _load(root, name)
        if d is not None:
            out.append((label, d.get("updated"), 30 * H, "full check"))
    hy = _load(root, "hype.json") or {}
    if hy.get("ref"):
        out.append(("hype reference pool", hy["ref"].get("built"), 36 * 24 * H, "full check step 5b"))
    sc = _load(root, "scout.json")
    if sc is not None:
        out.append(("Scout", sc.get("updated"), 3 * 24 * H, "full check (scout)"))
    pb = _load(root, "psa_backlog.json")
    if pb and pb.get("readings"):   # PSA publishes every other Tuesday; 17 days allows a late update
        out.append(("PSA backlog (Value tier reopening)", pb["readings"][-1]["d"] + "T00:00:00+09:00", 17 * 24 * H, "full check step 8i (psa_backlog.py from-page)"))
    om = _load(root, "odds_model.json") or {}
    out.append(("limit-odds model", om.get("built"), 32 * 24 * H, "full check step 5b"))
    vm = _load(root, "value_model.json") or {}
    out.append(("value model (Upside)", vm.get("built"), 62 * 24 * H, "full check step 5b"))
    # population: young cards daily, mature weekly
    if last_full:
        young = [c for c in last_full.get("cards", []) if isinstance(c.get("psa10_population"), int) and c["psa10_population"] < 8000]
        mature = [c for c in last_full.get("cards", []) if isinstance(c.get("psa10_population"), int) and c["psa10_population"] >= 8000]
        for group, label, age in ((young, "PSA10 population (young cards)", 34 * H), (mature, "PSA10 population (mature cards)", 8 * 24 * H)):
            if group:
                oldest = min((c.get("population_as_of") or last_full["collected_at_jst"]) for c in group)
                out.append((label, oldest, age, "full check (altema)"))
    return out


def stale(root=ROOT, now=None):
    now = now or datetime.now(JST)
    res = []
    for name, when, max_age, by in checks(root, now):
        t = _ts(when)
        if t is None or (now - t).total_seconds() > max_age:
            res.append((name, when, by))
    return res


def print_stale(root=ROOT):
    try:
        st = stale(root)
    except Exception as e:  # never break a price check over this
        print(f"\nFRESHNESS: skipped ({e}).")
        return
    if not st:
        print("\nFRESHNESS: everything the site shows is within its refresh cadence.")
        return
    print("\nSTALE DATA (refresh in this or the next full check; say so in the chat message):")
    for name, when, by in st:
        print(f"  {name}: last {str(when)[:16] if when else 'never'} — refreshed by {by}")


def main():
    now = datetime.now(JST)
    if "--stale" in sys.argv:
        print_stale()
        return
    for name, when, max_age, by in checks(ROOT, now):
        t = _ts(when)
        age = (now - t).total_seconds() / 3600 if t else None
        flag = "STALE" if age is None or age * 3600 > max_age else "ok"
        print(f"{flag:5}  {name:42} {str(when)[:16] if when else '—':16}  age {('%.0fh' % age) if age is not None else '—':>6} / max {max_age / 3600:.0f}h  ({by})")


if __name__ == "__main__":
    main()

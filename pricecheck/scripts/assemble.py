#!/usr/bin/env python3
"""Assemble the final price-check JSON from raw extractor results.

Usage:
  python3 assemble.py RAW.json --out OUT.json [--prev PREVIOUS_OUTPUT.json]

RAW.json is what Claude writes during the run, pasting each extractor's result verbatim:
{
  "cards": {
    "<snkrdunk_id>": {
      "base":   <snkrdunk_base.js result>,
      "psa10":  <snkrdunk_listings.js result on conditionIds=22>,
      "a":      <snkrdunk_listings.js result on conditionIds=18>,
      "altema": <altema_population.js result>  or  {"skipped": "<reason>"},
      "image_url": "<only if freshly fetched this run>"          (optional)
    }, ...
  },
  "index": { "psa10": <pokeca_index.js result on /gr/chart-index/>,
             "raw":   <pokeca_index.js result on /chart-index/> },
  "volume_overrides": { "psa10": {"volume_trend": "...", "volume_note": "..."} },   (optional)
  "psa_tier_status": { ... },                                                      (Mondays only)
  "run_notes": "<anything unusual worth recording>"                                (optional)
}

Card names, URLs and cached image URLs come from references/cards.json, so they never need retyping.
Prints warnings and (with --prev) a change summary to stdout for the short chat message.
"""
import argparse, json, sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
CARDS = json.loads((HERE.parent / "references" / "cards.json").read_text(encoding="utf-8"))["cards"]
LISTING_FIELDS = ["lowest_price", "threshold_115pct_of_lowest", "top20_cheapest_listings",
                  "listings_within_15pct_of_lowest", "count_within_15pct", "count_excluded_over_15pct"]
INDEX_FIELDS = ["latest_index_value_jpy", "day_change_jpy", "day_change_pct", "month_change_jpy",
                "month_change_pct", "year_change_jpy", "year_change_pct", "data_range"]
warnings = []


def grade_obj(listing, sales, label):
    g = {}
    if not listing:
        g["error"] = "listings not collected this run"
    elif listing.get("error"):
        g["error"] = listing["error"]
    else:
        for f in LISTING_FIELDS:
            g[f] = listing.get(f)
        for extra in ("sort_note", "grade_warning"):
            if listing.get(extra):
                g[extra] = listing[extra]
                warnings.append(f"{label}: {listing[extra]}")
    if not sales:
        g["sales_error"] = "completed sales not collected this run"
    elif sales.get("error"):
        g["sales_error"] = sales["error"]
        warnings.append(f"{label}: sales error: {sales['error']}")
    else:
        g["recent_completed_sales"] = sales.get("recent_completed_sales", [])
        if sales.get("sales_note"):
            g["sales_note"] = sales["sales_note"]
    return g


def index_obj(r, override, prev_range, label):
    if not r:
        warnings.append(f"index {label}: not collected")
        return {"error": "not collected this run"}
    o = {f: r.get(f) for f in INDEX_FIELDS}
    missing = [f for f in INDEX_FIELDS if o[f] is None]
    if missing:
        warnings.append(f"index {label}: missing {missing}")
    vs = r.get("volume_stats")
    if vs:
        o["volume_trend"] = r.get("volume_trend_suggested")
        pk = vs["peak_last14"]
        o["volume_note"] = (f"daily trades: 7d avg {vs['avg_last7']}, 14d avg {vs['avg_last14']} vs prior-30d avg "
                            f"{vs['avg_prior30']}; 14d peak {pk['volume']} on {pk['date']} (data to {vs['last_date']})")
    else:
        o["volume_trend"] = None
        o["volume_note"] = r.get("volume_error", "volume data not found")
        warnings.append(f"index {label}: {o['volume_note']}")
    if override:
        o.update({k: v for k, v in override.items() if k in ("volume_trend", "volume_note")})
    if prev_range and prev_range == o.get("data_range"):
        o["same_day_note"] = "data_range unchanged since previous run (index updates once per JST day) — expected, not a failed fetch"
    return o


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("raw"); ap.add_argument("--out", required=True); ap.add_argument("--prev")
    a = ap.parse_args()
    raw = json.loads(Path(a.raw).read_text(encoding="utf-8"))
    prev = json.loads(Path(a.prev).read_text(encoding="utf-8")) if a.prev and Path(a.prev).exists() else None
    now = datetime.now(ZoneInfo("Asia/Tokyo"))

    cards_out = []
    for c in CARDS:
        sid = c["snkrdunk_id"]
        r = raw.get("cards", {}).get(sid)
        o = {"card_name_ja": c["card_name_ja"], "url": c["url"]}
        img = (r or {}).get("image_url") or c.get("image_url")
        if img:
            o["image_url"] = img
        if not r:
            warnings.append(f"{sid}: card missing from raw results")
            o["error"] = "card not collected this run"
            cards_out.append(o); continue
        base = r.get("base") or {}
        o["favorite_count"] = base.get("favorite_count")
        if base.get("error") or base.get("favorite_error"):
            o["favorite_error"] = base.get("error") or base.get("favorite_error")
            warnings.append(f"{sid}: {o['favorite_error']}")
        alt = r.get("altema") or {"skipped": "not collected"}
        if alt.get("skipped"):
            o["population_note"] = f"altema not checked this run ({alt['skipped']})"
        else:
            o["psa10_population"] = alt.get("psa10_population")
            o["psa10_gem_rate_pct"] = alt.get("psa10_gem_rate_pct")
            if alt.get("error"):
                o["population_error"] = alt["error"]
            if alt.get("psa10_population") and c.get("altema_mode") == "weekly_until_graded":
                warnings.append(f"{sid}: altema now shows PSA10 population {alt['psa10_population']} — "
                                "switch this card to altema_mode 'daily' in references/cards.json")
        sales = base.get("sales", {})
        o["grades"] = {"psa10": grade_obj(r.get("psa10"), sales.get("PSA10"), f"{sid} PSA10"),
                       "raw_a_grade": grade_obj(r.get("a"), sales.get("A"), f"{sid} A")}
        cards_out.append(o)

    pidx = (prev or {}).get("pokeca_chart_index", {})
    ov = raw.get("volume_overrides", {})
    idx = raw.get("index", {})
    out = {
        "collected_at_jst": now.isoformat(timespec="seconds"),
        "notes": ("SNKRDUNK listings filtered to 販売中のみ and sorted 安い順; top 20 cheapest per grade, 15% cutoff "
                  "above the lowest ask. Completed sales from 売買履歴 filtered to the grade and 1枚. "
                  "pokeca_chart_index values are whole-market 100-card basket indices, not card prices."
                  + (" " + raw["run_notes"] if raw.get("run_notes") else "")),
        "cards": cards_out,
        "pokeca_chart_index": {
            "psa10": index_obj(idx.get("psa10"), ov.get("psa10"), pidx.get("psa10", {}).get("data_range"), "psa10"),
            "raw_bihin": index_obj(idx.get("raw"), ov.get("raw"), pidx.get("raw_bihin", {}).get("data_range"), "raw"),
        },
    }
    if raw.get("psa_tier_status"):
        out["psa_tier_status"] = raw["psa_tier_status"]

    Path(a.out).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    json.loads(Path(a.out).read_text(encoding="utf-8"))  # validate
    print(f"wrote {a.out} ({len(cards_out)} cards, {now:%Y-%m-%d %H:%M} JST, {now:%A})")

    for c in cards_out:  # thin-supply flags
        for gk, g in c.get("grades", {}).items():
            n = len(g.get("top20_cheapest_listings") or [])
            if g.get("error"):
                warnings.append(f"{c['card_name_ja'][:24]} {gk}: {g['error']}")
            elif n < 5:
                warnings.append(f"{c['card_name_ja'][:24]} {gk}: only {n} live listing(s)")
    if warnings:
        print("\nWARNINGS:"); [print(" -", w) for w in warnings]

    if prev:
        print("\nCHANGES vs previous run:")
        pmap = {c.get("url"): c for c in prev.get("cards", [])}
        for c in cards_out:
            p = pmap.get(c["url"])
            if not p:
                print(f" - {c['card_name_ja'][:24]}: new card"); continue
            bits = []
            fa, fb = p.get("favorite_count"), c.get("favorite_count")
            if fa and fb and fa != fb:
                bits.append(f"fav {fa}->{fb} ({(fb - fa) / fa:+.1%})")
            for gk in ("psa10", "raw_a_grade"):
                la = p.get("grades", {}).get(gk, {}).get("lowest_price")
                lb = c.get("grades", {}).get(gk, {}).get("lowest_price")
                if la and lb and la != lb:
                    bits.append(f"{gk} low {la}->{lb} ({(lb - la) / la:+.1%})")
                elif not la and lb:
                    bits.append(f"{gk}: first listings appeared (low {lb})")
            pa, pb = p.get("psa10_population"), c.get("psa10_population")
            if isinstance(pa, int) and isinstance(pb, int) and pa != pb:
                bits.append(f"pop {pa}->{pb} (+{pb - pa})")
            elif not isinstance(pa, int) and isinstance(pb, int):
                bits.append(f"population first appeared: {pb}")
            print(f" - {c['card_name_ja'][:24]}: " + ("; ".join(bits) if bits else "no notable change"))
        for k in ("psa10", "raw_bihin"):
            a0 = pidx.get(k, {}).get("latest_index_value_jpy"); b0 = out["pokeca_chart_index"][k].get("latest_index_value_jpy")
            if a0 and b0:
                print(f" - index {k}: {a0}->{b0} ({(b0 - a0) / a0:+.1%}), volume {out['pokeca_chart_index'][k].get('volume_trend')}")


if __name__ == "__main__":
    sys.exit(main())

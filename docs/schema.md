# Snapshot JSON schema

Every file in `data/snapshots/` is one collection run. The app only ever computes
derived numbers from raw inputs at render time — nothing derived should be
hand-written into this JSON. If a number here can be calculated from other fields
in this same file, it's a bug to store it separately.

## Raw fields (from the price-check run — required)

This is exactly what the `pokemon-card-price-check` skill produces; the app works
with just this much, and shows every card honestly as "tiers not yet established"
when nothing more is added.

```jsonc
{
  "collected_at_jst": "2026-09-15T16:26:00+09:00",
  "notes": "free-text methodology notes, shown in a collapsible section",
  "cards": [
    {
      "card_name_ja": "...",
      "url": "https://snkrdunk.com/apparels/...",
      "favorite_count": 780,
      "psa10_population": 10846,
      "psa10_gem_rate_pct": 88.0,
      "grades": {
        "psa10": {
          "lowest_price": 27000,
          "threshold_115pct_of_lowest": 31050,
          "top20_cheapest_listings": [27000, 29000, ...],
          "listings_within_15pct_of_lowest": [27000, 29000, 29800],
          "count_within_15pct": 3,
          "count_excluded_over_15pct": 17,
          "recent_completed_sales": [{ "price": 36300, "when": "2026/09/06" }, ...]
        },
        "raw_a_grade": { "...same shape..." }
      }
    }
  ],
  "pokeca_chart_index": {
    "psa10": { "latest_index_value_jpy": 119889, "day_change_pct": -1.6, "month_change_pct": -21.0, "year_change_pct": 26.4, "volume_trend": "flat" },
    "raw_bihin": { "...same shape..." }
  }
}
```

## Analysis overlay (optional — adds verdicts, gauges, tiers, banners)

This is the judgment layer from an actual evaluation (e.g. running the
`pokemon-tcg-card-evaluation` skill or a full analysis conversation), added on top
of the raw run above before pushing. **Only put in inputs and human reasoning here
— never a number the app can calculate itself** (off-peak %, DIY expected cost,
gauge positions, tier zone math — all computed client-side from these inputs, see
`assets/app.js`).

```jsonc
{
  // ...all the raw fields above, plus:

  "market_context": {                     // optional — becomes the strip's 4th cell
    "catalyst": "Release day tomorrow — Sept 16",
    "psa_tier_status": { "paused": true, "note": "weekly check is Mondays only" }
  },

  "banners": [                            // optional — human-written prose, the
    {                                      // highest-value, least-automatable part
      "type": "correction",                // "info" | "warning" | "correction"
      "title": "VMAX CSR's repricing is now fully confirmed.",
      "body": "20 real sales trace a clean break to ¥28,500–32,500..."
    }
  ],

  "cards": [
    {
      // ...all the raw fields above, plus:
      "analysis": {
        "representative_price": 29000,     // only if it should override lowest_price
        "price_source": "sales_confirmed", // "sales_confirmed" | "ask_depth" | "ask_unconfirmed"

        "peak": {                          // omit entirely if no real price history exists yet
          "price": 47000,
          "when": "August 2026",
          "source": "pokeca-chart per-card chart, Sept 12"
        },

        "tiers": {                         // omit entirely if not yet established —
          "definitely_buy": 28000,         // never guess plausible-looking numbers
          "buy_upper": 33000,
          "ceiling": 40000
          // watch = buy_upper..ceiling; the gauge splits that band into two visual
          // shades at its midpoint automatically, it's not a 4th number
        },

        "verdict": {
          "tag": "buy",                    // "definitely_buy" | "buy" | "watch" | "dont_buy" | "defer"
          "label": "Buy — at Definitely-buy, but weak demand",
          "reasoning": "The break to a lower price is now confirmed by a full sales window..."
        },

        "grading_fee_jpy": 9980,           // omit -> DIY-vs-slab economics section is skipped
        "shipping_insurance_jpy": 2000,    // optional, defaults to 2000 if grading_fee_jpy is set

        "raw_tiers": {                     // optional, only used in the DIY table's
          "definitely_buy": 48000,         // "buying raw anyway" sub-section
          "buy_upper": 55000,
          "ceiling": 65000
        }
      }
    }
  ]
}
```

## What the app computes for you (never hand-write these)

- **Off-peak %** — `(peak.price - representative_price) / peak.price`
- **Price delta since last snapshot** — diffed against the previous snapshot's
  representative price for the same card `url`
- **DIY expected cost & delta** — `(raw_lowest + grading_fee + shipping) / gem_rate`,
  compared against the representative PSA10 price
- **Gauge zone boundaries & scale** — `scale_max = round(peak * 1.08, -3)`, with the
  watch band split into two visual shades at its midpoint
- **Favorite-count / depth trend arrows** — diffed against the previous snapshot
- **Auto-detected flags** (small "Automatically detected" banner) — depth dropping
  >30% relative, favorite count moving >5%, or the representative price crossing a
  tier boundary since the last snapshot. These are factual diffs, not judgment —
  the human-written `banners` above are where the actual narrative/reasoning goes.

## Design principle

Every number the app shows should be traceable to why it's trustworthy. A card
with no `analysis` block still renders honestly — raw price, depth, sales, and
population, labeled "tiers not yet established" — rather than a guessed verdict.
Add the `analysis` overlay only once you've actually done the depth-check →
sales-check → peak-check work; false precision is worse than an honest gap.

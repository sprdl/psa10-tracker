# Snapshot output shape (produced by assemble.py)

Part of the full price check (`pricecheck/FULL-CHECK.md`, which holds the shared rules: credentials, publishing, the chat message). Read this file only when you need the snapshot JSON layout.

```json
{
  "collected_at_jst": "2026-09-24T08:10:00+09:00",
  "notes": "methodology: 販売中のみ / 安い順, top 20, 15% cutoff, ...",
  "cards": [{
    "card_name_ja": "...", "url": "...", "image_url": "...",
    "favorite_count": 3921,
    "psa10_population": 80321, "psa10_gem_rate_pct": 86.9,
    "grades": {
      "psa10": {
        "lowest_price": 0, "threshold_115pct_of_lowest": 0,
        "top20_cheapest_listings": [], "listings_within_15pct_of_lowest": [],
        "count_within_15pct": 0, "count_excluded_over_15pct": 0,
        "recent_completed_sales": [{ "price": 66500, "when": "49分前" }]
      },
      "raw_a_grade": { "...same shape..." }
    }
  }],
  "pokeca_chart_index": {
    "psa10": { "latest_index_value_jpy": 0, "day_change_jpy": 0, "day_change_pct": 0,
               "month_change_jpy": 0, "month_change_pct": 0, "year_change_jpy": 0, "year_change_pct": 0,
               "data_range": "...", "volume_trend": "flat", "volume_note": "..." },
    "raw_bihin": { "...same shape..." }
  },
  "psa_tier_status": { "...Mondays only..." }
}
```

Conventions: a grade with no live listings keeps its object with an `"error"` (so diffs show exactly when activity starts). Zero completed sales in the period is a valid result: an empty `recent_completed_sales` plus a `sales_note`, not an error. A failed population check gives `population_error`; a skipped weekly check gives `population_note`. `image_url` is omitted when unknown. `psa_tier_status` is omitted except on Mondays. The pokeca index `data_range` only advances once per JST day, so repeated same-day runs legitimately match (assemble.py notes this when `--prev` is given). All times are JST.

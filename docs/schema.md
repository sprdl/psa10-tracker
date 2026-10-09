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
      "image_url": "https://.../card-photo.jpg",  // optional — shown as a small thumbnail on the card
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

`image_url` can point at any directly-loadable image — a photo you host yourself, a
SNKRDUNK listing photo's URL, whatever's convenient. It's entirely optional and
per-card: a missing or broken URL just means no thumbnail for that card, nothing
else changes.

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

        "sell_tiers": {                    // optional, only used for cards you own (data/holdings.json);
          "reassess_below": 62000,         // optional: below this, rethink holding (the "Reassess" zone)
          "take_profit_from": 85000,       // from here on: start taking profit
          "sell_from": 105000              // from here on: sell. reassess_below <= take_profit_from <= sell_from.
          // below take_profit_from (and above reassess_below) is "Hold"
        },
        "sell_verdict": {                  // optional, the written reasoning behind the sell tiers
          "tag": "hold",                   // "hold" | "take_profit" | "sell" | "reassess"
          "label": "Hold for the peak",
          "reasoning": "..."               // `written` (date) is added by apply_analysis.py
        },

        "grading_fee_jpy": 9980,           // PSA Japan Standard; optional, the DIY tab uses 9980 when omitted
        "shipping_insurance_jpy": 2450,    // optional, defaults to 2450 (PSA insurance & shipping ¥1,900 + handling ¥550); a legacy 2000 is read as 2450

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

### Owned cards: the sell view

A card that appears in `data/holdings.json` gets a different card page and side panel: its buy tiers, tier
check, limit and Mercari rows are left out (the written buy analysis stays, folded), and the gauge shows what
you paid, the break-even price after SNKRDUNK's selling costs, your sell target and the peak, coloured by
`sell_tiers`. Its verdict chip is Sell / Take profit / Reassess / Near peak / Rich ask / Hold: the tiers, your
sell target, the peak and the ask-vs-sales check all feed it. Without `sell_tiers` the card still shows its
position, break-even and target, plus a note that the sell tiers aren't written yet. `apply_analysis.py`
accepts `sell_tiers` / `sell_verdict` alone (an owned card needs no new buy tiers to get them).

## What the app computes for you (never hand-write these)

- **Off-peak %** — `(peak.price - representative_price) / peak.price`
- **Price delta since last snapshot** — diffed against the previous snapshot's
  representative price for the same card `url`
- **Raw A-rank price** (`rawPrice` in `assets/app.js`, `scripts/raw_price.py`, since 2026-10-08) — the median of
  the last 5 one-copy A-rank sales from the past 30 days, never below the lowest A-rank ask; fewer than 3 such
  sales: the lowest ask. The cheapest raw listing is often a copy that won't grade and doesn't sell. Used for the
  DIY cost, the grading calculator, raw pulls, the raw figure under owned cards and raw-only cards.
- **DIY expected cost & delta** — `(raw A-rank price + grading_fee + shipping) / gem_rate`,
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

## Price history (computed, not stored)

Every card's expanded detail shows a long-run price chart built by reading
`representative_price` (or `lowest_price` as a fallback) out of every snapshot file
on file, matched by card `url` — not a separate field anywhere. Nothing needs to
change about how you add snapshots; the chart just gets one more data point each
time. To keep the worst-case page load bounded as the archive grows over months of
2x/day checks, the app only fetches the most recent `HISTORY_MAX_SNAPSHOTS` (200 as
of writing, in `assets/app.js`) snapshot files for this — plenty of runway for a
multi-month trend without ever downloading years of history on every card expand.

## Overview columns: Price and Limit

**Price** is always the PSA10 price. **Limit** depends on the card: for a card you watch it shows your limit with the
distance to the lowest ask underneath. For a card you own it shows the PSA10 price against your cost basis
(`boughtGap` in `assets/app.js`):
- bought as a **PSA10**: the price you paid ("paid ¥X" underneath);
- bought **raw**: the DIY cost computed with the raw price you paid instead of today's lowest raw listing,
  (raw paid + the holding's grading & shipping, ¥12,430 by default) ÷ gem rate ("DIY ¥X" underneath). A holding's
  own `gem_rate_pct` overrides the card's population gem rate; without any gem rate the fees are added undivided.
Several copies average their bases. Hovering shows the sum. The collection badge, the Limit sort, the side panel's
first tile and the card page's "PSA10 vs your DIY cost" use the same comparison; the other card-page numbers (worth
now, after selling costs, break-even) are still based on the PSA10 price.

## Sold items: `"sold"` in `data/holdings.json`

The site's **Sold it** links (single cards, the owned card page, unopened sealed products) open the `sold.yml`
form; `scripts/log_purchase.py` (label `sold`) moves the item out of `holdings` / `sealed` and adds a record:
`{"id": "x123", "kind": "single|sealed", "name", "card_url"|"url", "qty" (sealed), "cost_jpy", "bought",
"sold_price_jpy", "sold_date", "fees_jpy", "fees_estimated", "notes", "orig": <the original entry>}`. Fees default
to the cost model (9.5% + ¥200/¥300 + ¥1,000 shipping) unless you typed the real amount. A sealed lot can be sold in
part (the rest keeps its quantity and its share of the cost). A product with pulls is opened and can't be sold as
sealed. Profit = sold for − fees − cost. **Undo sale** (remove-purchase form with the `x…` id) puts the original
back. The Holdings page lists sales with a yearly summary; the value-over-time chart keeps sold items in its
history and, from the sale date on, counts the money received (so its result is total profit, unrealized plus
realized, while the header's +/− only covers what you still own).

## Raw singles on the Holdings page

A single bought raw shows three figures instead of one value: the **raw A-rank price** (the Overview's rule: median of the
last 5 sales in 30 days, never below the lowest ask) with its % against the price you paid; the **PSA10 lowest ask**
with its % against **your DIY cost**; and **your DIY cost** itself, (price paid + grading & shipping) ÷ gem rate. Slabs
keep one value with the profit against the purchase price. The row also shows when it was sent to PSA and when it is due
back (the "Grading info" form); the "expected value once graded" text only remains on pulls. The header totals still
count a raw single at its DIY cost (`rawHoldingCols`, `rawCopyBasis` in `assets/app.js`).

## Owned raw cards on the card page and the side panel

For a card you hold raw, the position (gain, result after selling costs, break-even, the sell gauge's marker, the
Upside tab) is measured against your **PSA10 DIY cost with the price you paid**, (price paid + grading & shipping) ÷
gem rate, the same number as the Overview's "DIY ¥X". "You paid for the card" shows the purchase price alone, with the
all-in figure including grading next to it. Slabs are measured against the price paid, as before (`ownedOf().basis`).

## Sorting by the Limit column, and the price log

Sorting by Limit keeps two groups apart: cards you watch first (closest to your limit first, then cards without a
limit), then cards you own (biggest gain first). Reversing flips the order inside each group, not the groups.
`data/portfolio_history.json` only receives prices actually read that day (a failed read's carried-over last-good
price stays out); a second run on the same day adds to that day's entry instead of replacing it.

## How Holdings counts a single, a raw card and an unpriced product

On the Holdings page (header totals, singles summary, value chart) a single is **worth what the card is today in the form
you hold it**: a slab at today's PSA10 price, a raw card (`condition: raw_to_grade`) at the raw A-rank price (the
Overview's rule: median of the last 5 sales in 30 days, never below the lowest ask). The DIY cost is not a value; it is
only shown next to the raw A-rank and PSA10 prices of a raw single. **Total cost / spent** counts what you paid for each
card, **without grading and shipping** (`holdingPaid`); the grading fee stays in `holdingCost`, which the budget planner and
the sold records use. P&L = value − paid. A sealed product with no price yet (e.g. not released) counts at what you
paid, in the header, the Sealed section and the chart. The Sold form's suggested price is the PSA10 price for a slab and
the raw A-rank price for a raw copy. "Remove card" is disabled for a card you hold or pulled, on the page and in
`scripts/remove_card.py`.

## Collection tiles for cards you own

The same figures as the Holdings page. A card bought as a PSA10: the PSA10 price with the gain against the price paid (badge
"+20.6% vs paid"). A card held only raw: the PSA10 price with the badge "+39.0% vs DIY" (PSA10 ask against your DIY cost) and,
under the price, "Raw A ¥78.5k +4.7% · DIY ¥100.7k" (the raw A-rank price against what you paid, and your DIY cost). Hovering
the line spells out the sums (`rawOnlyStats` in `assets/app.js`).

## Holdings values: lowest ask or after selling costs

A switch at the top of the Holdings page (saved in this browser) shows every value either at the lowest ask or
after SNKRDUNK's selling costs: 9.5% fee, ¥200 fixed fee (¥300 from ¥30,000) and ¥1,000 shipping, each single, pull
and unopened sealed item counted as one sale (`sellNet` in `assets/app.js`). It changes the header totals, the
singles list, the sealed section and the value-over-time chart together; spent amounts never change.

## `data/portfolio_history.json` — daily prices of bought items that aren't tracked cards

`{"points": [{"d": "2026-10-07", "p": {"<snkrdunk id>": 7600}}]}`, one entry per day, appended by
`scripts/holdings_prices.py` during the full check (same readings as `holdings_prices.json`; a later run the
same day replaces that day; at most 800 days). The Holdings page's "Value over time" chart back-fills singles and
pulls of tracked cards from `history.json` and uses this file for sealed products and untracked cards from their
first reading on (before that they are valued at cost). The chart's last point equals the header's "Worth now".

## `data/sell_targets.json` — your sell targets

`{"targets": {"<card url>": {"price": 90000, "set": "<iso time>", "issue": 123}}}`, written by
`scripts/set_limit.py` (label `set-sell-target`, same Action and form flow as limits). Only used for cards
in `holdings.json`: an owned card's Verdict column shows **Sell** when the price reaches its target,
**Near peak** within 5% of the recorded peak, **Rich ask** when the lowest ask is 8%+ above recent sales,
otherwise **Hold**.

## `data/holdings.json` — cards you've actually bought

Separate from the snapshot archive, this file is the portfolio layer: what you
paid, when, and for what — pure facts, no judgment, matching the same
raw-vs-computed split as everything else. The app matches each holding to the
current snapshot by `card_url` and computes current value / unrealized P&L itself;
never hand-write those numbers here.

```jsonc
{
  "holdings": [
    {
      "id": "p12",                                       // "p" + the GitHub issue number that logged it;
                                                           // used by the site's Remove link
      "card_url": "https://snkrdunk.com/apparels/...",  // must match a tracked card's `url`
      "card_name_ja": "...",                             // denormalized label — kept even if
                                                           // the card later drops out of tracking
      "image_url": "https://.../card-photo.jpg",         // optional, used only if card_url stops matching
      "condition": "psa10",                              // "psa10" (bought already-slabbed) or
                                                           // "raw_to_grade" (bought raw, paying to grade it)
      "purchase_price_jpy": 65000,
      "purchase_date": "2026-09-20",
      "grading_fee_jpy": 9980,                            // only used if condition is raw_to_grade
      "shipping_insurance_jpy": 2450,                     // optional, defaults to 2450 (PSA insurance & shipping ¥1,900 + handling ¥550); a legacy 2000 is read as 2450
      "notes": "optional free text"
    }
  ]
}
```

Sealed product (boxes, sets, packs bought at MSRP) sits next to it under `"sealed"`, logged with the
site's **+ Add sealed product** / **+ Add pull** forms (labels `sealed` / `pull`, same Action):

```json
"sealed": [
  {"id": "s51", "kind": "box", "url": "https://snkrdunk.com/apparels/881421", "name": "",
   "snkrdunk_name": "ポケモンカードゲームMEGA 拡張パック「30th CELEBRATION」ボックス",
   "image": "https://cdn.snkrdunk.com/upload_bg_removed/….webp?size=l", "set_code": "M6a", "qty": 1,
   "price_jpy": 11000, "date": "2026-10-03", "where": "Pokémon Center lottery",
   "pulls": [{"id": "u52", "card_url": "https://snkrdunk.com/apparels/896992", "card_name_ja": "…",
              "image_url": "…", "status": "raw|grading|psa10|graded_other", "value_jpy": 15000, "date": "2026-10-04"}]}
]
```
`kind` is box / set / pack / other. `snkrdunk_name` and `image` are read from the product's SNKRDUNK
page by the next price check (`scripts/sealed_info.py`, FULL-CHECK step 8h); the Action never opens SNKRDUNK. A pull of a tracked card is valued from the snapshot (raw A-rank
lowest ask, or the PSA10 price once `status` is psa10); `value_jpy` (optional) covers untracked cards.
Raw copies (a pull with status `raw` / `grading`, or a holding with `condition: raw_to_grade`) can also carry
`"sent": "2026-10-01"` (date sent to PSA), `"tier": "standard|priority|express"` and `"gem_rate_pct": 60` (your own
chance of a PSA10 for this copy, overriding the card's population gem rate). They are set with the site's
**Grading info** link (issue form `grading-info.yml`, label `grading-info`, handled by `scripts/log_purchase.py`;
blank fields remove the value). The site uses them for the "Grade it?" verdict, the expected result and the
return date (sent + 100 / 80 / 25 business days for Standard / Priority / Express). A non-10 is valued at the
raw A-rank price and everything is net of selling costs; see `gradeCalc` in `assets/app.js`.

Prices of what isn't tracked come from `data/holdings_prices.json` (written by the full check, never by
hand; `scripts/holdings_prices.py`): `{"updated": …, "prices": {"<snkrdunk id>": {"kind": "card|sealed",
"price": 7600, "date": "2026-10-07"}}}`, only the latest reading per id. `card` = raw A-rank price (rule above; `ask` and `sales` stored too) of a
bought raw card or a raw/at-PSA pull that isn't a tracked card; `sealed` = lowest ask of a product with no
pull logged (× `qty` on the site). Logging a pull opens the product, so its price is removed by the next
full check. Quick checks never read these.

Removing uses the same Remove form with an `s…` (product and its pulls) or `u…` (one pull) id.

Normally purchases are logged from the site (✓ Bought it → GitHub issue → `scripts/log_purchase.py` in Actions; see README). For bulk entry, add holdings with `python3 scripts/add_holding.py` (same clipboard-or-file-argument
pattern as `add_snapshot.py`) rather than hand-editing the file, so the commit
message and validation stay consistent. The "Your holdings" section on the site is
hidden entirely whenever `data/holdings.json` has no entries.

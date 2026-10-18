---
name: "pokemon-tcg-card-evaluation"
description: "Evaluate a Japanese PSA10 Pokemon card for the PSA10 tracker: buy tiers (definitely buy / buy / ceiling) with timing and risk for cards being watched, and sell tiers (take profit / sell) for cards already owned, plus a JSON analysis block applied to the tracker web app."
---

# Pokémon TCG (JP) Card Evaluation Method

A repeatable process for evaluating any PSA10 Japanese Pokémon card as a display-plus-investment piece. Built from the Umbreon ex SAR / Pikachu VMAX CSR / Pikachu ex SAR analysis, September 2026, validated on Gengar VMAX SA (SGG 020/019), and extended in October 2026 with sell tiers for owned cards.

**Two kinds of evaluation:**
- **Buy evaluation** (every tracked card): buy tiers, buy verdict, predictions. Steps 1–8.
- **Sell evaluation** (only cards the user owns, i.e. listed in the tracker's `data/holdings.json`): sell tiers and a sell verdict. Same research (steps 1–5), then step 7's sell part. A full check asks for it in its `SELL TIERS NOW` block; it can run on its own without touching the buy tiers.

Check ownership first. With the computer linked, one `device_bash` call:
```
R=$(ls -d "$HOME"/mnt/*/psa10-tracker "$HOME"/mnt/psa10-tracker 2>/dev/null | head -1); cd "$R" && git pull --ff-only -q; python3 -c "import json;[print(h['id'],h['card_url'],h['condition'],h['purchase_price_jpy'],h.get('grading_fee_jpy',0)+h.get('shipping_insurance_jpy',0),h['purchase_date']) for h in json.load(open('data/holdings.json'))['holdings']]"
```
A copy with condition `graded_other` came back below a 10 and isn't a PSA10 position: it needs no sell tiers. For break-even, `eval_context.py` prints the cost basis the site uses (grading counts once a copy is sent). An owned card gets the sell evaluation; do the buy part too only when the price check also asks for it (EVALUATE NOW / review due / verdict refresh), or the user wants to buy another copy.

**Inside a price check (EVALUATE NOW, SELL TIERS NOW, REVIEW DUE NOW).** The price check calls this skill for new cards (added or restored in that same run), cards whose PSA10 market just formed, and cards due for review. It must finish in that run: don't stop to ask whether to evaluate, and don't hand it back as an optional next step. Start with one `device_bash` call:
```
R=$(ls -d "$HOME"/mnt/*/psa10-tracker "$HOME"/mnt/psa10-tracker 2>/dev/null | head -1); cd "$R" && python3 scripts/eval_context.py <snkrdunk_id>
```
It prints what the run already collected and what the repo knows: lowest asks, depth, one-copy sales and sales per day for PSA10 and raw A, the raw A-rank price (the rule below), population and gem rate, DIY cost, ownership with the cost basis and break-even, slab premium, hype exposure, age and age-curve drift, our tracked price range, the current analysis, the My-tier index (7- and 30-day change, correction rule, rally flag), the pokeca-chart index, the event window, and limit-odds for the current tiers. Add `--odds <price> <price>…` to get 30/90-day odds for candidate tier prices. Use it for steps 2–4 and the reachability check instead of reading those pages again. Only fetch what it can't give: the peak-month median and longer price history (SNKRDUNK 売買履歴, pokeca-chart), set and release details, and, for a card a quick check just added, its listing depth (`pricecheck/scripts/snkrdunk_listings.js` on the listings page) and its PSA pop page (FULL-CHECK step 1c). Then go through steps 1–8 as usual; step 8 applies the result and takes the card off the evaluation queue.

## The 8 steps

### 1. Identify the card precisely
Full name, set code + card number, set name (Japanese + English), rarity, whether it is full art, release date, illustrator. Precision here determines whether searches return the right card — Pokémon has many same-name/different-print cards (e.g. two different "Pikachu ex SAR" prints exist across different sets).

### 2. Pull current market data
For PSA10 and raw/A-rank, from Japanese sources — never rely on international (TCGPlayer/eBay) pricing for a Japanese-market card. Read SNKRDUNK and pokeca-chart in the user's browser only (no headless access, no API calls); the tracker's latest snapshot already holds most of it, so start there (`scripts/eval_context.py <id>` prints it).
- **Current PSA10 price** — prefer actual recent transaction prints (SNKRDUNK 売買履歴, 1枚 filter) over stated "averages," and flag any single print that looks like an outlier before using it
- **PSA10 population + gem rate** — PSA's own pop report (psacard.com/pop, signed in; the tracker reads it every full check and `eval_context.py` prints it with its source). Gem rate = PSA 10s ÷ total graded on the card's row. altema is no longer used (dropped 2026-10-12).
- **Raw/A-rank price** and its 1-month trend — SNKRDUNK A-rank listings and sales, card shop buyback trackers, カードラッシュ. The raw A-rank price follows the tracker's rule (since 2026-10-08): the **median of the last 5 one-copy A-rank sales from the past 30 days, never below the lowest ask**; with fewer than 3 sales in 30 days, the lowest ask. The cheapest raw listing is often a copy that won't grade (bad centering) and doesn't sell, while PSA10-worthy copies sell higher (Mega Charizard X ex SAR on 2026-10-08: ask ¥72k, sales ¥75–80k). The card page's Raw A-rank tile shows this price (hover for the ask and the sales median); `scripts/raw_price.py` in the repo is the same rule in Python. Say which one it came from. Cross-check a buyback quote against actual recent A-rank *transaction* prints — a rising quote with no recent confirmed trade is a liquidity red flag, not confirmed price discovery
- **12-month price range and average** (or the longest window actually available — say plainly if you can only confirm a shorter window, e.g. 3 months, rather than presenting it as a full year)
- **Most recent peak price** and % drawdown from it — check specifically whether the peak lines up with a known hype event (see step 4). Use SNKRDUNK peak-month medians, which resist single-day spikes.
- **In-print vs. out-of-print (絶版) status**. Context only: on 2026-10-03 a test of the three Standard rotations in our data (2024/25/26) found no consistent price effect from a set leaving rotation/shelves (−22%, +5%, +12% vs the market over 6 months). Don't argue a buy or a hold from it.
- **DIY replacement cost** — what a PSA10 costs to make yourself: (raw A-rank price, as defined above, + ¥12,430) ÷ gem rate. ¥12,430 is PSA Japan's Standard service for one card, tax included (order screen, 2026-09-30): grading ¥9,980 + 保険・送料 (insurance & shipping) ¥1,900 + 事務手数料 (handling) ¥550. Standard caps the declared value (the PSA10 price) at ¥150,000 per card. From ¥150,000 to ¥250,000 use PSA Priority, ¥2,000 more (¥11,980 grading, ¥14,430 with shipping and handling, about 80 business days); above ¥250,000 only Express (¥29,980) applies, so say so. The site's DIY tab and `eval_context.py` pick the tier the same way. The site shows a **Self-grade** chip next to the verdict when the DIY cost is at least 15% under the PSA10 price (cards up to ¥250,000, not Defer); mention it when it applies. Re-check the fees if the evaluation is months later or PSA announces a change.
- **Selling cost** (for every breakeven, upside or sell statement) — SNKRDUNK's seller fee depends on member rank: Regular 9.5%, Bronze 9%, Silver 8.5%, Gold 8%, Platinum 7%. The rank follows the trading amount in the last 90 days (Bronze ¥45k+, Silver ¥90k+, Gold ¥225k+, Platinum ¥900k+), so assume Regular. Add the ¥200 (under ¥30k) or ¥300 transfer fee and the seller-paid shipping (about ¥1,000). Break-even sale price = (cost + transfer fee + ¥1,000) ÷ 0.905, i.e. roughly +11–13% on a ¥40–150k card, more on cheaper ones. The owned card page shows this break-even line. "Cost" is the app's cost basis: for a slab, the price paid; for a card bought **raw to grade**, the DIY cost with the price paid, (paid + grading & shipping, ¥12,430 by default) ÷ gem rate, not the plain sum (docs/schema.md, "Owned raw cards"). `eval_context.py` prints both the basis and the break-even.

### 3. Stress-test the population number (the PSA backlog check)
Population counts only reflect what's already graded and returned — not true supply. Check the card's **release date against current PSA turnaround time** (Standard tier ~100 business days as of late 2026; the Value tier is paused). Any card released within that window has an artificially low, unreliable population — treat its "scarcity" as unproven and expect the population (and likely the price) to shift once the backlog clears. Cards older than ~6–12 months have mature, trustworthy populations. Note the gem rate too (PSA10 acquisition rate) — a very high gem rate means scarcity comes from total copies pulled, not from grading difficulty. Summer submissions are expected back Nov 2026–Feb 2027: young, in-print cards can dip toward replacement cost when they land.

### 4. Map the macro context
- **Overall PSA10 market index trend** (pokeca-chart 指数チャート) — day/month/year change, and whether the market is in an active correction, bottoming, or rallying right now
- **Anniversary/event calendar** — is a hype-driving event (anniversary, new set, regulation news) approaching or just passed? Check whether unrelated cards/sets peaked in the same month — that pattern signals a single speculative narrative rather than card-specific fundamentals. If a card's own drawdown is *steeper* than the broad index's, say so explicitly — it means the card ran up harder than the market or is a bigger target for profit-taking. The tracker's `data/events.json` lists dated releases.
- **My-tier index** (the tracker's own equal-weighted index of 22 modern SAR/alt-art PSA10s, the tier actually being bought) — its 30-day change feeds the correction rule and its 7-day change the rally flag in step 7. `eval_context.py` prints both; without it, one `device_bash` call reads the 30-day change:
  ```
  R=$(ls -d "$HOME"/mnt/*/psa10-tracker "$HOME"/mnt/psa10-tracker 2>/dev/null | head -1); cd "$R" && git pull --ff-only -q; python3 -c "import json,datetime as D;s=json.load(open('data/custom_index.json'))['series'];l=s[-1];t=(D.date.fromisoformat(l['d'])-D.timedelta(30)).isoformat();o=[e for e in s if e['d']<=t];print(l['d'],l['level'],'30d:',f\"{(l['level']/o[-1]['level']-1)*100:+.1f}%\" if o else 'n/a (under 30 days of data)')"
  ```
- **Upcoming events in the next ~3 days** — a major set or anniversary product release, a Pokémon Presents / product announcement, a PSA service or price change. Needed for the event rule in step 7 (confirmed on our own snapshots on 2026-10-02: keep it).
- **Historical analog** — for anniversary-driven moves, the prior cycle (e.g. 25th anniversary → 30th anniversary) is a useful calibration tool: typical peak-to-trough give-back and typical time-to-floor
- **Card age** — new cards keep falling against the market for months after release. Backtest on 125 modern PSA10s, 2022–26 (2026-10-02): about −20% a month in months 0–3, −8.5% a month in months 3–6, −2% a month in months 6–9, then flat. Build that drift into tiers and timing for any card under 9 months old.
- **Hype exposure** (the card page's panel, `data/hype.json`): how much of a hype run the card still carries (12-month change vs the market) and how actively it trades, ranked against ~250 PSA10s. In every market fall since 2021, the most exposed cards fell hardest (about 11 points worse than the least exposed over 3 months in falling stretches, 13 of 14 times) and rose more in rallies (about 7 points). It describes how hard a card swings *with* the market. Use it for downside risk (buy) and for how urgent taking profit is (sell); never as a buy or sell signal on its own.

### 5. Assess demand and supply drivers
- Character popularity and cultural staying power (not just current hype)
- Illustrator reputation/fanbase
- Anniversary or media tie-ins that could help or hurt (a new competing card in the same character/theme can cannibalize as easily as it can halo-lift) — explicitly flag if you did not check for a specific competing/reprint risk rather than silently assuming none exists
- Genuine scarcity (out-of-print, low real population, e.g. "1 pull per N boxes" of a niche product) vs. manufactured/temporary scarcity (backlog, limited early data)
- Competitive legality — has the card rotated out of standard play? If so, its value is pure collector/display demand with no tournament-utility floor

### 6. Weigh against personal goals and constraints
- Display criteria: a **full-art** card of any rarity (AR, SAR, SR, CSR, CHR, SA, MA, MUR, UR, BWR and similar: the illustration covers the whole card), no regular-frame commons/rares or RR ex cards with a framed picture, no vintage, and an aesthetic fit with the rest of the collection. The rarity code itself doesn't matter (changed 2026-10-03). If you can't tell from the sources, look at the card's own picture. Say plainly when a card isn't full art: it doesn't fit the collection, whatever its price.
- Investment floor (breakeven-or-better over the stated hold period)
- Budget: about ¥250,000 for singles including grading (raised from ¥200,000 on 2026-10-10; sealed product doesn't count). The singles logged in `data/holdings.json` already cost more than that (¥278,500 on 2026-10-10), so treat any new buy as outside the budget unless the user says otherwise, and say so. Also say how this card competes against other targets for the same yen, and call out explicitly if it is meaningfully more expensive or volatile than the cards already tracked. A card whose PSA10 is above ¥150,000 can't go through PSA Standard (declared-value cap): it needs Priority (¥2,000 more) up to ¥250,000 and Express above that, which matters for the raw-to-grade route.
- Emotional priority (a genuine "grail" can justify paying up vs. optimizing price to the yen). For sell tiers the user asked to treat every owned card the same, grails included: set honest tiers; the user decides.

### 7. Output the decision in two parts

**Part A — the prose decision, in a consistent format.**

*Buy part* (watched cards, or when a buy evaluation is asked for):
- **Don't-buy ceiling** — the level above which you're chasing a bubble
- **Watch closely** — current-ish range, worth monitoring, not yet a buy
- **Buy** — a fair entry
- **Definitely buy** — a genuine discount, backed by the 12-month average/range
- **Timing window** — when to expect these levels, not just what price
- **Probability estimate** — rough odds of reaching each tier in a stated timeframe, reasoned from the trend, not guessed
- **Downside risk if bought today** — chance and magnitude of a further drop, and what would drive it (hype exposure belongs here)
- Phrase buy advice as "wait for / buy a listing at ≤¥X", never "bid" or "offer". SNKRDUNK is not a bidding platform: sellers set fixed prices that generally aren't negotiated.

*Sell part* (owned cards only): two lines, no stop-loss line (the user chose this on 2026-10-07):
- **Hold** — below Take profit. Say what the card nets after selling costs at today's price vs the user's cost basis (for a raw card, the DIY cost with the price paid, as in step 2).
- **Take profit from ¥X** — where selling becomes attractive: clearly above the user's break-even after fees, and rich against the card's own pre-hype level.
- **Sell from ¥Y** — bubble territory, where holding on is mostly a bet on the bubble continuing.
- **Timing and odds** — rough odds of a listing reaching each line by a stated date, and what would get it there (market rally, event) or stop it.
- **Market regime** — whether the market is rising or rolling over, and the card's hype exposure: a high-exposure card at Take profit while the market turns down is the strongest case for selling.
- Phrase it as "list at ≥¥X / take profit from ¥X". SNKRDUNK sales are fixed-price listings; to sell you list at or a little under the lowest ask.

**Verdict guardrails (buy).** Apply them before choosing the buy verdict. The first two change only the verdict for today's price, never the tier numbers; the third changes nothing but the wording. Say so in the label/reasoning when one of them applies (the site applies the same rules to its computed call):
1. **Event rule.** Within about 3 days before a major release or announcement (step 4), don't call Buy. Use Watch with a label like "Watch: wait until after <event>", unless today's price is already at or below Definitely-buy. Why: on 2026-09-15, the day before the 30th-anniversary release, two Buy calls (Umbreon ex SAR, Gengar VMAX SA) were beaten by release-day dips of 5–12%.
2. **Correction rule.** If the My-tier index is down more than 10% over the last 30 days (step 4), the market is still falling: only call a Buy when today's price is at or below Definitely-buy (tag `definitely_buy`). Between Definitely-buy and `buy_upper`, use Watch, e.g. "Watch: in the Buy zone, but the market is still correcting". Buying partway down a correction is when a cheaper listing most often shows up within weeks.
3. **Rally flag.** If the My-tier index is up 10% or more over 7 days, it's a flag only: no tag changes. Mention it in the reasoning (limits and Buy lines set before a rally are less likely to fill soon; don't move tiers up just to chase it, since the odds model assumes no trend), and for an owned card near Take profit it is one more reason to act there.

**What the backtests say about setting buy tiers (2026-10-02, 125 modern PSA10s, 2022–26; project doc `claude/tiers-upside-backtest-2026-10-02.md`):**
- A card's price relative to its own 6–12-month median did **not** predict how it did against other cards once the measurement month was skipped. "Below its usual level" or "back at its pre-hype range" is context, not evidence of a bargain. Don't argue a Buy from it alone.
- What does hold up, so lean on it: how reachable a price is (the limit-odds model), the DIY replacement floor, the age curve above, and the market regime (guardrails).
- **Reachability check for every tier.** Before finalising, look up the limit-odds model's 30/90-day odds for Definitely-buy and Buy (`eval_context.py <id> --odds <DB> <Buy>`, or the card page's Tier check line). Definitely-buy should usually sit around 15–35% within 90 days; under 10% is a long shot. If you keep it anyway, say so in the reasoning. Buy should be reachable within weeks (roughly 40–60% within 30 days) unless the price is already there.
- **Upside statements** come from the card page's Upside tab (12- and 24-month ranges after SNKRDUNK fees). Its "Typical" assumes no market growth (the typical outcome is today's price, so the typical result is minus the selling cost); the italic figure shows the 2022–26 market as it was. The market part dominates: the mature market's 12-month moves ranged from −69% to +143% in 2022–26. Popular characters beat the rest by about +14% a year in the data, but not significantly. Mention it as a tilt, never as a reason on its own.

**What the data says about setting sell tiers (2026-10-07, 284 PSA10s, 2021–26, monthly; project docs `claude/sell-tiers-2026-10-07.md` and `claude/crash-resilience-study-2026-10-03.md`):**
- A card trading at **2× or more its own trailing-12-month median** had a median **−17% over the next 6 months**, and a **53%** chance of falling more than 10% (cards 0–70% above their median: median +19% to +29%, 19–26% chance of a >10% fall). These cases cluster at market tops (2023, 2026), so they mostly mark *market* peaks. Anchor **Sell from** around 2× the card's pre-hype level (its Q3–Q4 2025 range or trailing-12-month median), or the prior hype peak's monthly median if that's lower.
- Below that, rising cards kept rising on average (momentum). Being up a lot is not by itself a reason to sell, and against other cards being far above its own history predicted nothing (+2 points on average, worse in only 10 of 27 months). So set **Take profit** where the gain is worth locking in: at least ~15% above the user's break-even after fees, and roughly +50–70% over the pre-hype level, or about 85% of the prior peak-month median.
- When the market turns down, the cards that ran up most fall hardest (top third by run-up −11% to −22% vs the market in the 2023–24 and 2026 falls). So a high hype exposure plus a falling My-tier index is the strongest reason to act at Take profit rather than wait for Sell.
- Never set Take profit below the user's break-even after fees. If the card is under water, the verdict is Hold (with today's net result stated), whatever the market does.
- Check reachability: the Upside tab's 12-month range (Take profit usually between its Typical and Strong case) and the price history. A Sell line no listing has come near in the card's history is a long shot: say so.

How calls are scored (so verdicts and odds are set with it in mind): the tracker judges each buy verdict on the lowest PSA10 ask over the next 30 days. A dip counts only when it's below the card's own threshold (5%, or the card's normal swing between checks if larger, up to 10%) for two checks in a row. Every prediction (buy or sell) gets a Brier score on the Track record page.

**Cards with no PSA10 market yet** (no PSA10 listing, or one or two asks and no sales, typically a set released in the last few months, since slabs come back from PSA ~100 business days after submission): still evaluate them, because a new card on the tracker must end the price check with a written verdict. Use `verdict.tag` `"defer"` with no `tiers` and no `peak`, a label like "Defer — no PSA10 market yet", and reasoning that covers: when a PSA10 market is likely (release date vs PSA turnaround and the summer-submission wave), today's raw A-rank price and what a DIY slab would cost at the card's likely gem rate (say if the gem rate is a guess from similar cards), the age-curve drift for a young card, and what would make it worth tiers (e.g. "re-evaluate once 5+ PSA10 sales exist"). Add `raw_tiers` only if you can set them responsibly from raw sales (the user does buy raw copies to grade). Predictions are optional here and need a price and a deadline like any other. The price check gives a deferred card one fresh look a week (Mondays) once it has a PSA10 ask.

**Part B — a structured JSON block**, output immediately after Part A, so the evaluation can be applied straight to that card's `analysis` field in the PSA10 tracker web app's snapshot JSON (see the app's `docs/schema.md` for the authoritative field list). Send only the parts you evaluated: a sell-only evaluation sends just `sell_tiers` + `sell_verdict`; everything else stays. Shape:

```json
{
  "representative_price": 29000,
  "price_source": "sales_confirmed",
  "peak": {
    "price": 47000,
    "when": "August 2026",
    "source": "SNKRDUNK peak-month median, 1枚"
  },
  "tiers": {
    "definitely_buy": 28000,
    "buy_upper": 33000,
    "ceiling": 40000
  },
  "verdict": {
    "tag": "buy",
    "label": "Buy — at Definitely-buy, but weak demand",
    "reasoning": "One to three sentences synthesizing the timing window, probability estimate, and downside risk from Part A.",
    "predictions": [
      {"text": "Reaches Buy (≤¥33k) within 3 months", "p": 0.45, "type": "touch_below", "price": 33000, "by": "2026-12-25"},
      {"text": "Reaches Definitely-buy (¥28k) within 6 months", "p": 0.25, "type": "touch_below", "price": 28000, "by": "2027-03-25"}
    ]
  },
  "sell_tiers": {
    "take_profit_from": 42000,
    "sell_from": 52000
  },
  "sell_verdict": {
    "tag": "hold",
    "label": "Hold — ¥6k under break-even after fees",
    "reasoning": "One to three sentences: net result at today's price, what the lines are anchored on, odds and timing, and what would make you sell earlier.",
    "predictions": [
      {"text": "A listing at ≥¥42k (Take profit) by year-end", "p": 0.2, "type": "touch_above", "price": 42000, "by": "2026-12-31"}
    ]
  }
}
```

Field rules — get these right, since the app trusts this JSON as human judgment and never double-checks the math:

- **`representative_price`** — the single current price you'd actually transact at today, from step 2's data. Prefer a real recent completed sale over a listing/ask price; if lowest-listing and confirmed-sales disagree, use the sales price and say so via `price_source`.
- **`price_source`** — exactly one of `"sales_confirmed"` (recent real completed sales support this number), `"ask_depth"` (no recent sale, but multiple asks cluster here so it's a credible number), or `"ask_unconfirmed"` (thin data — one or two asks, no real sales to confirm).
- **`peak`** — from step 2's peak/drawdown research. Omit this whole object if there's no real price history yet for this card (e.g. it just released). Never fabricate a plausible-looking peak.
- **`tiers`** — exactly these three numbers, in JPY, mapped from Part A's Definitely-buy / Buy / (Watch-closely upper edge = ceiling) tiers, no other keys. Omit the whole `tiers` object if there isn't enough data to responsibly set boundaries yet — never guess plausible-looking numbers just to fill the field. "Watch" is implicitly `buy_upper`..`ceiling` in the app; do not add a fourth number for it.
- **`verdict.tag`** — which of `"definitely_buy"`, `"buy"`, `"watch"`, `"dont_buy"`, or `"defer"` applies to *today's* `representative_price` — not to the tiers in the abstract. Look at where `representative_price` actually falls relative to the tiers you just set, apply the guardrails, and say so plainly.
- **`verdict.reasoning`** — compress Part A's timing window, probability estimate, and downside risk into 1–3 sentences, with today's numbers. The site shows it folded under a computed "today" summary, dated, and the full check rewrites it once the ask moves 5% from the price it was written at, so don't pad it with figures that will date fast.
- **`sell_tiers`** (owned cards only) — exactly `take_profit_from` and `sell_from`, in JPY, `take_profit_from` < `sell_from`. Don't send `reassess_below`: the user chose two lines, and `apply_analysis.py` rejects it. Below `take_profit_from` the app shows Hold.
- **`sell_verdict.tag`** — `"hold"`, `"take_profit"` or `"sell"` for *today's* price against the sell tiers (`apply_analysis.py` rejects any other tag). The label says it in a few words; the reasoning compresses Part A's sell part (net result today, anchors, odds, regime) into 1–3 sentences. `apply_analysis.py` dates it, and the full check asks for a fresh one after 30 days.
- **`predictions`** (in `verdict` and `sell_verdict`) — every probability stated in Part A or the reasoning, as a checkable prediction. The Track record scores them against later prices (Brier score), so they must be honest and resolvable:
  - `p` is a probability between 0 and 1 (0.45, not 45). Use the midpoint for a range ("25–30%" → 0.275). It must be strictly between 0 and 1.
  - `type` is `touch_below` ("the lowest PSA10 ask reaches ≤ price", buy targets) or `touch_above` ("reaches ≥ price", sell targets). `price` is one number: the upper end of a target range for `touch_below` ("¥57–60k" → 60000), the lower end for `touch_above`.
  - `by` is a concrete date (YYYY-MM-DD): "within 3 months" from today → today + 3 months; "by year-end" → 12-31; "3–6 months" → the later date.
  - `text` is a short plain-English restatement of the prediction.
  - Only include odds that have a price and a deadline. Either give one or leave it out of `predictions`. Don't write a prediction that is already true today; the tracker marks those void.
  - Scoring uses the lowest PSA10 ask. Frame targets as "a listing at ≤¥X" / "≥¥X".
- Do **not** include any field the app computes itself (off-peak %, gauge positions, price deltas, break-even, net after fees, the raw A-rank price) — only raw inputs and judgment calls belong here. See `docs/schema.md`'s "What the app computes for you" section if unsure.
- If step 2's raw-A-rank research supports a DIY-vs-slab comparison, also include `grading_fee_jpy` (9980 for PSA Standard, 11980 for Priority; the app picks the tier from the PSA10 price when it's 9980 or omitted), `shipping_insurance_jpy` (2450: insurance & shipping ¥1,900 + handling ¥550; the app assumes 2450 if omitted), and a `raw_tiers` object (same three-key shape as `tiers`, but for the raw-card entry price). Omit all three if that angle wasn't evaluated: the app's DIY tab then works it out with PSA Standard fees whenever a raw price and a gem rate exist.

### 8. Apply it to the tracker

**If the linked computer is available** (the `mcp__remote-devices__*` tools work), one `device_bash` call. Key the JSON by the card's **SNKRDUNK URL**, not its name, since similar names collide (V CSR vs. VMAX CSR, ゲッコウガ vs. メガゲッコウガ); several cards go in one object. Build the JSON with `json.dumps` or check it with `python3 -m json.tool` before applying (hand-typed JSON has lost a closing brace before), and preview with `--dry-run` when it's a new card or new sell tiers:
```
R=$(ls -d "$HOME"/mnt/*/psa10-tracker "$HOME"/mnt/psa10-tracker 2>/dev/null | head -1); cd "$R" && python3 scripts/apply_analysis.py - <<'JSON' 2>&1 | tail -30
{"https://snkrdunk.com/apparels/<id>": {<Part B>}}
JSON
```
`apply_analysis.py` pulls, matches by URL, validates the tiers, sell tiers, tags and predictions, and merges over the existing analysis, keeping fields you didn't send (a sell-only evaluation leaves the buy tiers and buy verdict alone). It dates new verdicts, rebuilds the price-history index and the track record, takes the card off the evaluation queue (`data/eval_queue.json`) when a buy verdict was applied, and commits and pushes, using the repo's own credential file. Inside a price-check run (the run clock is running) it only commits, and the price check's `runclock.py end` pushes everything at once; run on its own, it pushes right away. Never put a token in a command. It stops rather than guessing if the card isn't on the tracker or the JSON is invalid. If it warns that the reasoning states odds but `predictions` is missing, add them and re-run. If git fails with a `.lock` "File exists" / "Operation not permitted" error, call `device_request_delete_permission` for the connected folder once, remove the stale lock and re-run.

In the chat, give one line per card with the result, including how many predictions were recorded, e.g. "Applied: Watch → Buy (live zone: Buy), 2 predictions recorded" or "Sell tiers for Umbreon: take profit ≥¥95k, sell ≥¥120k (Hold, +¥3k net today)". If it printed a note that the written verdict differs from the live price zone, pass that on. If the card isn't in the latest snapshot yet, `apply_analysis.py` stops: a card added by a request appears once a price check publishes it (the price check does that before it evaluates). For a card that isn't tracked at all, point to the site's **+ Add card** button; the next price check adds it and evaluates it in the same run.

**If the computer isn't linked:** give the user Part B and tell them to run `python3 scripts/apply_analysis.py` in the repo on their Mac. It reads the clipboard (macOS only; elsewhere pass a file or `-` for stdin), and `--dry-run` previews without writing.

Skip this step when the user is only exploring a card they don't plan to track, or explicitly asks not to publish.

Throughout: be explicit about data quality, flag stale or conflicting figures (e.g. conflicting illustrator attributions, or a stated "average" vs. an actual transaction print), and don't let a plausible theory (e.g. "everyone's selling to fund new pulls") get accepted without checking whether the data actually supports it — but don't dismiss it either if the timing genuinely lines up.

---

## Reusable prompt template

Copy this, fill in the brackets, and use it (with web search / browsing available) whenever evaluating a card outside a price check.

```
Analyze [CARD NAME] — [set code + number], [Japanese set name] (【set name】),
released [date if known], illustrator [name if known] — for my PSA10 Japanese
Pokémon TCG collection. [I'm watching it / I own it: bought [date] for ¥[price]
([slab / raw, sent to PSA])].

CRITERIA: only PSA10 graded copies (raw/A-rank for reference only). Only
modern full-art cards of any rarity (AR, SAR, SR, CSR, SA, MA, …) — no
regular-frame commons/rares, no vintage. Goal is display (magnetic UV case,
office) plus investment. Today's date is [date]. [Optional: budget context /
other cards being weighed against this / how much this card is wanted and why.]

RESEARCH — use Japanese-market sources (SNKRDUNK, pokeca-chart.com/gr, card
shop buyback trackers, note.com market commentary) and PSA's pop report
(psacard.com/pop) for population, read in my browser. Gather:
1. Current PSA10 market price — recent transaction prints over stated averages;
   flag outlier prints
2. PSA10 population and gem rate, release date, backlog check; DIY replacement
   cost = (raw A-rank + ¥12,430) ÷ gem rate (Standard to ¥150,000; Priority
   +¥2,000 to ¥250,000; Express above), where
   raw A-rank = median of the last 5 one-copy A sales in 30 days, never
   below the lowest ask (fewer than 3 sales: the lowest ask)
3. Raw/A-rank price (rule above) and 1-month trend, cross-checked against real trades
4. Longest reliable price range and average (state the window), the pre-hype
   level, and the most recent peak (peak-month median) with % drawdown
5. Demand drivers, cannibalization/reprint risk, in-print status
6. Market regime: My-tier index 30-day change, pokeca-chart index, events in
   the next 3 days, the card's age and hype exposure
7. Selling cost on SNKRDUNK (9.5% + ¥300 + ~¥1,000 shipping) and, if owned,
   my break-even sale price

OUTPUT — two parts:

PART A (prose): if watching, the buy part (Don't-buy ceiling, Watch, Buy,
Definitely buy, timing, odds with deadlines checked against the limit-odds
model, downside risk); if owned, the sell part (Hold / Take profit from ¥X /
Sell from ¥Y, net result after fees today, anchors, odds with deadlines,
market regime). Be honest about data quality; correct my assumptions when the
data disagrees.

PART B: the JSON block from the pokemon-tcg-card-evaluation skill (tiers +
verdict for a buy evaluation, sell_tiers + sell_verdict for an owned card,
every stated probability as {text,p,type,price,by}).
```

---

## Card reference (evaluated cards)

Starting data for cards already evaluated with this skill. Use it for step 1 (identification) and as a prior baseline. Always re-pull live data: the tracker's latest snapshot and the card page are the current source, and these figures go stale within days.

### ゲッコウガex SAR [SV5a 090/066] (Greninja ex SAR)
- **Identity:** 強化拡張パック「クリムゾンヘイズ」 (Crimson Haze), released 2024-03-22, illus. akagi. SNKRDUNK https://snkrdunk.com/apparels/224087 · PSA pop: Pokemon Japanese Sv5a-Crimson Haze, no. 090. Don't confuse it with Mega Greninja (M4), the overseas promo SA, or other Greninja prints.
- **Supply:** mature population, 15,446 PSA10 of 18,269 graded, 84.5% gem rate (PSA pop report, 2026-10-12). The sealed box trades at about 2× retail, which suggests it's likely out of print (not formally verified).
- **PSA10 phases (SNKRDUNK monthly medians):** 2024: ¥12k post-release trough in May → ¥25.5k by Dec. 2025: ¥41–48k H1 → ¥47–49k Jul–Aug → ¥58–62k Sep–Dec. 2026: peak ¥79–83k Jan–Feb (high ¥85.5k on 2/13, before the anniversary announcement) → ¥64–75k Mar–Aug → ¥42.75k on 2026-09-25.
- **Tiers (2026-09-25):** Definitely buy ≤¥38,000 · Buy ≤¥43,000 · Ceiling ¥49,000.
- **Watch for:** the PSA10 premium over raw A-rank collapsed to about 13% (usually about 45%). The card fell 31% year on year while the index rose 5%; likely cause is cannibalization by M4 Mega Greninja (hypothesis, not proven). Raw A-rank trades only 1–3 times a month.
- **Useful as an analog:** how a popular-character SAR behaves after release, from trough to about 7× over 21 months in a rising market.

### ゲンガーVMAX SA [SGG 020/019] (Gengar VMAX, Special Art) — restored to the tracker 2026-10-10
- **Identity:** ハイクラスデッキ「ゲンガーVMAX」 (High Class Deck Gengar VMAX). SNKRDUNK https://snkrdunk.com/apparels/91178.
- **Price levels:** pre-hype ¥238–247k in Q4 2025, about ¥270k in Feb 2026, peak-month median ¥457.7k (Aug 2026). On 2026-10-10 the lowest ask was ¥378k with sales at ¥385–400k, up ~35% in a week during the rally.
- **Tiers (2026-10-10):** Definitely buy ≤¥265,000 · Buy ≤¥295,000 · Ceiling ¥335,000 (Don't buy at ¥378k). The user's saved limit was ¥150,000. Above PSA Priority's ¥250,000 declared-value cap (only Express), and above the whole singles budget on its own.

### メガゲッコウガex SAR [M4 114/083] (Mega Greninja ex SAR) — removed from the tracker 2026-10-06
- **Identity:** 拡張パック「ニンジャスピナー」 (Ninja Spinner), released 2026-03-13, illus. Susumu Maeya. SNKRDUNK https://snkrdunk.com/apparels/776365. The MUR print (M4 120/083) is a separate card.
- **Useful as an analog:** a card that launched into a bubble with no pre-hype baseline: median ¥118k (Apr 2026) → ¥28k (2026-09-25), raw ¥55k → ¥17k, PSA10 ending at DIY cost (94.7% gem rate, in print).

### メガリザードンXex MA [M2a 223/193] (Mega Charizard X ex, Mega Attack Rare) — owned
- **Identity:** ハイクラスパック「MEGAドリームex」 (MEGA Dream ex), released 2025-11-28, illus. Saboteri. SNKRDUNK https://snkrdunk.com/apparels/722239. Full art (American-comic style, INFERNO X in large letters). MA cards are numbered 223–232. Texture-error copies (Traditional Chinese texture) trade separately at about 7–10×.
- **Supply:** 66,963 PSA10 at a 91.2% gem rate (2026-10-03): very common. Raw A-rank about ¥3.5–4k, so there's no DIY floor.
- **PSA10 phases (monthly medians):** ¥27–28k Dec 2025–Jan 2026 → ¥21.6k Mar → peak ¥38.7k Apr → ¥33.5k May → ¥26.9k Jun → ¥20.3k Jul → ¥14.7k Aug → ¥12.7k Sep → ¥10.7k on 2026-10-03.
- **Buy tiers (2026-10-03):** Definitely buy ≤¥8,500 · Buy ≤¥9,500 · Ceiling ¥11,500. Bought 2026-10-07 for ¥10,800 (slab).

---

## Notes for future use

- Rerun this roughly every time before a purchase or sale decision — prices in this market move meaningfully week to week.
- When comparing multiple candidate cards at once, use the same output format for each so they're directly comparable, then add a combined table.
- The tracker web app shows the gauge, verdict and sell view for tracked cards from Part B, so a standalone graphic is only needed for cards outside the tracker.
- When this runs as part of a price check (EVALUATE NOW, SELL TIERS NOW, review due, verdict refresh), still apply every step — don't shortcut to a simple percentage-band guess; `eval_context.py` makes the data part quick. If a step's data can't be found, say so explicitly in the output rather than silently omitting it. A card that can't be evaluated stays on the evaluation queue and the price check's chat message names it with the reason.
- `python3 scripts/eval_queue.py` lists what the next price check will evaluate; `eval_queue.py add <id> "<why>"` queues a card by hand (e.g. after reprint news), `drop <id>` removes one.
- The tracker flags **Review due** when buy tiers are over 30 days old, the market has moved 10%+ since they were set, Definitely-buy is a long shot, or a young card's tiers are 2+ weeks old; and asks for fresh sell tiers when a sell verdict is over 30 days old. A re-evaluation that keeps the same numbers still counts.
- Stated odds become the tracker's Track record: write them as honestly calibrated probabilities, not hedges. Check the Brier score and "expected vs happened" count when setting new odds.
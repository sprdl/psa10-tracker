# Sell side (owned cards)

(Part of the `pokemon-tcg-card-evaluation` skill; SKILL.md says when to read this. Split out of SKILL.md on 2026-10-23 so runs that don't need it don't read it; the claude.ai copy of the skill still has it inline.)

## Part A — the sell part

*Sell part* (owned cards only): two lines, no stop-loss line (the user chose this on 2026-10-07):
- **Hold** — below Take profit. Say what the card nets after selling costs at today's price vs the user's cost basis (for a raw card, the DIY cost with the price paid, as in step 2).
- **Take profit from ¥X** — where selling becomes attractive: clearly above the user's break-even after fees, and rich against the card's own pre-hype level.
- **Sell from ¥Y** — bubble territory, where holding on is mostly a bet on the bubble continuing.
- **Timing and odds** — rough odds of a listing reaching each line by a stated date, and what would get it there (market rally, event) or stop it.
- **Market regime** — whether the market is rising or rolling over, and the card's hype exposure: a high-exposure card at Take profit while the market turns down is the strongest case for selling.
- Phrase it as "list at ≥¥X / take profit from ¥X". SNKRDUNK sales are fixed-price listings; to sell you list at or a little under the lowest ask.

## What the data says about setting sell tiers (2026-10-07, 284 PSA10s, 2021–26, monthly; project docs `claude/sell-tiers-2026-10-07.md` and `claude/crash-resilience-study-2026-10-03.md`)
- A card trading at **2× or more its own trailing-12-month median** had a median **−17% over the next 6 months**, and a **53%** chance of falling more than 10% (cards 0–70% above their median: median +19% to +29%, 19–26% chance of a >10% fall). These cases cluster at market tops (2023, 2026), so they mostly mark *market* peaks. Anchor **Sell from** around 2× the card's pre-hype level (its Q3–Q4 2025 range or trailing-12-month median), or the prior hype peak's monthly median if that's lower.
- Below that, rising cards kept rising on average (momentum). Being up a lot is not by itself a reason to sell, and against other cards being far above its own history predicted nothing (+2 points on average, worse in only 10 of 27 months). So set **Take profit** where the gain is worth locking in: at least ~15% above the user's break-even after fees, and roughly +50–70% over the pre-hype level, or about 85% of the prior peak-month median.
- When the market turns down, the cards that ran up most fall hardest (top third by run-up −11% to −22% vs the market in the 2023–24 and 2026 falls). So a high hype exposure plus a falling My-tier index is the strongest reason to act at Take profit rather than wait for Sell.
- Never set Take profit below the user's break-even after fees. If the card is under water, the verdict is Hold (with today's net result stated), whatever the market does.
- Check reachability: the Upside tab's 12-month range (Take profit usually between its Typical and Strong case) and the price history. A Sell line no listing has come near in the card's history is a long shot: say so.

## Part B — the sell fields

- **`sell_tiers`** (owned cards only) — exactly `take_profit_from` and `sell_from`, in JPY, `take_profit_from` < `sell_from`. Don't send `reassess_below`: the user chose two lines, and `apply_analysis.py` rejects it. Below `take_profit_from` the app shows Hold.
- **`sell_verdict.tag`** — `"hold"`, `"take_profit"` or `"sell"` for *today's* price against the sell tiers (`apply_analysis.py` rejects any other tag). The label says it in a few words; the reasoning compresses Part A's sell part (net result today, anchors, odds, regime) into 1–3 sentences. `apply_analysis.py` dates it, and the full check asks for a fresh one after 30 days.

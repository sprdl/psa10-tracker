# Steps 6 and 6b: Monday tasks

Part of the full price check (`pricecheck/FULL-CHECK.md`, which holds the shared rules: credentials, publishing, the chat message). Read this file on Mondays (JST).

**6. Monday only: PSA tier status.** Follow `pricecheck/references/state.md`. On other days skip it entirely.
Put the result on one line: `TIER <the psa_tier_status JSON>`.

**6b. Monday only: release calendar** (computer linked only). The tracker's `data/events.json` drives the event rule: in the 3 days before a major release (and on the day), Buy-zone prices show as Watch on the site, and the evaluation skill won't call Buy. Keep it current:
1. One `device_bash` call: `cd "$R" && python3 scripts/events.py list` (upcoming dated events plus rumoured undated ones).
2. One or two `WebSearch` calls for newly announced Japanese products, e.g. `ポケモンカード 新弾 発売日 <this month> <next month>` and `ポケカ 新商品 発表 <year>`. Prefer the official site (pokemon-card.com) or a schedule page that cites it; open a page with `WebFetch` only if the snippets don't give a date.
3. For each official announcement not yet listed, one `device_bash` call from the repo:
   - New dated product: `python3 scripts/events.py add YYYY-MM-DD "<official Japanese name>" --scope all --source <url>`. Use `--scope <set code>` (e.g. `M6a`) for a product that only adds packs of an existing set, and `--minor` for promos, supplies or small reprints that won't move PSA10 prices. Major announcements with a known date (e.g. a Pokémon Presents) go in with `--kind announcement`.
   - A rumoured (undated) event that now has an official date: `python3 scripts/events.py date "<name part>" YYYY-MM-DD`.
   - A product that was cancelled or turned out wrong: `python3 scripts/events.py remove "<name part>"`.
   The script commits and pushes each change (same credential rules as step 7).
4. Only add official dates. Trademark filings and leaks stay undated and never trigger the rule; never give them a date.
If nothing new was announced, change nothing. In the chat message, mention any calendar change in one line ("Calendar: added 拡張パック「…」 on 11/27"), and whether the event rule is on right now (`python3 scripts/events.py window`).

**6c. Monday only: Binder prices.** Nothing extra to run: `plan.py` adds the Binder's cards to the step 2b HELD list on Mondays, and `full_update.py` saves them to `data/binder.json` (A-rank raw rule, previous price kept for the ▲/▼ indicator). Cards without a SNKRDUNK id are listed under FOLLOW-UPS `2c` (`pricecheck/steps/2c-binder-ids.md`). Mention one line in the chat message, e.g. "Binder: ¥xx,xxx (+3.1% vs 10/19)" from the `binder:` line the update prints.

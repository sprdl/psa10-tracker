# Step 2c: SNKRDUNK ids for the Binder cards

Part of the full price check (`pricecheck/FULL-CHECK.md`). Read this when FOLLOW-UPS lists `2c` (`BINDER IDS NEEDED`).

The Binder (`data/binder.json`, site page "Binder") holds the raw cards from Philipp's physical binder. Each card is priced once a week, **on Mondays only**, as an A-rank raw copy (the rule in `scripts/raw_price.py`). The reading is the same in-page script as step 2b (`snkrdunk_held.js`, H lines); `plan.py` adds the binder's ids to HELD on Mondays. A card without a `snkrdunk_id` is not priced.

For each card listed under `BINDER IDS NEEDED`:
1. In the browser (SNKRDUNK tab, a normal tab, a few page loads at a time; no automated or headless access), search SNKRDUNK for the card by set code and number (e.g. `M6a 118/103`, `sv2a 168/165`) and open the matching single-card page. Check set, number and rarity against the binder entry.
2. The id is the number in the page URL `/apparels/<id>`. Save it:
```
python3 scripts/binder.py set-id <binder card id> <snkrdunk id>
```
3. If the card has no SNKRDUNK page or you aren't sure which page is right, don't guess: leave it without an id and tell Philipp in the chat message.

Commit `data/binder.json` (the run clock pushes it at the end). The first reading happens on the next Monday's full check; the ▲/▼ indicator needs two readings.

Chat message: one line, e.g. "Binder: 21 cards now have SNKRDUNK ids; first prices on Monday".

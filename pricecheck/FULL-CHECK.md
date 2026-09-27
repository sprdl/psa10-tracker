# Full price check (SNKRDUNK + pokeca-chart.com + altema)

The full-check procedure of the `pokemon-card-price-check` skill. The skill itself only carries
the mode choice and the quick check; read this file for a full check. Paths like
`scripts/...` and `references/...` below mean this `pricecheck/` folder (copied to
`./price-check-run` in step 1); `scripts/...` inside the tracker repo (add_snapshot.py,
events.py, …) are named as "the repo's" or run from `$R`.

## Why the run is built this way

The expensive part of this task used to be context growth: full-page `get_page_text` dumps and screenshots piling up across 11 cards. So:
- **Extract with the scripts, not get_page_text or screenshots.** Each script returns a few hundred bytes of JSON and verifies its own work (sort order, SOLD tiles, grade filter, pill activation). Take a screenshot only to debug a script error.
- **One `browser_batch` per card.** Navigate + script pairs for a card go in a single round trip.
- **Card metadata lives in `references/cards.json`** and is merged in by `scripts/assemble.py`, so names, URLs, and image URLs never need retyping.

## Files

- `scripts/snkrdunk_base.js`: on `https://snkrdunk.com/apparels/<id>` → favorite count + 売買履歴 completed sales for PSA10 and A.
- `scripts/snkrdunk_listings.js`: on `<url>/used?conditionIds=22` (PSA10) or `=18` (A) → applies 安い順 + 販売中のみ, returns top-20 cheapest and the 15% stats.
- `scripts/altema_population.js`: on the card's altema URL → PSA10総枚数, 取得率, plus 型番/封入パック for identity checking.
- `scripts/pokeca_index.js`: on either pokeca-chart index page → header stats + exact daily volume from the chart's own data.
- `scripts/assemble.py`: raw results → final output JSON, validation, warnings, change summary.
- `references/cards.json`: tracked cards (SNKRDUNK id, name, URL, cached image URL, altema URL, altema cadence).
- `references/state.md`: last known PSA tier state, altema search tips, new-release notes, how to change the card list. Read only when needed.
- `references/manual-fallback.md`: hand procedure for a single step if its script breaks. Read only when needed.
- My-tier index: the tracker repo's `scripts/add_custom_index.py` holds the 22-card index definition (in `data/custom_index.json`), prints its in-page extractor (`--print-js`), and saves + pushes the day's value. Full checks only.
- Limit-odds model: the tracker repo's `data/odds_model.json` (odds that a listing reaches a price within 30/90 days; the site and `scripts/odds_model.py` use it). It's rebuilt monthly from pokeca-chart price history with `scripts/odds_model_builder.js` + `scripts/save_odds_model.py` (step 5b). `add_snapshot.py` logs the model's weekly forecasts by itself; nothing to do for that.
- Release calendar: the tracker repo's `data/events.json`, edited with `scripts/events.py`. It drives the event rule on the site and is refreshed on Mondays (step 6b).
- Card evaluations: the `pokemon-tcg-card-evaluation` skill. Full checks run it for tracked cards that have a PSA10 market but no tiers yet, such as a card just added in step 1b (step 8b).
- Publishing target: the user's `psa10-tracker` repo on their linked computer. Full checks publish via its `scripts/add_snapshot.py` (step 8). Quick checks publish via its `scripts/quick_update.py` (step Q4). Its `scripts/check_status.py` says which mode to run. Its `data/tracked_cards.json` lists cards tracked beyond `references/cards.json`, and its `scripts/card_requests.py` handles "Add card" requests (GitHub issues labeled `add-card`) and updates that list.

## Cards tracked in the repo (data/tracked_cards.json)

Cards added after `references/cards.json` was written live in the tracker repo's `data/tracked_cards.json`, same fields as cards.json. Every run merges them in (step 1). New cards arrive there through the site's **+ Add card** button. That button files a GitHub issue, step 1b turns the issue into a list entry, and step 8b evaluates the new card, so adding a card never needs a skill change or a separate evaluation request.

Fallback, only when the computer isn't linked and the repo file can't be read: merge these two entries instead (they're also in the repo file).

```json
[
 {"snkrdunk_id": "224087", "card_name_ja": "ゲッコウガex SAR [SV5a 090/066](強化拡張パック「クリムゾンヘイズ」)", "url": "https://snkrdunk.com/apparels/224087", "image_url": "https://cdn.snkrdunk.com/upload_bg_removed/f5941c92-741f-43c8-a292-ef1e8f876517.webp?size=l", "altema_url": "https://altema.jp/pokemoncard/card/26372", "altema_mode": "daily"},
 {"snkrdunk_id": "776365", "card_name_ja": "メガゲッコウガex SAR [M4 114/083](拡張パック「ニンジャスピナー」)", "url": "https://snkrdunk.com/apparels/776365", "image_url": "https://cdn.snkrdunk.com/upload_bg_removed/7741933e-2432-47b7-9b3f-6aa150211963.webp?size=l", "altema_url": "https://altema.jp/pokemoncard/card/36855", "altema_mode": "daily"}
]
```

## Choosing the mode

- **Full:** listing pages (depth, top-20) for cards with a PSA10 market, altema population (daily for young cards, Mondays for mature ones), the pokeca-chart index, evaluations for cards without tiers, and on Mondays the PSA tier check and the release-calendar refresh. Cards with no PSA10 market get the tile-only treatment except on Mondays (step 3).
- **Quick:** one page per card, the SNKRDUNK product page. It reads the lowest PSA10/A ask from the grade tiles plus recent completed sales and favorites. Depth, population and the index are carried from the last full check and labeled "as of" on the site. This costs roughly a third of a full run.

Pick the mode like this:
1. If the user asked for one ("quick check", "full check"), use it.
2. Otherwise, if the linked computer is available, one `device_bash` call:
   ```
   R=$(ls -d "$HOME"/mnt/*/psa10-tracker "$HOME"/mnt/psa10-tracker 2>/dev/null | head -1); cd "$R" && git pull --ff-only --quiet; python3 scripts/check_status.py; python3 scripts/card_requests.py list
   ```
   Use `suggested_mode` from the first line. That's `full` for the first run of the JST day and `quick` after that. **If the second line lists any open card requests, run a full check anyway**: new cards need one to be added (step 1b) and evaluated (step 8b), and a quick check can only update cards already on the tracker. Say so in the one-line mode note.
3. If the computer isn't linked, run a full check. Quick needs the repo's latest snapshot to build on.

Tell the user in one short line which mode is running and why, e.g. "Quick check: today's full check already ran at 15:15."

## Full check procedure

**1. Setup.** Run `TZ=Asia/Tokyo date '+%F %A'` to get the JST date and weekday. Get the tracker repo's `pricecheck/` folder into a working directory: `git clone --depth 1 https://github.com/sprdl/psa10-tracker.git /tmp/pt && cp -r /tmp/pt/pricecheck ./price-check-run` (public repo, so this works in the cloud workspace whether or not the computer is linked). In the copy, append every entry from the repo's `data/tracked_cards.json` to `references/cards.json`, skipping any `snkrdunk_id` already there. Read it with `cat "$R/data/tracked_cards.json"` via `device_bash`; it's small. If the computer isn't linked, use the fallback entries above instead. Use the copy's `scripts/assemble.py` in step 7. Then read the merged `references/cards.json` and the four `.js` files once, plus `scripts/grade_tiles.js`. If the computer is linked, also get the My-tier index extractor with `device_bash`: `cd "$R" && python3 scripts/add_custom_index.py --print-js` (small; paste it verbatim in step 5). In the same call, print the odds model's build date: `python3 -c "import json;print('odds model built', json.load(open('data/odds_model.json'))['built'])"`. If it's more than 30 days old, this run also does step 5b. Paste each script into `javascript_tool` verbatim; they are self-contained and safe to re-run. Get a tab id (`tabs_context_mcp` with createIfEmpty, or a standalone `navigate`).

Also in setup, if the linked computer is available, stage the tracker's latest snapshot now (the `device_bash` + `device_stage_files` routine in step 7). Steps 2–3 need it, and step 7 reuses it as `--prev`. Print a compact per-card summary from it locally, never the whole file:
```
python3 -c "import json,sys;d=json.load(open(sys.argv[1]));[print(c['url'].rstrip('/').split('/')[-1], c.get('psa10_population'), (c.get('grades',{}).get('psa10') or {}).get('lowest_price')) for c in d['cards']]" <staged snapshot>
```
This prints `snkrdunk_id  population  PSA10 lowest ask` per card. If the computer isn't linked, there's no snapshot: treat every card as having a PSA10 market and every population as young (the old daily behavior).

**1b. Add requested cards** (only if the mode check listed open requests). For each request:
- `snkrdunk_id` is null: run `python3 scripts/card_requests.py reject <number> "no SNKRDUNK product URL found — open the card on snkrdunk.com and paste its address"`.
- Otherwise, one `browser_batch`: `navigate` its URL → `snkrdunk_base.js` → `scripts/grade_tiles.js`.
  - If the base result has no `title` or errors (the page doesn't exist), reject with the reason.
  - Otherwise, in one `device_bash` call from the repo: `python3 scripts/card_requests.py add <number> --name "<base.title>" --mode <daily if the PSA10 tile shows a price, else weekly_until_graded>`. This writes the entry, commits, pushes, and closes the issue with a confirmation. The same credential rules as step 8 apply.

  Then append the same entry to the working copy's `references/cards.json` (image_url and altema_url empty), so this run already includes it. Step 8b evaluates it once this run has published.
- For a new card with an empty `altema_url`: find its altema page with the on-site search, using the tips in `references/state.md`, and confirm the 型番 matches. Save it with `python3 scripts/card_requests.py set <snkrdunk_id> altema_url=<url>`. If you can't find it, leave it empty; its population shows as unavailable until found.

**2. Decide altema checks per card.** Population barely moves once a card is mature, and `add_snapshot.py` carries the last value forward (stamped `population_as_of`) whenever a run skips it.
- `altema_mode: "daily"` and the latest snapshot shows `psa10_population` **≥ 8,000**: check only on Mondays. Otherwise record `{"skipped": "weekly population check (mature card, 8,000+ graded)"}`.
- `altema_mode: "daily"` and under 8,000 (e.g. Mega Greninja, still in print and growing fast), or no snapshot value: check every run.
- `"weekly_until_graded"`: check only if today is Monday, or if this run's SNKRDUNK results show any PSA10 listing or completed sale for that card (graded copies exist, so population may appear). Otherwise record `{"skipped": "weekly check until graded"}`.

**3. Per card, one `browser_batch`** (use the explicit tabId in every action):
1. `navigate` → `https://snkrdunk.com/apparels/<id>`
2. `javascript_tool` → snkrdunk_base.js
3. `navigate` → `https://snkrdunk.com/apparels/<id>/used?conditionIds=22`
4. `javascript_tool` → snkrdunk_listings.js
5. `navigate` → `https://snkrdunk.com/apparels/<id>/used?conditionIds=18`
6. `javascript_tool` → snkrdunk_listings.js
7. (if altema is due) `navigate` → altema_url, then `javascript_tool` → altema_population.js

For a `weekly_until_graded` card, if steps 2/4 show PSA10 activity, run the altema pair as a small follow-up batch.

**Cards with no PSA10 market** (the latest snapshot has no PSA10 lowest ask, e.g. the new M6a cards; for a card just added in 1b, go by its PSA10 tile): on non-Mondays, don't open their listing pages. Their batch is `navigate` base page → `snkrdunk_base.js` → `scripts/grade_tiles.js`. Up to 4 of these cards can share one `browser_batch`. Then:
- If the **PSA10 tile shows a price**, a market is forming. Run the two listing pairs (steps 3–6) for that card as a follow-up batch, so it gets full data from its first day.
- Otherwise record `"psa10": {"error": "no for-sale listings (出品待ち on the grade tile)"}` and `"a": {"lowest_price": <A tile lowest_ask>, "threshold_115pct_of_lowest": <round(lowest_ask × 1.15)>}` in the raw file. If the A tile shows 出品待ち or failed, use `"a": {"error": "<the tile's note or error>"}`.

On Mondays these cards get the full listing pages too, which keeps a weekly depth reading of their raw market.

If the card's `image_url` in cards.json is empty, add one more action after step 2: `javascript_tool` with `[...document.images].map(i=>i.currentSrc||i.src).find(s=>s.includes('upload_bg_removed'))`. Record the result as that card's `image_url` in the raw file. Then persist it so later runs skip the fetch. For a card from the repo list, run `python3 scripts/card_requests.py set <snkrdunk_id> image_url=<url>` (no skill change needed). For a card in `pricecheck/references/cards.json`, edit that file in the repo and commit it (no skill change needed). If nothing is found, leave it empty so a later run retries.

`browser_batch` stops at the first *tool* error (e.g., a navigation failure). If that happens, re-run only the remaining actions. A script returning `{"error": ...}` is not a tool error; it's a valid result to record. If an error says the page structure changed (controls/pill/chart data not found), do that one step by hand per `references/manual-fallback.md` and flag it at the end so the script can be fixed.

**4. Sanity checks while reading results** (cheap, no extra calls): listings `filter_label` should match the grade (`PSA10` / `A（きれいな状態）`); altema `card_number` should match the card's number. An empty PSA10 result on a new-release card is expected (see state.md). For the tile-only cards above, assemble.py's "only 0 live listing(s)" warning on their A grade is expected too (no top-20 was read). Don't report it.

**5. Market index, one batch:** navigate `https://pokeca-chart.com/gr/chart-index/` → pokeca_index.js, then navigate `https://pokeca-chart.com/chart-index/` → pokeca_index.js, then (computer linked only) navigate `https://pokeca-chart.com/gr/all-card/?sort=newest` → the My-tier index extractor from step 1. Keep the extractor's result (`{page_cards_seen, prices, missing}`) aside for step 8; it does not go into the raw file (assemble.py would drop it). If it returns an error, skip the My-tier index this run and mention it. The script's `volume_trend_suggested` applies a fixed rule (spiking if any day in the last 14 exceeds 2× the prior-30-day average; rising/falling if the 14-day average is ±15% vs the prior 30 days; else flat). Use it as-is unless the numbers clearly say otherwise. Add a `volume_overrides` entry only if you have a genuinely better read or a notable day worth describing.

**5b. Monthly: rebuild the limit-odds model** (only when step 1 found it more than 30 days old, and the computer is linked). It reads about 125 pokeca-chart card pages through same-origin iframes, so it takes several minutes; do it after the price reads.
1. `cat "$R/scripts/odds_model_builder.js"` via `device_bash`, navigate to `https://pokeca-chart.com/gr/all-card/?sort=newest`, and paste the file's contents verbatim into `javascript_tool` (it defines `__oddsBuilder`). Never fetch the script from a URL to run it.
2. `javascript_tool`: `await __oddsBuilder('list')` → "pool: N cards".
3. `javascript_tool`: `await __oddsBuilder('grab')` → repeat until it returns "done". Each call reads up to 35 cards. A card that fails is retried on the next call, up to twice; "done" reports how many were read.
4. `javascript_tool`: `await __oddsBuilder('build')` → a JSON string of about 7 KB.
5. One `device_bash` call: write it with a heredoc to `data/incoming/odds-model.json`, then `python3 scripts/save_odds_model.py data/incoming/odds-model.json`. It refuses thin builds (under 60 cards) and keeps the model's `about` block, then commits and pushes.
Mention the rebuild in the chat message in one line ("Limit-odds model rebuilt: 125 cards, pool volatility 20%/39% per 30/90 days"). If any step fails, keep the old model and say so.

**6. Monday only: PSA tier status.** Follow `references/state.md`. On other days skip it entirely.

**6b. Monday only: release calendar** (computer linked only). The tracker's `data/events.json` drives the event rule: in the 3 days before a major release (and on the day), Buy-zone prices show as Watch on the site, and the evaluation skill won't call Buy. Keep it current:
1. One `device_bash` call: `cd "$R" && python3 scripts/events.py list` (upcoming dated events plus rumoured undated ones).
2. One or two `WebSearch` calls for newly announced Japanese products, e.g. `ポケモンカード 新弾 発売日 <this month> <next month>` and `ポケカ 新商品 発表 <year>`. Prefer the official site (pokemon-card.com) or a schedule page that cites it; open a page with `WebFetch` only if the snippets don't give a date.
3. For each official announcement not yet listed, one `device_bash` call from the repo:
   - New dated product: `python3 scripts/events.py add YYYY-MM-DD "<official Japanese name>" --scope all --source <url>`. Use `--scope <set code>` (e.g. `M6a`) for a product that only adds packs of an existing set, and `--minor` for promos, supplies or small reprints that won't move PSA10 prices. Major announcements with a known date (e.g. a Pokémon Presents) go in with `--kind announcement`.
   - A rumoured (undated) event that now has an official date: `python3 scripts/events.py date "<name part>" YYYY-MM-DD`.
   - A product that was cancelled or turned out wrong: `python3 scripts/events.py remove "<name part>"`.
   The script commits and pushes each change (same credential rules as step 8).
4. Only add official dates. Trademark filings and leaks stay undated and never trigger the rule; never give them a date.
If nothing new was announced, change nothing. In the chat message, mention any calendar change in one line ("Calendar: added 拡張パック「…」 on 11/27"), and whether the event rule is on right now (`python3 scripts/events.py window`).

**7. Assemble.** Write the raw file in the shape documented at the top of `scripts/assemble.py`: paste each script result verbatim under `cards.<snkrdunk_id>.{base, psa10, a, altema}` and `index.{psa10, raw}`, plus `psa_tier_status` on Mondays and optional `run_notes`.

For `--prev`, use the tracker's latest snapshot staged in step 1, so the change summary compares against what is actually live. The staging routine, used in step 1, needs the linked computer (the `mcp__remote-devices__*` tools). Find the repo and the latest snapshot's file name with one small `device_bash` call. Print only the file name, never the file:

```
R=$(ls -d "$HOME"/mnt/*/psa10-tracker "$HOME"/mnt/psa10-tracker 2>/dev/null | head -1); echo "$R"
cd "$R" && git pull --ff-only --quiet; python3 -c "import json;m=json.load(open('data/manifest.json'));print(sorted(m['snapshots'],key=lambda s:s['collected_at_jst'])[-1]['file'])"
```

Then copy that snapshot into the working directory with `device_stage_files`, using the repo's path on the device (from `get_device_info` connectedFolders + `/psa10-tracker/data/snapshots/<file>`), not a `device_bash` read. If the computer isn't linked, run without `--prev`.

```
python3 ./price-check-run/scripts/assemble.py raw.json --out pokemon-price-check_<YYYY-MM-DD_HHMM>JST.json [--prev <staged latest snapshot>]
```

It merges card metadata, builds the approved output shape, validates the JSON, and prints WARNINGS (errors, thin supply, a card that should switch to daily altema) and, with `--prev`, CHANGES (favorite count, lowest price, population, index).

**8. Publish to the tracker.** The run ends with the site updated, not with a file the user still has to handle.

If the linked computer is available:
1. `SendUserFile` the output file. This gives the user a copy and returns a `file_uuid`.
2. `device_commit_files` that `file_uuid` to `<repo path on the device>/data/incoming/latest-run.json`. The folder is gitignored, and the file is overwritten each run on purpose, so no cleanup or delete permission is needed.
3. One `device_bash` call:
   ```
   cd "$R" && git pull --ff-only --quiet && python3 scripts/add_snapshot.py data/incoming/latest-run.json 2>&1 | tail -40
   ```
   (`$R` is the repo path from step 7. Each `device_bash` call is a fresh shell, so set it again.) `add_snapshot.py` normalizes the shape, carries forward tiers/peak/verdict, saves `data/snapshots/<timestamp>.json`, updates the manifest, commits and pushes. The repo has its own credential file configured. **Never put a token or credential in any command**, and never ask the user for one. If a push fails with an auth error, tell the user the token in `.psa10-git-credentials` may have expired.

   If step 5 produced a My-tier index result, append it to the same call, so it costs no extra round trip. Paste the extractor result verbatim into the heredoc, and pass today's pokeca-chart PSA10 `latest_index_value_jpy` from step 5:
   ```
   ... && cat > data/incoming/custom-index.json <<'EOF'
   <extractor result JSON>
   EOF
   python3 scripts/add_custom_index.py data/incoming/custom-index.json --pokeca <PSA10 index value> 2>&1 | tail -5
   ```
   It saves one entry per JST day (a second full check the same day replaces it), carries a missing card's last price forward, refuses to save if under 80% of the cards are priced, then commits and pushes `data/custom_index.json`.
4. Read its output. The push succeeded if it ends with "Pushed." If it says the snapshot is byte-identical to an existing one, nothing new was published; say so. If `git pull --ff-only` or the push fails because the history diverged, don't force anything. Tell the user to run `git pull` then `git push` in the repo on their Mac. If git fails with `unable to unlink ... .git/index.lock: Operation not permitted`, the connected folder doesn't allow deletes this session: call `device_request_delete_permission` for that folder once (git has to remove its own lock files), then `rm -f .git/index.lock` and re-run the step.

If the computer isn't linked, deliver the file with `SendUserFile`. Tell the user to publish it from the repo on their Mac with `python3 scripts/add_snapshot.py ~/Downloads/<file name>`.

Run one price check at a time. Overlapping runs published three identical snapshots on 2026-09-25.

**8b. Evaluate cards that have no tiers yet** (full checks only, computer linked, after step 8 has published). A card added in step 1b reaches the tracker without tiers or a verdict, and so does a watched card whose PSA10 market has just formed. Evaluate them in the same run, so the user never has to ask separately.
1. Find them with one `device_bash` call:
   ```
   cd "$R" && python3 -c "import json;m=json.load(open('data/manifest.json'));f=sorted(m['snapshots'],key=lambda s:s['collected_at_jst'])[-1]['file'];d=json.load(open('data/snapshots/'+f));[print(c['url'], (c.get('grades',{}).get('psa10') or {}).get('lowest_price'), ((c.get('analysis') or {}).get('verdict') or {}).get('tag'), c['card_name_ja']) for c in d['cards'] if not (c.get('analysis') or {}).get('tiers')]"
   ```
   It prints `url  PSA10 lowest ask  verdict tag  name` for every card without tiers.
2. Evaluate a card when it has a PSA10 lowest ask (a real PSA10 market) and either no verdict at all, or a `defer` verdict and today is Monday (a deferred card gets one fresh look a week, not one every run). Skip cards without a PSA10 ask: they stay on the watching page until graded copies are listed.
3. For each card to evaluate, run the `pokemon-tcg-card-evaluation` skill end to end, including its step 8, which applies the result to the tracker with `apply_analysis.py` (keyed by the card's SNKRDUNK URL). Reuse what this run already collected for the card (lowest asks and depth, completed sales, population and gem rate, raw A price, favorites, the PSA10 index and My-tier index) instead of reading those pages again. Only fetch what the evaluation still needs: the card's pokeca-chart price history and peak, set and release details, and the event calendar (`scripts/events.py window`). If the data is too thin to set tiers (e.g. only one or two PSA10 listings and no sales), the evaluation records `defer` without tiers, as its own rules say; that's a valid result.
4. Evaluate at most 3 cards per run. Name any others in the chat message; the next full check continues with them.
5. If an evaluation can't finish (a site is unreachable, or `apply_analysis.py` refuses the JSON), nothing is applied for that card. Say which card and why.

**Chat message (full check):** keep it short. Say where it was published (snapshot file name, or "not published" and why). Then pass on anything notable from the assemble WARNINGS/CHANGES and from `add_snapshot.py`'s own warnings: a stale timestamp, the tracked-card set changing, cards whose verdict now needs a fresh review. Examples: very few live listings, a big favorite-count move, a volume spike, a site that couldn't be reached. The live site shows the rest. Include the My-tier index line `add_custom_index.py` printed (level and change), or say why it was skipped. On Mondays, add the release-calendar line from step 6b. Also report any card requests handled in step 1b ("Added: <name>" / "Couldn't add #<n>: <reason>") and one line per card evaluated in step 8b, e.g. "Evaluated <name>: Watch, tiers ¥X / ¥Y / ¥Z, 2 predictions recorded".

## Output shape (produced by assemble.py)

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

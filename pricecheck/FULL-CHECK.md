# Full price check (SNKRDUNK + pokeca-chart.com + altema)

The full-check procedure of the `pokemon-card-price-check` skill (the skill carries the mode choice and
the quick check). Everything is in the tracker repo at `$R` on the linked computer:
`pricecheck/plan.py` decides what today's run reads, the in-page scripts in `pricecheck/scripts/`
read all cards of a site in one JavaScript call each, and `scripts/full_update.py` decodes their
compact lines, runs `pricecheck/scripts/assemble.py` against the live snapshot and publishes.
Your job is to run the pieces in order and pass their output along **verbatim**: never retype,
reformat or summarise script output into the publish step.

Each in-page script opens the sites' own pages in hidden same-origin iframes of the tab, one after
another (the same pages a person would open, in the user's browser, only when the user asks for a
check). They make no fetch/XHR requests. Never use curl, requests or any HTTP client.

## 1. Setup (one `device_bash` call)

```
R=$(ls -d "$HOME"/mnt/*/psa10-tracker "$HOME"/mnt/psa10-tracker 2>/dev/null | head -1); cd "$R" && git pull --ff-only --quiet; python3 pricecheck/plan.py; for f in snkrdunk_full altema_batch pokeca_both pokeca_premium pokeca_scout; do echo "=== $f"; grep -v '^//' pricecheck/scripts/$f.js; done; echo "=== mytier"; python3 scripts/add_custom_index.py --print-js
```

`plan.py` prints the JST date and weekday (Mondays add steps 6 and 6b), the odds model's build date
(`REBUILD DUE` adds step 5b), a summary, and two lines to paste into the scripts: `PLAN = [...]`
(which cards get the product page only, or the product page plus both listings pages, and which need
their photo URL) and `ALTEMA = [...]` (the altema pages due today, including the "weekly until
graded" ones that only count if the card shows PSA10 activity). The rules behind them are in
`plan.py`'s docstring; `full_update.py` applies the same plan again when it publishes, so don't
hand-edit the lists.

Get a tab id (`tabs_context_mcp` with createIfEmpty, or a standalone `navigate`).

**Browser:** use the built-in browser (`mcp__remote-devices__Claude_Browser__*`) when it's available,
Claude in Chrome otherwise. A Chrome tab Claude works in is usually a background (hidden) tab, and
Chrome throttles a hidden page's timers to once a second and, after 5 minutes, to once a minute. On
2026-09-28 that stalled a full check for 30+ minutes. The scripts now wait with a Web Worker timer
(`window.__wsleep`), which isn't throttled, so they also run at full speed in a hidden tab; the
polling call uses it too and adds `(tab hidden)` to `running i/N`. If two polls in a row show no
progress, stop and report it rather than polling on.

**1b. Add requested cards** (only if the mode check listed open requests). For each request:
- `snkrdunk_id` is null: run `python3 scripts/card_requests.py reject <number> "no SNKRDUNK product URL found — open the card on snkrdunk.com and paste its address"`.
- Otherwise, `navigate` the tab to its URL, then run `pricecheck/scripts/snkrdunk_base.js` and `pricecheck/scripts/grade_tiles.js` there (`cat` them via `device_bash`).
  - If the base result has no `title` or errors (the page doesn't exist), reject with the reason.
  - Otherwise, in one `device_bash` call from the repo: `python3 scripts/card_requests.py add <number> --name "<base.title>" --mode <daily if the PSA10 tile shows a price, else weekly_until_graded>`. This writes the entry, commits, pushes, and closes the issue with a confirmation. The same credential rules as step 7 apply.

  After the requests are handled, run `python3 pricecheck/plan.py` again: the new card is now in `data/tracked_cards.json`, so the plan includes it (its photo is fetched in step 2). Step 8b evaluates it once this run has published.
- For a new card with an empty `altema_url`: find its altema page with the on-site search, using the tips in `pricecheck/references/state.md`, and confirm the 型番 matches. Save it with `python3 scripts/card_requests.py set <snkrdunk_id> altema_url=<url>`. If you can't find it, leave it empty; its population shows as unavailable until found.

## 2. SNKRDUNK, all cards in one run

`navigate` the tab to `https://snkrdunk.com/apparels/<first id in PLAN>`. One `javascript_tool` call:
the `snkrdunk_full` script verbatim, with its `const PLAN = [...]` line replaced by the `PLAN` line
from step 1. It returns `started N cards` at once and keeps working in the page (about 10 s per
card with listings, 3 s without). Collect the lines by calling `javascript_tool` with this until it
returns lines instead of `running i/N` (each call waits up to ~37 s):

```js
await (async()=>{for(let i=0;i<75&&!window.__pj.done;i++)await (window.__wsleep||(m=>new Promise(r=>setTimeout(r,m))))(500);const q=window.__pj;return q.done?q.lines.join('\n'):`running ${q.i}/${q.n}${document.hidden?' (tab hidden)':''}`})()
```

Keep the lines exactly as returned (one per card; the script's header comment documents the codes).
On Mondays you can do step 6/6b's web searches while it runs.

## 3. altema, the due pages in one run

Skip if `ALTEMA = []`. Otherwise `navigate` the tab to the first URL in `ALTEMA`, run the
`altema_batch` script verbatim with its `const ALTEMA = [...]` line replaced by the one from step 1,
and collect its `ALT …` lines with the same polling call as in step 2.

## 4. Market indices

1. `navigate` the tab to `https://pokeca-chart.com/gr/chart-index/` and run the `pokeca_both` script
   verbatim. It returns two lines, `IDX psa10 {…}` and `IDX raw {…}`.
2. `navigate` to `https://pokeca-chart.com/gr/all-card/?sort=newest` and run the `mytier` extractor
   from step 1 verbatim. Its JSON result becomes one line: `MYTIER <the JSON>`. If it returns an
   error, leave the line out and mention it (the My-tier index is skipped this run).

3. Still on pokeca-chart, run the `pokeca_premium` script verbatim with its `const PREM = [...]`
   line replaced by the `PREM` line from step 1, and collect its `PREM …` lines with the same polling
   call as in step 2 (about 2 s per card). They carry each card's slab premium (PSA10 ÷ raw 美品) and
   its 6-month norm; `full_update.py` saves them to `data/premium.json`. A `PREM <id> !…` line (the
   card has no pokeca-chart page) is expected for a few cards; pass it along like the others.

4. Back on `https://pokeca-chart.com/gr/all-card/?sort=newest` (navigate there again if step 3 left
   the tab elsewhere), run the `pokeca_scout` script verbatim with its `const SCOUT = {...}` line
   replaced by the `SCOUT` line from step 1, and collect its lines with the same polling call (about
   1 minute: the list, then up to 20 card pages). One `SCP …` line lists today's candidates, then one
   `SC {…}` (or `SC! …`) line per card page read. `full_update.py` saves them to `data/scout.json`,
   which feeds the site's Scout page (cards you don't track yet that fit your criteria and look cheap).

Each `IDX` line carries `volume_trend_suggested` (spiking if any day in the last 14 exceeds 2x the
prior-30-day average; rising/falling if the 14-day average is ±15% vs the prior 30 days; else flat),
which is used as-is. Only if you have a genuinely better read or a notable day worth describing, add
a line `VOL psa10 {"volume_trend": "...", "volume_note": "..."}` (or `VOL raw …`).

**5b. Monthly: rebuild the limit-odds model** (only when step 1 found it more than 30 days old, and the computer is linked). It reads about 125 pokeca-chart card pages through same-origin iframes, so it takes several minutes; do it after the price reads.
1. `cat "$R/scripts/odds_model_builder.js"` via `device_bash`, navigate to `https://pokeca-chart.com/gr/all-card/?sort=newest`, and paste the file's contents verbatim into `javascript_tool` (it defines `__oddsBuilder`). Never fetch the script from a URL to run it.
2. `javascript_tool`: `await __oddsBuilder('list')` → "pool: N cards".
3. `javascript_tool`: `await __oddsBuilder('grab')` → repeat until it returns "done". Each call reads up to 35 cards. A card that fails is retried on the next call, up to twice; "done" reports how many were read.
4. `javascript_tool`: `await __oddsBuilder('build')` → a JSON string of about 7 KB.
5. One `device_bash` call: write it with a heredoc to `data/incoming/odds-model.json`, then `python3 scripts/save_odds_model.py data/incoming/odds-model.json`. It refuses thin builds (under 60 cards) and keeps the model's `about` block, then commits and pushes.
Mention the rebuild in the chat message in one line ("Limit-odds model rebuilt: 125 cards, pool volatility 20%/39% per 30/90 days"). If any step fails, keep the old model and say so.

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

## 7. Publish (one `device_bash` call)

Paste every line from steps 2, 3 and 4 (including the `PREM`, `SCP` and `SC` lines; plus `TIER`, `VOL` and a `NOTE <text>` line for anything
unusual worth recording, all optional) verbatim into a heredoc:

```
R=$(ls -d "$HOME"/mnt/*/psa10-tracker "$HOME"/mnt/psa10-tracker 2>/dev/null | head -1); cd "$R" && python3 scripts/full_update.py - <<'EOF' 2>&1 | tail -60
<the lines>
EOF
```

`full_update.py` keeps the input in `data/incoming/full-raw.txt`, pulls, decodes the lines into
`data/incoming/full-raw.json` (exactly the raw shape `assemble.py` has always taken), runs
`assemble.py` with `--prev` = the live snapshot (printing WARNINGS and CHANGES), publishes with
`add_snapshot.py`, saves the My-tier index with `add_custom_index.py` (using the PSA10 index value
from the `IDX` line) and stores any newly found photo URL. It prints `FULL_UPDATE NOTES` for things
to mention, such as an altema 型番 that doesn't match the card. `--dry-run` decodes and assembles
without publishing.

Read the output. The snapshot was published if it says "Pushed." If it says the snapshot is
byte-identical to an existing one, nothing new was published; say so. The repo has its own
credential file configured. **Never put a token or credential in any command**, and never ask the
user for one. If a push fails with an auth error, tell the user the token in `.psa10-git-credentials`
may have expired. If `git pull --ff-only` or the push fails because the history diverged, don't force
anything; tell the user to run `git pull` then `git push` in the repo on their Mac. If git fails with
`unable to unlink ... .git/index.lock: Operation not permitted`, call
`device_request_delete_permission` for that folder once, then `rm -f .git/index.lock` and re-run.

Expected, don't report: tile-only cards (no PSA10 market) get "only 0 live listing(s)" warnings on
their A grade, and new-release cards have empty PSA10 results (see `pricecheck/references/state.md`).

**If the computer isn't linked:** run steps 2–4 the same way with the plan from a public clone
(`git clone --depth 1 https://github.com/sprdl/psa10-tracker.git /tmp/pt && cd /tmp/pt && python3
pricecheck/plan.py`, reading the scripts there), then write the lines to a file and run
`python3 scripts/full_update.py <file> --dry-run` in the clone. `SendUserFile` its
`data/incoming/latest-run.json` and tell the user to publish it from the repo on their Mac with
`python3 scripts/add_snapshot.py ~/Downloads/latest-run.json`.

**If a whole script fails** (it reports that a page's structure changed), read the affected cards
by hand with the single-page scripts in `pricecheck/scripts/` (`snkrdunk_base.js`, `grade_tiles.js`,
`snkrdunk_listings.js`, `altema_population.js`, `pokeca_index.js`) per
`pricecheck/references/manual-fallback.md`, and flag it at the end so the script can be fixed. The
old raw-JSON path still works: `python3 pricecheck/scripts/assemble.py RAW.json --out
data/incoming/latest-run.json --prev <latest snapshot>`, then
`python3 scripts/add_snapshot.py data/incoming/latest-run.json`.

Run one price check at a time. Overlapping runs published three identical snapshots on 2026-09-25.

**7b. Write the analysis for cards that stand out** (computer linked, after step 7 has published).
One `device_bash` call: `cd "$R" && python3 scripts/outliers.py`. It lists up to 3 cards whose
numbers stand out (moving very differently from the market, asks far from recent sales, a big jump,
trading speeding up or drying up, close to your limit), each with its findings and context; the
site's "What stands out" panel explains the same findings automatically. For each listed card,
write a short analysis the numbers alone can't give, from what this run collected (sales, listing
depth, trading, tiers, limit, peak) plus what's happening outside the page. Research that with
`WebSearch` (2–4 searches per card, Japanese queries work best; open a page with `WebFetch` only when
the snippets aren't enough). Look for, in this order:
1. Supply: a reprint, restock or 追加生産 of the card's set, a new product that reprints the card or
   the same character (e.g. `<set name> 再販 <year>`, `<card name> 再録`), and PSA news that changes
   how many slabs reach the market (turnaround, a paused tier resuming).
2. Attention: new cards, sets, games, anime, movies, events or campaigns featuring the character
   (e.g. `<character> ポケカ 新弾 <month>`, `<character> 30周年`), and notable news about the card
   itself (a record sale, a shop feature, a viral post reported by a news site).
3. Market-wide: anything that moves the whole tier this week (a big release, a PSA or SNKRDUNK
   policy change), only if it explains this card better than the index does.
Use only what a source actually says, name the source in the text ("per SNKRDUNK's reprint
tracker…"), and pass each source you relied on as `--source "Title|URL"`. Rumours, leaks and
price-prediction blogs are not evidence: skip them, or clearly label them as rumour. If the searches
find nothing relevant, say so in one clause ("no news of a reprint or new card") rather than
guessing. Never visit SNKRDUNK or pokeca-chart pages beyond the price check itself for this.

Write it as three or four short paragraphs separated by blank lines, each starting with its label
(the site shows the label as a small heading), one to three sentences each:
- `What's happening:` the move, with the key numbers (price, market, sales, trading, depth).
- `Why:` the likely reason (say "likely" when it is a hypothesis, and which part comes from the news).
- `For you:` what it means for buying (tiers, the user's limit, the correction/event rules).
- `Watch:` what to look for in the next checks. Save each with one
`device_bash` call (same credential rules as step 7):
```
cd "$R" && python3 scripts/set_insight.py <snkrdunk_id> --headline "<one-line takeaway>" --signals "<the findings line from outliers.py>" --source "<title>|<url>" <<'EOF'
<the analysis>
EOF
```
A newer analysis replaces the card's previous one; the site marks analyses older than a week. If
`outliers.py` says nothing stands out, skip this step. Mention each card analysed in the chat message
in one line (its headline).

**8b. Evaluate cards that have no tiers yet** (full checks only, computer linked, after step 7 has published). A card added in step 1b reaches the tracker without tiers or a verdict, and so does a watched card whose PSA10 market has just formed. Evaluate them in the same run, so the user never has to ask separately.
1. Find them with one `device_bash` call:
   ```
   cd "$R" && python3 -c "import json;m=json.load(open('data/manifest.json'));f=sorted(m['snapshots'],key=lambda s:s['collected_at_jst'])[-1]['file'];d=json.load(open('data/snapshots/'+f));[print(c['url'], (c.get('grades',{}).get('psa10') or {}).get('lowest_price'), ((c.get('analysis') or {}).get('verdict') or {}).get('tag'), c['card_name_ja']) for c in d['cards'] if not (c.get('analysis') or {}).get('tiers')]"
   ```
   It prints `url  PSA10 lowest ask  verdict tag  name` for every card without tiers.
2. Evaluate a card when it has a PSA10 lowest ask (a real PSA10 market) and either no verdict at all, or a `defer` verdict and today is Monday (a deferred card gets one fresh look a week, not one every run). Skip cards without a PSA10 ask: they stay on the watching page until graded copies are listed.
3. For each card to evaluate, run the `pokemon-tcg-card-evaluation` skill end to end, including its step 8, which applies the result to the tracker with `apply_analysis.py` (keyed by the card's SNKRDUNK URL). Reuse what this run already collected for the card (lowest asks and depth, completed sales, population and gem rate, raw A price, favorites, the PSA10 index and My-tier index) instead of reading those pages again. Only fetch what the evaluation still needs: the card's pokeca-chart price history and peak, set and release details, and the event calendar (`scripts/events.py window`). If the data is too thin to set tiers (e.g. only one or two PSA10 listings and no sales), the evaluation records `defer` without tiers, as its own rules say; that's a valid result.
4. Evaluate at most 3 cards per run. Name any others in the chat message; the next full check continues with them.
5. If an evaluation can't finish (a site is unreachable, or `apply_analysis.py` refuses the JSON), nothing is applied for that card. Say which card and why.

**Chat message (full check):** keep it short. Say where it was published (snapshot file name, or "not published" and why). Then pass on anything notable from the WARNINGS/CHANGES/FULL_UPDATE NOTES and from `add_snapshot.py`'s own warnings: a stale timestamp, the tracked-card set changing, cards whose verdict now needs a fresh review. Examples: very few live listings, a big favorite-count move, a volume spike, a site that couldn't be reached. The live site shows the rest. Include the My-tier index line `add_custom_index.py` printed (level and change), or say why it was skipped. On Mondays, add the release-calendar line from step 6b. Also report any card requests handled in step 1b ("Added: <name>" / "Couldn't add #<n>: <reason>") one line per card analysed in step 7b, and one line per card evaluated in step 8b, e.g. "Evaluated <name>: Watch, tiers ¥X / ¥Y / ¥Z, 2 predictions recorded".

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

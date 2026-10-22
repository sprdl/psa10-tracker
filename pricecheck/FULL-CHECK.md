# Full price check (SNKRDUNK + pokeca-chart.com + PSA pop report)

The full-check procedure of the `pokemon-card-price-check` skill. `pricecheck/start.py` prints this
file, followed by today's setup output (plan, browser calls, PSA backlog schedule). Everything is in the
tracker repo at `$R` on the linked computer: `pricecheck/plan.py` decides what today's run reads,
`pricecheck/jsrun.py` turns the in-page scripts in `pricecheck/scripts/` into ready-to-paste browser
calls (each reads all cards of a site in one JavaScript call), and `scripts/full_update.py` decodes their
compact lines, runs `pricecheck/scripts/assemble.py` against the live snapshot and publishes.
Your job is to run the pieces in order and pass their output along **verbatim**: never retype,
reformat or summarise script output into the publish step.

Each in-page script opens the sites' own pages in hidden same-origin iframes of the tab, one after
another (the same pages a person would open, in the user's browser, only when the user asks for a
check). They make no fetch/XHR requests. Never use curl, requests or any HTTP client.

This file holds the core run (steps 0–7), the shared rules and the chat message. Steps that only some
runs need are in their own files; read one only when its trigger appears (the index is below step 7).

## Tool pitfalls (read before the first browser call)

- **Browser JavaScript tool.** The browser tools are often deferred (and again after a context compaction). Before the first call, load them with `ToolSearch` (`select:mcp__remote-devices__Claude_Browser__browser_batch,...javascript_tool,...get_page_text,...navigate,...tabs_create,...tabs_context,...tabs_close`, all in one call: the run uses three tabs and batches its browser steps) and read the schema. `javascript_tool` takes `action: "javascript_exec"` and `text` (the code). A call with wrong parameter names does not fail: it prints `undefined`. A correct call that returns nothing prints a value or an error, so **if you see `undefined` twice, stop retrying and check the tool's parameters** (the old "extra no-op call" trick only applies to a correct call). The code is a REPL expression: no `return` at top level; wrap async work as `await (async () => {...})()`.
- **Pasting browser calls.** Paste the RUN / STORE / POLL calls exactly as `jsrun.py` printed them, never a shortened stand-in or a hand-edited argument. They carry today's arguments and the scripts' SHA-256 hashes, so a call that was altered refuses to run instead of reading wrong data.
- **JSON for `apply_analysis.py` / `set_story.py`.** Build it with `python3 -c`/`json.dumps` or write it to a file and run `python3 -m json.tool file` before applying; hand-written JSON lost a closing brace on 2026-10-04 (nothing was saved; the script rejects bad JSON). Also include `predictions` whenever the reasoning states odds (price + deadline), or the warning "reasoning states odds but verdict.predictions is missing" appears.

## 0. Allow deletes in the repo folder (before anything else)

The repo folder is mounted with deletes blocked until the user approves them. Git removes its own
temporary files (`.git/HEAD.lock`, `ORIG_HEAD.lock`, `tmp_obj_*`) after every commit/push, so with
deletes blocked it leaves stale locks and the next commit fails ("Another git process seems to be
running"). Call `device_request_delete_permission` once at the start with the exact connected
folder root for this repo (from `get_device_info.connectedFolders`, e.g. `.../psa10-tracker`, not a
subfolder and not the nested parent folder) and a one-line reason ("let git clean up its lock
files during the price check"). If it is declined, carry on; afterwards clear leftovers with
`find .git -name '*.lock' -delete` only if deletion was granted, otherwise tell the user.

## 1. Setup (done: `pricecheck/start.py`)

The skill's one setup call already ran `git pull`, the mode check and card requests, started the run
clock, and printed this file plus today's setup output:
- `plan.py`: the JST date and weekday (Mondays add steps 6 and 6b), the odds model's build date
  (`REBUILD DUE` adds step 5b), a summary, and the plan lines `PLAN`, `PSAPOP`, `PREM`, `HELD`, `SCOUT`
  (and `PSAPOP MISSING` when step 1c has work). The rules behind them are in `plan.py`'s docstring;
  `full_update.py` applies the same plan again when it publishes. You don't paste these lines anywhere
  any more: `jsrun.py` has already put them into the RUN calls.
- `jsrun.py full`: one block per in-page script with its RUN call (and POLL call), labelled with the
  site and tab it belongs on.
- `psa_backlog.py due`: the last line, `DUE: …` or `none due: …` (step 8i).

If you need to re-run setup (after step 1b added a card, or after a context compaction lost the
calls): `cd "$R" && python3 pricecheck/plan.py && python3 pricecheck/jsrun.py full`.

**PSA look due today? Remind about the VPN, in the first message of the run.** The last line of that output is `DUE: …` or `none due: …` (the PSA backlog schedule, step 8i). On `DUE`, the first thing Philipp reads (your opening line, before any browser work) must say that today's run has to read PSA's page and ask him to **turn his VPN off** (psacard.com's Cloudflare check blocked the browser on 2026-10-10's earlier attempt, probably because of the VPN), and that it can go back on after step 8i. Say it again just before step 8i if you have no sign that it's off. On `none due`, don't mention the VPN.

**Open card requests** (`card_requests.py list` printed any): follow `pricecheck/steps/1b-add-cards.md`
before the browser reads. **`PSAPOP MISSING`** printed: follow `pricecheck/steps/1c-psa-pop-pages.md`
(up to 3 cards per run).

**Browser:** use the built-in browser (`mcp__remote-devices__Claude_Browser__*`) when it's available,
Claude in Chrome otherwise. A Chrome tab Claude works in is usually a background (hidden) tab, and
Chrome throttles a hidden page's timers to once a second and, after 5 minutes, to once a minute. On
2026-09-28 that stalled a full check for 30+ minutes. The scripts now wait with a Web Worker timer
(`window.__wsleep`), which isn't throttled, so they also run at full speed in a hidden tab; the
polling call uses it too and adds `(tab hidden)` to `running i/N`. If two polls in a row show no
progress, stop and report it rather than polling on.

## Browser calls: how the script cache works

The scripts' text is kept in each site's own browser storage (`localStorage`, key `pc:js:<name>`), so
a run pastes short RUN calls instead of the scripts. Every RUN call checks the cached text's SHA-256
against the repo version, fills in today's arguments, checks the SHA-256 of the filled-in script
against the one `jsrun.py` computed, and only then runs it. What runs is therefore byte-for-byte the
script the old procedure pasted, or nothing runs. Since 2026-10-20 the runner that does these checks
is cached too (key `pc:run`), so a RUN call is a short prefix plus today's arguments, and the POLL call
is a one-liner. Responses:
- `started …` or result lines: it ran. Carry on.
- `NEED_RUNNER (…)`: nothing ran (first run on this site since the change, a new runner version, or cleared
  site data). One `device_bash` call: `cd "$R" && python3 pricecheck/jsrun.py store runner`, paste the STORE
  call it prints on the same tab (`stored runner …`), then the same RUN call again (it may then answer
  `NEED_SCRIPT`, below). With `(site storage unavailable …)` or `EVAL_BLOCKED runner`: as `EVAL_BLOCKED` below.
- `NEED_SCRIPT <name> (…)`: nothing ran (first use on this site, a new script version, or cleared site
  data). One `device_bash` call: `cd "$R" && python3 pricecheck/jsrun.py store <name>`, paste the STORE
  call it prints into `javascript_tool` on the same tab (it answers `stored <name> …`), then paste the
  same RUN call again. `STORE REFUSED` means the pasted text didn't match the repo's hash: paste the
  STORE call again, verbatim.
- `EVAL_BLOCKED`, `STORE FAILED` or `NEED_SCRIPT … (site storage unavailable …)`: the site doesn't allow
  this. Paste `python3 pricecheck/jsrun.py inline <name>` instead: the filled-in script itself, which is
  the old way and gives the same result. Mention it in the chat message so the cache can be looked at.
- `RUNNER ERROR …`: the call was altered or the repo changed under it. Re-print the calls
  (`python3 pricecheck/jsrun.py full`) and use the new ones; never edit a call by hand.
- `SCRIPT ERROR …`: the script itself failed; treat it like a failed script (step 7, "If a whole script fails").

**Long results.** Claude in Chrome's JavaScript tool cuts a result at about 1,000 characters. So when a
script's lines are longer than that, the RUN or POLL call doesn't return them: it puts them on the tab as
its page and answers `PAGE <n> lines, <m> chars: …`. Then call `get_page_text` on that tab (in a batch
with whatever comes next on it) and use every line after its `---` line exactly as shown. Never read long
results in pieces by hand: that's slow and invites slips. The tab stays on the site, so its next scripts
still run there.

**SNKRDUNK lines come as a diff.** The `snkrdunk_full` (and the quick check's `snkrdunk_quick`) POLL writes each
card's sales and listing lists against the previous run's lines (e.g. `P^3.10,39480@261015,14.6`) and ends
with one `#B <mode> <base> <hash>` line. Pass them along exactly like the other lines, the `#B` line included,
in the order returned: `scripts/salesdiff.py` (inside the publish step) rebuilds the full lines and checks them
against the page's hash. If the publish step says the diff can't be rebuilt, print the full POLL with
`python3 pricecheck/jsrun.py poll snkrdunk_full --full`, paste it on tab S (it returns the same lines undiffed,
plus the `#B` line, as the page again: `get_page_text`) and publish with those lines instead.

## 2–4. Browser reads: the three sites at the same time, one tab each

Each site's script reads that site's pages one after another, at the same pace as before. The three
sites just run in parallel, in separate tabs, so the wait is the slowest site rather than the sum. All
reads happen in hidden iframes (the My-tier extractor scrolls its own tab, which is why it runs in the
tab you are working in) and wait on the Worker timer, so a background tab is fine. Rules:
- Use one tab per site, and pass that tab's id in every `javascript_tool` call: **S** = snkrdunk.com,
  **P** = psacard.com, **K** = pokeca-chart.com (created as the order below says). Never run a call on another site's tab: a POLL that answers
  `NOT STARTED` means you're on the wrong tab.
- Only one script per tab at a time: don't start the next RUN on a tab until its POLL has returned lines.
- Keep every returned line exactly as returned (the scripts' header comments document the codes);
  collect them for step 7.

Order. SNKRDUNK is the slowest site (about 4 minutes), so it starts first, and the steps you can
predict go into one `browser_batch` call each (its items run one after another on the tabs you name;
every item takes the same input as the tool alone, with an explicit `tabId`; item names: `navigate`,
`javascript_tool` with `action: "javascript_exec"`, `get_page_text`, `tabs_create_mcp` / `tabs_close_mcp` in Claude in
Chrome, `tabs_create` / `tabs_close` in the built-in browser). A batch stops only on a tool error, not
on a script's answer: read every item's output, and handle a `NEED_SCRIPT` / `MYTIER!` / sign-in answer
as below before going on (a POLL item after a RUN that didn't start answers `NOT STARTED`; ignore it).
1. **Open the three tabs.** One standalone `navigate` to `https://snkrdunk.com/apparels/<first id in PLAN>`
   **without a tabId** (it opens the first tab, S, and prints its id; only if your browser's `navigate`
   insists on a tabId, call `tabs_context` with createIfEmpty first). Then **batch 1**: `tabs_create` twice
   (once if the setup printed no `psa_pop` block). They give you tabs P and K.
2. **Batch 2: check the sites, then start everything** (all in one `browser_batch`). The first items check
   that PSA and pokeca-chart can be read *before* SNKRDUNK's 4-minute read starts (2026-10-23: two runs
   stopped half-way, on the VPN and on a blocked domain):
<!-- only:psapop -->
   - only when the setup printed a `psa_pop` block (skip if `PSAPOP = []`): `navigate` tab P to
     `https://www.psacard.com/pop/tcg-cards/156940`, then the `psa_check` call on tab P (printed with the
     setup). It throws on a Cloudflare page or a sign-in page, which stops the batch;
<!-- /only -->
   - `navigate` tab K to `https://pokeca-chart.com/gr/chart-index/`;
   - then the starts: the `snkrdunk_full` RUN call on tab S (`started N cards`; about 10 s per card with
     listings, 3 s without), the `psa_pop` RUN call on tab P when due (`started …`; about 5–8 s per set page),
     and the `pokeca_both` RUN call on tab K. It returns two lines, `IDX psa10 {…}` and `IDX raw {…}`;
   - `navigate` tab K to `https://pokeca-chart.com/gr/all-card/?sort=newest`, then the `mytier` RUN call on
     tab K. It returns one line, `MYTIER {…}`. If it returns `MYTIER! <error>`, leave that line out and
     mention it (the My-tier index is skipped this run);
   - last, on tab K: the `pokeca_scout` RUN call when Scout is due (step 3), otherwise the `pokeca_premium`
     RUN call (step 3 too). Scout goes first because it reads the all-card list on the tab itself, and a
     long result replaces the tab's page (see "Long results" above).
   **If batch 2 stops at a site check** (a `navigate` refused with "Navigation to this domain is not
   allowed", or `psa_check` throwing), nothing has started: stop there and say what blocked it and what to
   do (VPN off; sign in to psacard.com; for a refused domain, close the run and start a fresh one, or run
   the check from the Claude desktop app). Don't start SNKRDUNK alone. One exception: when it stopped with
   "Security check failed: the page navigated to a different domain" (the navigation finished late), send
   the `psa_check` call alone once more; if it answers `PSA page ok`, send the rest of batch 2.
   If a batch ever fails with a timeout, send its remaining items as separate calls.
3. **Tab K: Scout, then the slab premiums.**
<!-- only:scout -->
   - **Scout (step 4.4)** runs about every other day: when the setup printed `SCOUT = null`, skip it;
     otherwise it's required (don't `--skip scout` to save time; `scripts/freshness.py` flags a stale Scout
     page). POLL tab K with the `pokeca_scout` POLL call until it's done (about 1 minute: the list, then up
     to 20 card pages); its `PAGE …` answer means one batch: `get_page_text` on tab K (the lines), then the
     `pokeca_premium` RUN call on tab K. One `SCP …` line lists today's candidates, then one `SC {…}` (or
     `SC! …`) line per card page read. `full_update.py` saves them to `data/scout.json`, which feeds the
     site's Scout page (cards you don't track yet that fit your criteria and look cheap).
<!-- /only -->
   - **Slab premiums:** POLL tab K with the `pokeca_premium` POLL call until it's done (about 2 s per card),
     then `get_page_text` on tab K for the lines when it answered `PAGE …`. The `PREM …` lines carry each
     card's slab premium (PSA10 ÷ raw 美品) and its 6-month norm; `full_update.py` saves them to
     `data/premium.json`. A `PREM <id> !…` line (the card has no pokeca-chart page) is expected for a few
     cards; pass it along like the others.
<!-- only:psapop -->
4. **Tab P, collect the PSA pop report.** POLL tab P until it returns its `POP …` lines (or `PAGE …`:
   then `get_page_text` on tab P).
   Gem rate = PSA 10s ÷ total graded on the card's row. If the lines say `PSA sign-in page`, ask the
   user to sign in to psacard.com in the browser pane and re-run; if they say `Cloudflare check`, ask the user
   to turn the VPN off. Never type credentials and never try to pass a "verify you are human" check. If PSA
   can't be read this run, re-run `full_update.py` with `--skip psapop` and say why: the previous population
   is carried forward. Same precautions as SNKRDUNK: the user's own browser, only when a check is asked for,
   one page load per set. (PSA's pop report is the only source of PSA10 population and gem rate since
   2026-10-12; it needs a signed-in PSA account, and the browser pane keeps the login.)
<!-- /only -->
5. **Tab S, collect SNKRDUNK.** POLL tab S with the `snkrdunk_full` POLL call until it's done; it answers
   `PAGE …` (the lines are long), so the next batch starts with `get_page_text` on tab S. That batch: `tabs_close` tabs P and K (their lines are in), and, only if the setup
   printed a `snkrdunk_held` block, the `snkrdunk_held` RUN call on tab S followed by its POLL for the `H` /
   `HE` lines (about 5 s per item). Step 2b: `HELD` lists what the Holdings page needs a price for but the
   tracked cards don't cover: bought raw cards and raw/at-PSA pulls that aren't tracked (raw A-rank ask plus
   the last 30 days of one-copy A sales, turned into the raw A-rank price by `scripts/raw_price.py`), and
   sealed products with no pull logged (lowest ask); on Mondays also the Binder's cards, see step 6c. A
   sealed product with a pull is opened and no longer listed; its stored price is deleted by the publish
   step. Full checks only, never the quick check.

<!-- only:monday -->
On Mondays you can do step 6/6b's web searches (`pricecheck/steps/6-monday.md`) while the reads run.

<!-- /only -->
Each `IDX` line carries `volume_trend_suggested` (spiking if any day in the last 14 exceeds 2x the
prior-30-day average; rising/falling if the 7-day average is ±15% or the 14-day average ±10% vs the prior
30 days; else flat; changed 2026-10-08 after the old 14-day-only rule called +29% over 7 days "flat"),
which is used as-is. Only if you have a genuinely better read or a notable day worth describing, add
a line `VOL psa10 {"volume_trend": "...", "volume_note": "..."}` (or `VOL raw …`).

<!-- only:rebuild -->
**5b. Monthly model rebuild** (when the setup printed `REBUILD DUE`): follow
`pricecheck/steps/5b-models.md` after the price reads.

<!-- /only -->
<!-- only:monday -->
**6 / 6b. Mondays:** follow `pricecheck/steps/6-monday.md` (PSA tier status, `TIER` line; release calendar).

<!-- /only -->
## 7. Publish (one `device_bash` call)

Paste every line from steps 2, 2b, 3 and 4 (including SNKRDUNK's `#B` line and the `PREM`, `SCP` and `SC` lines; plus `TIER`, `VOL` and a `NOTE <text>` line for anything
unusual worth recording, all optional) verbatim into a heredoc:

```
R=$(ls -d "$HOME"/mnt/*/psa10-tracker "$HOME"/mnt/psa10-tracker 2>/dev/null | head -1); cd "$R" && python3 scripts/full_update.py - <<'EOF' 2>&1 | tee data/incoming/full-update.log | tail -120
<the lines>
EOF
```

The whole output is also kept in `data/incoming/full-update.log`: if the shown part starts after the `WARNINGS:` / `CHANGES` blocks, read them there (`grep -n -A30 "WARNINGS:\|CHANGES" data/incoming/full-update.log`) rather than skipping them.

Read the output. The snapshot was published if it says "Pushed N commit(s)." (each part of the publish commits on
its own and `full_update.py` pushes them together; `add_snapshot.py`'s "Committed locally" line is expected). If it
says the snapshot is byte-identical to an existing one, nothing new was published; say so. **Never put a token or
credential in any command**, and never ask the user for one.

**Completeness guard:** `full_update.py` refuses to publish when a planned step left no lines and names them: run
them and re-run with all lines. `--skip <names>` only for a step that genuinely failed (say which and why), never
to save time.

**When anything in this step fails** (git pull or push, an auth error, a refused publish, a script reporting a
changed page, or no linked computer): read `pricecheck/references/troubleshooting.md` and follow it.

Expected, don't report: tile-only cards (no PSA10 market) get "only 0 live listing(s)" warnings on
their A grade, and new-release cards have empty PSA10 results (see `pricecheck/references/state.md`).

Run one price check at a time. Overlapping runs published three identical snapshots on 2026-09-25.

**7b. Cards that stand out** (computer linked, after step 7 has published): `full_update.py` prints
`scripts/outliers.py`'s list itself (`CARDS THAT STAND OUT`, and `7b` in the FOLLOW-UPS line), so no
separate call is needed. If it lists cards, follow `pricecheck/steps/7b-outliers.md`; if it says nothing
stands out, skip it.

**Freshness.** Just before the follow-ups, `full_update.py` (and `quick_update.py`) print `STALE DATA` for any source the site shows that is older than its cadence (`python3 scripts/freshness.py` prints the whole table: source, last update, cadence, which check refreshes it). Refresh what the full check can in this run; name the rest in the chat message.

**Follow-ups.** `full_update.py`'s last line is `FOLLOW-UPS (…): …`, naming every step that still has work (with counts and the file to read for each) or `none`. Do 8b (evaluations) first: it's the step a long run is most tempted to drop. The run is not finished until each one listed is done. If the output was cut, `python3 scripts/full_update.py --followups` prints the blocks again. Read each listed step's file before doing it; it holds that step's full rules:

| Step | When | File |
|---|---|---|
| 1b | open card requests | `pricecheck/steps/1b-add-cards.md` |
| 1c | `PSAPOP MISSING` printed | `pricecheck/steps/1c-psa-pop-pages.md` |
| 2c | `BINDER IDS NEEDED` printed | `pricecheck/steps/2c-binder-ids.md` |
| 5b | `REBUILD DUE` printed | `pricecheck/steps/5b-models.md` |
| 6, 6b, 6c | Mondays (6c: Binder prices ride along in step 2b) | `pricecheck/steps/6-monday.md` |
| 7b | `CARDS THAT STAND OUT` lists cards | `pricecheck/steps/7b-outliers.md` |
| 8b | `EVALUATE NOW` / `SELL TIERS NOW` have cards (required, first) | `pricecheck/steps/8b-evaluate.md` |
| 8c | `WRITE STORIES NOW` has cards (required) | `pricecheck/steps/8c-stories.md` |
| 8d | `REVIEW DUE NOW` has cards | `pricecheck/steps/8d-review.md` |
| 8e | a major release was 4–10 days ago, not yet reported | `pricecheck/steps/8e-event-study.md` |
| 8g | `REFRESH VERDICTS NOW` (required) | `pricecheck/steps/8g-refresh-verdicts.md` |
| 8h | `SEALED INFO NOW` | `pricecheck/steps/8h-sealed.md` |
| 8i | `PSA BACKLOG NOW` (required when due) | `pricecheck/steps/8i-psa-backlog.md` |
| 8j | `WEEKLY RECAP NOW` (required when due) | `pricecheck/steps/8j-recap.md` |

The snapshot's JSON layout is in `pricecheck/references/output-shape.md` (only when you need it).

**End of the run.** After the last follow-up, one `device_bash` call: `cd "$R" && python3 scripts/runclock.py end`, with the `tabs_close` of tab S in the same message. It also pushes the follow-ups (analyses, insights, stories, hype readings): during a run those scripts only commit, so the site redeploys once instead of after each one (`scripts/deferpush.py`). Never skip this step; if its line says commits were NOT pushed, tell me.
It prints how long the run took (with the time it published) and logs it for comparison
(`python3 scripts/runclock.py history`). Put that line in the chat message with the tokens used.

**Chat message (full check):** keep it short. Say where it was published (snapshot file name, or "not published" and why). If `full_update.py` printed a `FOCUS WATCH` block, put it right after that, one line per focus card: status, lowest ask and its move, the gap to the target, the sales since the last check with prices, the BOOK DEPTH line (count within 3%, its change and the last reads), and every flag marked `!` (scripts/focus.py). Then pass on anything notable from the WARNINGS/CHANGES/FULL_UPDATE NOTES and from `add_snapshot.py`'s own warnings: a stale timestamp, the tracked-card set changing, cards whose verdict now needs a fresh review. Examples: very few live listings, a big favorite-count move, a volume spike, a site that couldn't be reached. The live site shows the rest. Include the My-tier index line `add_custom_index.py` printed (level and change), or say why it was skipped. On Mondays, add the release-calendar line from step 6b. Every card in `full_update.py`'s `WRITE STORIES NOW` block must appear as "Story added: …" or "NOT written: <name> — <concrete reason>". Every card in its `EVALUATE NOW` block must appear either as evaluated ("Evaluated <name>: …") or as "NOT evaluated: <name> — <concrete reason, e.g. evaluation skill couldn't reach pokeca-chart>"; being new is not a reason. Also report any card requests handled in step 1b ("Added: <name>" / "Couldn't add #<n>: <reason>") one line per card analysed in step 7b, one line per card evaluated in step 8b or re-evaluated in step 8d, one line per PSA pop page found in step 1c, and one line per story written in step 8c, e.g. "Evaluated <name>: Watch, tiers ¥X / ¥Y / ¥Z, 2 predictions recorded".

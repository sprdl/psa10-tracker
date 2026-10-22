# Troubleshooting a price check

Read this only when the procedure or a script points here (`pricecheck/FULL-CHECK.md` step 7,
`pricecheck/QUICK-CHECK.md` Q4). Split out of the procedures on 2026-10-23, so every run doesn't print them.

## Publishing (full_update.py / quick_update.py)

**Completeness guard:** `full_update.py` refuses to publish when a planned step left no lines (IDX, MYTIER, POP when PSA pop pages were due, PREM, SCP/SC) and names the missing steps. Go back, run them, and re-run with all lines. Only when a step genuinely failed (the site is down, a script reports a changed page), re-run with `--skip <names>` (e.g. `--skip scout`) and say in the chat message which step was skipped and why. Never use `--skip` to save time.

Read the output. Each part of the publish (snapshot, My-tier index, premium, holdings prices, scout) commits on its own, and `full_update.py` pushes them together once at the end (`add_snapshot.py`'s "Committed locally" line is expected). The snapshot was published if it says "Pushed N commit(s)."; a failed push says so and nothing reached the site. If it says the snapshot is
byte-identical to an existing one, nothing new was published; say so. The repo has its own
credential file configured. **Never put a token or credential in any command**, and never ask the
user for one. If a push fails with an auth error, tell the user the token in `.psa10-git-credentials`
may have expired. If `git pull --ff-only` or the push fails because the history diverged, don't force
anything; tell the user to run `git pull` then `git push` in the repo on their Mac. If git fails with
`unable to unlink ... .git/index.lock: Operation not permitted`, call
`device_request_delete_permission` for that folder once, then `rm -f .git/index.lock` and re-run.

The quick check's publish (`quick_update.py`) follows the same git rules.

## What full_update.py does

`full_update.py` keeps the input in `data/incoming/full-raw.txt`, pulls, decodes the lines into
`data/incoming/full-raw.json` (exactly the raw shape `assemble.py` has always taken), runs
`assemble.py` with `--prev` = the live snapshot (printing WARNINGS and CHANGES), publishes with
`add_snapshot.py`, saves the My-tier index with `add_custom_index.py` (using the PSA10 index value
from the `IDX` line) and stores any newly found photo URL. It prints `FULL_UPDATE NOTES` for things
to mention, such as a PSA pop page that couldn't be read. `--dry-run` decodes and assembles
without publishing.

## No linked computer

**If the computer isn't linked:** run steps 2–4 the same way with the plan from a public clone
(`git clone --depth 1 https://github.com/sprdl/psa10-tracker.git /tmp/pt && cd /tmp/pt && python3
pricecheck/start.py --mode full`, using the RUN calls it prints), then write the lines to a file and run
`python3 scripts/full_update.py <file> --dry-run` in the clone. `SendUserFile` its
`data/incoming/latest-run.json` and tell the user to publish it from the repo on their Mac with
`python3 scripts/add_snapshot.py ~/Downloads/latest-run.json`.

## A whole script fails

**If a whole script fails** (it reports that a page's structure changed), read the affected cards
by hand with the single-page scripts (`python3 pricecheck/jsrun.py run <name>` for `snkrdunk_base`, `grade_tiles`,
`snkrdunk_listings` or `pokeca_index`, on the page each reads; a long result answers `PAGE …`, read with
`get_page_text`; PSA pop by hand, never a hand-edited `psa_pop.js` call) per
`pricecheck/references/manual-fallback.md`, and flag it at the end so the script can be fixed. The
old raw-JSON path still works: `python3 pricecheck/scripts/assemble.py RAW.json --out
data/incoming/latest-run.json --prev <latest snapshot>`, then
`python3 scripts/add_snapshot.py data/incoming/latest-run.json`.

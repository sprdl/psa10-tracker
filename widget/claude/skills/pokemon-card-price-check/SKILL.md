---
name: "pokemon-card-price-check"
description: "Check SNKRDUNK and pokeca-chart.com for current PSA10/raw-A prices and market index on the user's tracked Pokemon cards. Run when the user asks to check prices on their tracked cards."
---

# Pokemon card price check (SNKRDUNK + pokeca-chart.com + PSA pop report)

*Local copy for Claude Code runs on the Mac (menu bar): commands without the repo-finding prefix, no heredocs (see CLAUDE.md), so a run you started never stops for a permission question. Keep the rest in step with the claude.ai skill.*

Manual, on-demand check. Run it only when the user asks ("check my card prices", "run the pokemon price check", "quick price check"). It has two modes, **full** and **quick**. Run one price check at a time: overlapping runs published three identical snapshots on 2026-09-25.

Everything runs in the user's real browser: the built-in browser (`mcp__remote-devices__Claude_Browser__*`) when it's available, Claude in Chrome (`mcp__claude-in-chrome__*`) otherwise. The in-page scripts only read the rendered DOM of the sites' own pages (hidden same-origin iframes, one page after another, the same pages a person would open) and make no fetch/XHR requests. Never use curl, requests, or any HTTP client. If no browser tool works, tell the user you can't reach the sites right now; never guess prices.

**PSA population (full check).** PSA10 population and gem rate come from PSA's own pop report (psacard.com/pop), read in the user's browser like the other sites: one set page per set, only during a check the user asked for. It is the only population source (altema was dropped on 2026-10-12), so a card PSA doesn't list yet (e.g. a brand-new print) simply has no population until it does. The pop report needs a signed-in PSA account; the user signed in in the built-in browser pane. If the script reports `PSA sign-in page`, ask the user to sign in to psacard.com in that browser; on a Cloudflare / "verify you are human" check, ask the user to turn the VPN off. Never type credentials and never try to pass such a check. **Never put a token or credential in any command**, and never ask the user for one.

All the machinery lives in the user's tracker repo (`psa10-tracker`, on the linked computer at `$R`): the procedures (`pricecheck/FULL-CHECK.md`, `pricecheck/QUICK-CHECK.md`, `pricecheck/steps/*.md`), the in-page scripts and the publishing scripts. Improving the procedure or a script means committing to the repo, not changing this skill.

## Start: one call

One `device_bash` call (add `--mode full` or `--mode quick` if the user asked for one):
```
python3 pricecheck/start.py
```
It prints the status line (`check_status.py`, including `eval_due`), open card requests (`card_requests.py list`), `MODE: full|quick (why)` (full for the JST day's first check, quick after that, unless asked; open requests and `eval_due` don't change the mode), then **the procedure for that mode in full, followed by today's plan and ready-to-paste browser calls**. Send it in the same message as one `ToolSearch` that loads the browser tools the procedure uses (`browser_batch`, `navigate`, `javascript_tool`, `get_page_text`, the tab tools): the two don't depend on each other, and every round trip costs time. Tell the user in one short line which mode is running and why (e.g. "Quick check: today's full check already ran at 08:58"), then follow the printed procedure exactly. Don't `cat` the procedure again; it's in that output. Read a `pricecheck/steps/*.md` file only when the procedure or the FOLLOW-UPS line names it.

Browser calls come from `pricecheck/jsrun.py`: paste them verbatim, never edit one by hand. They verify the cached script and today's arguments by SHA-256 before anything runs; the procedure explains the `NEED_SCRIPT` / `STORE` / `inline` responses.

If the computer isn't linked, a quick check can't run (it builds on the repo's latest snapshot and publishes there). Say so, and offer a full check from a public clone (`git clone --depth 1 https://github.com/sprdl/psa10-tracker.git /tmp/pt && cd /tmp/pt && python3 pricecheck/start.py --mode full`), which hands over a file instead (FULL-CHECK step 7).

## New cards: added, published and evaluated in the same run

A card the user asked for (an open "Add card" request, a restore) is **added, published and evaluated by the same price check**, quick or full. The evaluation is part of the price check, not a follow-up to offer: never end a run with "the card has no tiers yet, I can evaluate it now or leave it". On 2026-10-10 a run did exactly that and the user had to ask separately.

1. **Add** it: `pricecheck/steps/1b-add-cards.md` (the quick check runs it as Q0). `card_requests.py add` also puts it on the evaluation queue (`data/eval_queue.json`).
2. **Publish** it with this run's snapshot: re-print the browser calls after adding (`python3 pricecheck/jsrun.py full`, or `quick`) so they include it; the full check's plan and the quick check's card list both include tracked cards that aren't published yet.
3. **Evaluate** it, right after publishing and before every other follow-up: the update script prints an `EVALUATE NOW` block (`scripts/eval_queue.py`) listing queued cards first, whatever their PSA10 market, then cards whose PSA10 market just formed. For each (at most 3 per run):
   - one `device_bash` call: `python3 scripts/eval_context.py <snkrdunk_id>` (everything this run already has for the card, plus `--odds <prices>` for tier reachability);
   - load the `pokemon-tcg-card-evaluation` skill with the Skill tool and follow it end to end, reusing that output; a card with no PSA10 ask yet gets a `defer` verdict with reasoning, which is a complete evaluation;
   - apply it with that skill's step 8 (`apply_analysis.py`), which saves it and takes the card off the queue. During a run it only commits; `runclock.py end` pushes it with the other follow-ups.
   The full rules are in `pricecheck/steps/8b-evaluate.md`.
4. The chat message says "Added: <name>" and "Evaluated <name>: <verdict>, tiers ¥X / ¥Y / ¥Z, N predictions recorded" (or "Defer: no PSA10 market yet"). If an evaluation genuinely can't finish (a site down, the JSON refused), say "NOT evaluated: <name> — <reason>"; the card stays queued and the next check does it.

## Finishing

The run is not finished until the `FOLLOW-UPS` line the update script prints last says `none`, or every step it lists is done (8b first). Then one `device_bash` call: `python3 scripts/runclock.py end` (close your tabs in the same message). Skip it only when `quick_update.py` printed a `RUN CLOCK` block: with nothing left to do it already ended the run and printed the line. Otherwise never skip it: besides timing the run, it pushes every follow-up committed during the run (evaluations, insights, stories, hype readings), so until then the site doesn't show them. If its line says commits were NOT pushed, say so in the chat. Write the chat message as the procedure describes, and end it with how long the price check took (the ⏱ total line) and how many tokens you used.
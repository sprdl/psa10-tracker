# Step 1b: add requested cards

Part of the full price check (`pricecheck/FULL-CHECK.md`, which holds the shared rules: credentials, publishing, the chat message). Read this file when `card_requests.py list` shows open requests (full check; the quick check runs it as Q0).

**1b. Add requested cards** (only if the mode check listed open requests; the quick check runs this same step as Q0). For each request:
- `snkrdunk_id` is null: run `python3 scripts/card_requests.py reject <number> "no SNKRDUNK product URL found — open the card on snkrdunk.com and paste its address"`.
- Otherwise, print the two RUN calls once (one `device_bash` call: `python3 pricecheck/jsrun.py run grade_tiles && python3 pricecheck/jsrun.py run snkrdunk_base`; they're the same for every card, as these scripts take no arguments), `navigate` the tab to the card's URL, then one `browser_batch` on that tab with three `javascript_tool` items, in this order:
  1. the photo: `[...document.images].map(i=>i.currentSrc||i.src).find(s=>s.includes('upload_bg_removed'))||''`;
  2. the `grade_tiles` RUN call (`TILES {…}`);
  3. the `snkrdunk_base` RUN call, last, because a long result replaces the tab's page: it answers `BASE {…}` or, usually, `PAGE …`, and then `get_page_text` on that tab gives the `BASE {…}` line.
  A RUN item answering `NEED_RUNNER` / `NEED_SCRIPT`: store it as in FULL-CHECK's "Browser calls" section (`jsrun.py store runner` / `jsrun.py store <name>`, the STORE call on that tab), then repeat the batch. Never paste the script files themselves, and never read a long result in pieces (the JavaScript tool cuts results at about 1,000 characters).
  - If the base result has no `title` or errors (`BASE! …`: the page doesn't exist), reject with the reason.
  - Otherwise, in one `device_bash` call from the repo: `python3 scripts/card_requests.py add <number> --name "<base.title>" --image "<photo URL, if found>"` (add `--psa-url … --psa-no … --psa-name …` if you already found its PSA pop page, step 1c). This writes the entry, **queues the card for its evaluation** (`data/eval_queue.json`), commits, pushes, and closes the issue with a confirmation. The same credential rules as step 7 apply. A request for a card that was removed earlier restores it and queues it too (its old tiers may be stale).

  After the requests are handled, run `python3 pricecheck/plan.py` and `python3 pricecheck/jsrun.py full` again (one `device_bash` call) and use the new RUN calls: the new card is now in `data/tracked_cards.json`, so the plan includes it. **Adding a card commits you to evaluating it in this same run** (step 8b): the run isn't finished, and you don't offer it as an optional next step, until the evaluation is applied or you can name a concrete reason it couldn't be.
- For a new card that already sells as a PSA10: find its PSA pop page as in step 1c and save it (`card_requests.py set <snkrdunk_id> psa_pop_url=… psa_pop_no=… psa_pop_name=…`). A brand-new print PSA doesn't list yet stays without population until it does.

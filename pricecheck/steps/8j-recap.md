# Step 8j: weekly recap note

Part of the full price check (`pricecheck/FULL-CHECK.md`, which holds the shared rules: credentials, publishing, the chat message). Read this file when FOLLOW-UPS lists `8j` (`WEEKLY RECAP NOW`).

**8j. Weekly recap note** (full checks only, computer linked, after step 7 has published; **required when due**, i.e. on the first full check from Monday until it's written). The site's Weekly recap page (`#/recap`, and a card on the Overview) computes every number itself for a Mon–Sun JST week: owned and watched cards' moves, the indices, purchases, `events.json` releases. What it can't compute is the news, so this step writes a short note for the week that just ended into `data/recaps.json`. `full_update.py` prints `WEEKLY RECAP NOW` and lists "8j weekly recap" in FOLLOW-UPS when it's due; `scripts/recap.py due` decides, not you.
1. One `device_bash` call: `cd "$R" && python3 scripts/recap.py facts`. It prints the week's numbers (indices, every card's move, owned cards marked *, the releases already on the page).
2. Research what happened that week and what's coming in the next 7 days, with `WebSearch` / `WebFetch` only (never SNKRDUNK or pokeca-chart pages): the official sites (pokemon-card.com, www.30th.pokemon-card.com, pokemon.co.jp news), PSA Japan announcements, reliable Japanese card-news sites (e.g. tcg-portal.jp, dengekionline, famitsu). Look for new product announcements, release dates, reprints or restocks, PSA service changes, regulation/rotation news and anything that plausibly explains the week's biggest moves. 2–4 searches are enough.
3. Write the note in plain English. `headline`: one sentence on what defined the week **for Philipp's cards** (e.g. "A market-wide rally lifted every owned card except Mega Gengar MA"). `takeaway` (optional): 1–3 sentences on what it means for buying or selling. `happened` / `ahead`: 0–5 items each, `{d, title, text, source}`; `ahead` items may have `d: null` for an announced but undated product. Never invent a cause: if no news explains a move, say the move was broad and no single news item was found. Label rumours as rumours. Don't repeat items the page already shows (purchases, `events.json` releases, the price and index numbers); refer to them instead. If something belongs on the release calendar, also add it with `scripts/events.py`.
4. Save with one `device_bash` call (same credential rules as step 7):
```
cd "$R" && python3 scripts/recap.py save - <<'JSON'
{"week": "<Monday YYYY-MM-DD>", "headline": "...", "takeaway": "...", "happened": [{"d": "YYYY-MM-DD", "title": "...", "text": "...", "source": "https://..."}], "ahead": [{"d": "YYYY-MM-DD", "title": "...", "text": "...", "source": "https://..."}]}
JSON
```
It checks the dates fall in the right week, commits and pushes. Chat message: one line, "Weekly recap written for <week>: <headline>".

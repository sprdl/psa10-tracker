# Step 8c: write the story for cards that have none

Part of the full price check (`pricecheck/FULL-CHECK.md`, which holds the shared rules: credentials, publishing, the chat message). Read this file when FOLLOW-UPS lists `8c` (`WRITE STORIES NOW` has cards).

**8c. Write the story for cards that have none** (full checks only, computer linked, after step 7 has published). **Required, not optional**, like 8b: `full_update.py` ends by printing a `WRITE STORIES NOW` block with these cards, and the run is not finished while it lists cards you haven't written a story for (a 2026-10-03 run left a new card without one). Every tracked card gets a Story tab on its card page and a tile on the Stories page from `data/stories.json`: who illustrated it, what the art shows, how it connects to other cards or the games, set context and a few facts. A card added in step 1b arrives without one.
1. One `device_bash` call: `cd "$R" && python3 scripts/set_story.py --missing`. It lists tracked cards without a story (usually none).
2. For each listed card (at most 3 per run; name any others in the chat message), research with `WebSearch` / `WebFetch` only. Never use SNKRDUNK or pokeca-chart pages for this. Start with the illustrator: the official card database (pokemon-card.com; the card's page lists イラストレーター; search e.g. `<card name> <number> イラストレーター`), then Bulbapedia or Serebii. Then the art itself and its context: Famitsu's SAR/AR round-ups, PokeBeach reveal posts, Bleeding Cool's "The Cards of Pokémon TCG" series, the official set page, the illustrator's own posts. Worth looking for: connected artworks (panels that join into one picture, day/night pairs, a trainer and Pokémon pairing), the Pokédex lore or game/anime/film moment it depicts, the set's release date and theme, the English counterpart's name and number, the illustrator's other well-known cards.
3. Write it in plain English. `art`: 2–4 sentences on what the artwork shows and details worth noticing. `story`: 1–3 sentences on connections or references, or null. `set`: 1–2 sentences. `trivia`: 1–3 verifiable facts. No prices or market talk. Every claim must come from a listed source. Never guess: leave out what you can't verify, and set `illustrator` to null if no source credits one. `confidence`: "high" when the illustrator is confirmed and the scene description has 2+ sources, "medium" when the scene rests on one source.
4. Save each with one `device_bash` call (same credential rules as step 7):
```
cd "$R" && python3 scripts/set_story.py <snkrdunk_id> <<'EOF'
{"illustrator": "...", "illustrator_ja": null, "art": "...", "story": "...", "set": "...", "trivia": ["..."], "english": "...", "sources": [{"title": "...", "url": "https://..."}], "confidence": "high"}
EOF
```
It checks the fields, refuses SNKRDUNK/pokeca-chart sources and commits (the push follows with `runclock.py end`). Mention each story in the chat message in one line ("Story added: <name>, illustrated by <artist>").

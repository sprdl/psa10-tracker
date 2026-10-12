# Step 7b: write the analysis for cards that stand out

Part of the full price check (`pricecheck/FULL-CHECK.md`, which holds the shared rules: credentials, publishing, the chat message). Read this file when `scripts/outliers.py` lists cards.

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

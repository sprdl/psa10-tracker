# Step 8g: refresh written verdicts that no longer match the price

Part of the full price check (`pricecheck/FULL-CHECK.md`, which holds the shared rules: credentials, publishing, the chat message). Read this file when FOLLOW-UPS lists `8g` (`REFRESH VERDICTS NOW`).

**8g. Refresh written verdicts that no longer match the price** (full checks only, computer linked, after 8b and 8d). **Required.** `full_update.py` prints a `REFRESH VERDICTS` block: cards whose lowest ask has moved 5%+ from the price their written verdict was based on (at most 3 per run, biggest move first; `python3 scripts/review_due.py --text` prints it again). Cards 8d is reviewing this run are excluded, since that rewrites them anyway. For each listed card, rewrite only the verdict from this run's data, keeping the tiers:
- `tag`: the live zone of today's ask against the existing tiers, with the guardrails applied (correction or event rule: a Buy-zone price becomes `watch`; keep `defer` only if its reason still holds).
- `label`: `"<Tag> — <one-line takeaway>"`.
- `reasoning`: 3–5 sentences with today's numbers: the ask and its move since the old verdict, the recent sales range, depth and activity, the market (My-tier index 30-day move), what changed versus the old text, and what would change the call. Never copy a number from the old text without re-checking it today.
- `predictions`: only if the reasoning states a probability (each with price and deadline, as in the evaluation skill). Otherwise leave the key out; the old predictions stay on the Track record and keep being scored.

Save each with one `device_bash` call (same credential rules as step 7):
```
cd "$R" && python3 scripts/apply_analysis.py - <<'JSON'
{"<SNKRDUNK url>": {"verdict": {"tag": "...", "label": "...", "reasoning": "..."}}}
JSON
```
`apply_analysis.py` dates the new verdict and resets its reference price to today's ask, so the card leaves the list. One line per card in the chat message: "Verdict refreshed: <name> <old tag> → <new tag> (<move>)".

# Step 8f: Mercari for cards near the limit

Part of the full price check (`pricecheck/FULL-CHECK.md`, which holds the shared rules: credentials, publishing, the chat message). Read this file when FOLLOW-UPS lists `8f` (`MERCARI NOW`).

**8f. Mercari for cards near the limit** (full and quick checks, computer linked, after step 7 has published). `full_update.py` ends with a `MERCARI` block. When it says `MERCARI NOW`, follow `pricecheck/MERCARI.md` (one script call on jp.mercari.com, then `scripts/mercari.py` saves `data/mercari.json`); when it says `none due`, skip it. Alerts it prints (`** AT/UNDER LIMIT`, `** AUCTION ending`) go first in the chat message, with the item link.

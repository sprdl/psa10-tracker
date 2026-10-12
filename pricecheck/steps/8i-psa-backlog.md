# Step 8i: PSA backlog update

Part of the full price check (`pricecheck/FULL-CHECK.md`, which holds the shared rules: credentials, publishing, the chat message). Read this file when FOLLOW-UPS lists `8i` (`PSA BACKLOG NOW`).

**8i. PSA backlog: new update on PSA's page?** (full checks only, computer linked, after step 7 has published; **required when it is due**). PSA posts a backlog update every other Tuesday at https://www.psacard.com/info/backlog-tracker. The tracker's Market page and Submissions page show it (`data/psa_backlog.json`), because PSA reopens the Value tiers once the backlog is under 5M units. `full_update.py` prints `PSA BACKLOG NOW` when a look is due and `PSA BACKLOG: none due (…)` otherwise, and lists "8i PSA backlog" in FOLLOW-UPS. **The schedule is enforced by `scripts/psa_backlog.py due`, not by you; don't look on a run that says none due.** Its rule:
- An update is expected 14 days after the newest stored one. With 2026-10-06 stored, the update is expected 2026-10-20 and **the first look is on 2026-10-21**, on that day's first full check.
- If the page has nothing newer, the look repeats on **every day's first full check** (a second full check the same day doesn't repeat it) until a newer update is there.
- When a newer update is saved, the next one is expected 14 days after *its* heading date, so the cadence returns to every other Tuesday (an update posted late still carries its own date; the next look starts the day after the next expected date).

When it is due:
1. One `WebFetch` of `https://www.psacard.com/info/backlog-tracker` with this prompt: `Return verbatim, without paraphrasing or summarizing: the heading of the NEWEST dated update (like "October 6, 2026 Update") and the complete first paragraph under it; then the heading of the second newest update and its first sentence.`
2. Save it, one `device_bash` call, pasting the fetched heading and paragraph verbatim (nothing added):
```
R=$(ls -d "$HOME"/mnt/*/psa10-tracker "$HOME"/mnt/psa10-tracker 2>/dev/null | head -1); cd "$R" && python3 scripts/psa_backlog.py from-page - <<'EOF'
<heading>
<paragraph>
EOF
```
The script reads the date and the figure itself and checks them against what is stored (the update's own "down from X million" must match the last stored reading; a jump of more than 3M is refused). It prints one of:
- `SAVED: 7.4M on 2026-10-20 …`: the reading, the projection and the page are updated and pushed (same credential rules as step 7). Report the new figure and the scenario lines it prints.
- `NO NEW UPDATE …`: it records that you looked (shown on the Market page) and pushes. Nothing else to do; it is due again on the next day's first full check.
- `CHECK BY HAND …`: nothing saved. Do what it says (read the page's earlier updates and use `python3 scripts/psa_backlog.py add YYYY-MM-DD <millions>` for each missed one, oldest first), or tell the user.

If `WebFetch` fails or returns something that isn't the update text, open the page in the browser on a normal tab (`navigate`, then `get_page_text`) and use that text the same way. **If a Cloudflare or "verify you are human" page appears, stop: don't try to pass it, work around it or use curl** (psacard.com has been blocked to browser automation before, probably because of a VPN; on 2026-10-10 both WebFetch and the built-in browser read the page fine without one; see `pricecheck/references/state.md`). Remind Philipp to turn the VPN off if it's on. Say so in the chat message and ask the user to paste the newest update's text or a screenshot of it; the same `from-page -` command takes pasted text. One page load per look.

Chat message: one line, e.g. "PSA backlog: 7.4M on 10/20 (−0.8M); the 5M line is crossed around 12/01 to 12/15 on the current pace" (use the scenario lines the script prints), or "PSA backlog: no new update yet (looked 10/21; will look again tomorrow)".

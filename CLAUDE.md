# PSA10 tracker: local Claude Code runs

This file is for Claude Code sessions started in this repo on the Mac, mainly by the menu bar
widget (`widget/run-check.sh`). The project skills in `.claude/skills/` (a link to `widget/claude/skills/`) are copies of the claude.ai
skills `pokemon-card-price-check` and `pokemon-tcg-card-evaluation`, written for the Claude desktop
app's tools. Here, read them with this mapping:

**You are on the linked computer.** Never conclude "the computer isn't linked" or offer the public
clone fallback: the repo is right here.

| The skills / procedures say | Use here |
|---|---|
| `device_bash` / "one `device_bash` call" | the **Bash** tool (one call each, same command) |
| `$R`, `R=$(ls -d "$HOME"/mnt/*/psa10-tracker …); cd "$R" && …` | **drop the prefix**: the working directory already is the repo root, so run what follows `cd "$R" &&` as its own command (e.g. `python3 pricecheck/start.py --mode quick`; a `git pull --ff-only --quiet` before it goes in a separate Bash call). A command with `$(…)` or `"$HOME"` can't be matched against `.claude/settings.json`'s allow list, so it asks for confirmation on every run and stalls an unattended check. Same for any other `$R/…` path: write it relative to the repo root |
| `mcp__remote-devices__Claude_Browser__*` (built-in browser) | **Claude in Chrome**: `mcp__claude-in-chrome__*` |
| `tabs_context` / `tabs_create` / `tabs_close` | `tabs_context_mcp` (with `createIfEmpty: true`) / `tabs_create_mcp` / `tabs_close_mcp` |
| `javascript_tool` | `mcp__claude-in-chrome__javascript_tool` with `action: "javascript_exec"`, `text`, `tabId` (a number) |
| `navigate` | `mcp__claude-in-chrome__navigate` |
| `ToolSearch select:mcp__remote-devices__Claude_Browser__…` | load the `mcp__claude-in-chrome__` equivalents instead, if they're deferred |
| "load the `pokemon-tcg-card-evaluation` skill with the Skill tool" | same: it's a project skill here |
| delete permission / stale `.git/*.lock` files | not an issue locally: git removes its own locks. If git says a lock file exists and no other git is running, `rm -f` that lock |

**Tabs (full check).** Open the three tabs (S, P, K) right at the start: `tabs_context_mcp` with
`createIfEmpty: true` for the first, then `tabs_create_mcp` twice, and pass each tab's id explicitly.
If a tab can't be created, call `tabs_context_mcp` once and retry once. If you still only have two
tabs, put PSA and pokeca-chart on the second tab one after the other (PSA first: `psa_pop` RUN, POLL
until done, then the pokeca steps) and never wait for SNKRDUNK's tab: on 2026-10-13 PSA waited for
SNKRDUNK and the run took 22 minutes. Say in the chat message that only two tabs were available.

**A page script that reads nothing** (every listing empty, a "not found" error on every card): the site
changed its markup. Fix the selectors in `pricecheck/scripts/`, keeping the old ones as a fallback
in case the old markup comes back), commit, then re-print the calls with
`python3 pricecheck/jsrun.py full` (new hashes; the RUN answers `NEED_SCRIPT`, so STORE it first).

Everything else in the procedures applies unchanged: paste the `jsrun.py` browser calls verbatim,
one price check at a time, never type credentials, PSA sign-in or a Cloudflare check → ask me.
Close the tabs you opened when the run ends.

**Finishing.** End with the procedure's chat message and the `runclock.py end` line. You can't see
your own token count here; leave it out (I can run `/cost`).

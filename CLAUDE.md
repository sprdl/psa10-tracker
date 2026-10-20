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
| `browser_batch` | `mcp__claude-in-chrome__browser_batch`: items `{name, input}` with the names `navigate`, `javascript_tool`, `tabs_create_mcp`, `tabs_close_mcp` and an explicit `tabId` (a number) in every page item. Tested 2026-10-20: a batch of two 38 s POLL-length calls (76 s) runs fine |
| `javascript_tool` | `mcp__claude-in-chrome__javascript_tool` with `action: "javascript_exec"`, `text`, `tabId` (a number) |
| `navigate` | `mcp__claude-in-chrome__navigate` |
| `ToolSearch select:mcp__remote-devices__Claude_Browser__…` | load the `mcp__claude-in-chrome__` equivalents instead, if they're deferred |
| "load the `pokemon-tcg-card-evaluation` skill with the Skill tool" | same: it's a project skill here |
| a command with a heredoc (`… <<'EOF'` + lines + `EOF`), e.g. publishing with `quick_update.py -` / `full_update.py -`, `apply_analysis.py -`, `hype.py --ref -`, `set_insight.py`, `set_story.py`, `recap.py save -` | **never a heredoc here.** First save the lines with the **Write** tool to `data/incoming/<script>-in.txt` (git-ignored), then run the same command reading that file: `python3 scripts/quick_update.py - < data/incoming/quick_update-in.txt 2>&1 \| tee data/incoming/quick-update.log \| tail -50`. A long heredoc is too long for Claude Code's command checker ("Parser aborted … over-length"; anything over 10,000 characters always), so it can't be pre-approved. `start.py` prints the procedures already rewritten this way; read step files with `python3 pricecheck/start.py --show pricecheck/steps/<file>` to get them rewritten too |
| `WebSearch` / `WebFetch` (stories, insights, Monday calendar, PSA backlog, weekly recap) | allowed as they are |
| delete permission / stale `.git/*.lock` files | not an issue locally: git removes its own locks. If git says a lock file exists and no other git is running, `rm -f` that lock |

**First message.** Send the Skill call, the Bash call `python3 pricecheck/start.py --mode <mode>` and one
`ToolSearch` loading the Chrome tools you'll need (`browser_batch`, `navigate`, `javascript_tool`,
`tabs_context_mcp`, `tabs_create_mcp`, `tabs_close_mcp`) together in one message: they don't depend on
each other. Throughout the run, put independent calls in one message and predictable browser steps in
one `browser_batch`, as the procedures say: each round trip costs several seconds.

**Tabs (full check).** Open the three tabs (S, P, K) right at the start, as FULL-CHECK's order says: a
standalone `navigate` without a tabId opens S (it creates the tab and prints its id), and the batch that
starts SNKRDUNK creates P and K with `tabs_create_mcp`. Pass each tab's id explicitly.
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
Close the tabs you opened when the run ends (in the same message as `runclock.py end`, or right after the
publish when `quick_update.py` already ended the run clock).

**Unattended: nothing may ask.** The menu bar starts the run with `--permission-mode dontAsk` (`acceptEdits` on an older Claude Code): every tool call `.claude/settings.json` doesn't allow is refused instead of asked. A refused call means the command has a form the run doesn't use (a heredoc, `$(…)`, `"$HOME"`, `find … -delete`, `curl`): don't retry it in another shape; use the form above, or skip that step and name it in the chat message. Don't use AskUserQuestion. Stop and say what you need only when the check genuinely can't go on (PSA sign-in, a Cloudflare check, a site down). To wait, use the POLL calls, not `sleep`.

**Finishing.** Run `python3 scripts/runclock.py end` after the last follow-up (skip it when `quick_update.py`
printed a `RUN CLOCK` block: with no follow-ups it already ended the run): it also pushes everything the
follow-ups committed during the run (they don't push on their own while the run clock runs). End with the
procedure's chat message and the `runclock.py end` line. You can't see
your own token count here; leave it out (I can run `/cost`).

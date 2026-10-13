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
| `$R`, `R=$(ls -d "$HOME"/mnt/*/psa10-tracker …)` | works as written (`~/mnt/psa10-tracker` links to this repo); `R` is also simply the repo root, the working directory |
| `mcp__remote-devices__Claude_Browser__*` (built-in browser) | **Claude in Chrome**: `mcp__claude-in-chrome__*` |
| `tabs_context` / `tabs_create` / `tabs_close` | `tabs_context_mcp` (with `createIfEmpty: true`) / `tabs_create_mcp` / `tabs_close_mcp` |
| `javascript_tool` | `mcp__claude-in-chrome__javascript_tool` with `action: "javascript_exec"`, `text`, `tabId` (a number) |
| `navigate` | `mcp__claude-in-chrome__navigate` |
| `ToolSearch select:mcp__remote-devices__Claude_Browser__…` | load the `mcp__claude-in-chrome__` equivalents instead, if they're deferred |
| "load the `pokemon-tcg-card-evaluation` skill with the Skill tool" | same: it's a project skill here |
| delete permission / stale `.git/*.lock` files | not an issue locally: git removes its own locks. If git says a lock file exists and no other git is running, `rm -f` that lock |

Everything else in the procedures applies unchanged: paste the `jsrun.py` browser calls verbatim,
one price check at a time, never type credentials, PSA sign-in or a Cloudflare check → ask me.
Close the tabs you opened when the run ends.

**Finishing.** End with the procedure's chat message and the `runclock.py end` line. You can't see
your own token count here; leave it out (I can run `/cost`).

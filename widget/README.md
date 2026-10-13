# PSA10 menu bar widget (macOS)

A 🃏 in the menu bar that starts a price check with one click, and asks at **08:00, 14:00 and 19:00**
whether to start one. Runs use **Claude Code** on the Mac (not the desktop app):

- **Full check → Sonnet**, **Quick check → Haiku** (`FULL_MODEL` / `QUICK_MODEL` in `lib.sh`)
- Each run opens a Terminal window with the session, so you can watch it and step in (PSA sign-in…)
- Git runs natively on the Mac, so no delete-permission prompts and no stale `.git/*.lock` files;
  `run-check.sh` also clears locks older than 5 minutes (only when no git is running) before each run
- One run at a time: the buttons are greyed out and prompts are skipped while a check runs, including
  checks started from the desktop app (it watches `data/incoming/runclock.json`)

## Menu

```
🃏
├ Full check (Sonnet)
├ Quick check (Haiku)
├ Last snapshot / last full check / suggested mode / next prompt
├ Ask me now…
├ Open tracker site
└ Run history
```

The prompt dialog offers **Skip / Quick (Haiku) / Full (Sonnet)**, with the mode `check_status.py`
suggests as the default. It closes itself after 15 minutes. It's skipped if a snapshot was published
in the last 60 minutes. If the Mac was asleep at a prompt time, it still comes up within 2 hours after.
Times and windows are at the top of `lib.sh`.

## Setup (once)

1. **SwiftBar**: `brew install --cask swiftbar` (or https://swiftbar.app). Start it once; set it to
   launch at login in its preferences.
2. **Claude Code** (skip if `claude --version` works): `curl -fsSL https://claude.ai/install.sh | bash`
3. **Installer**: `bash ~/Documents/"My JavaScript Projects"/psa10-tracker/widget/install.sh`
4. **Claude Code sign-in and Chrome**: in Terminal, `cd` into the repo and run `claude`, then
   - `/login` with your claude.ai account (Chrome integration needs it; an API key won't work),
   - make sure the **Claude in Chrome** extension is installed and signed in to the same account,
   - `/chrome` → status should show Enabled / Installed. Then `/exit`.
5. **Chrome sign-ins**: sign in to **psacard.com** once in Chrome (until now it was the desktop app's
   built-in browser). In the extension, allow snkrdunk.com, pokeca-chart.com, psacard.com and
   jp.mercari.com when it first asks ("allow all actions on this site").
6. **First click**: macOS asks whether SwiftBar may control Terminal, and maybe whether Terminal /
   SwiftBar may access the Documents folder. Allow them.

## Files

| File | What |
|---|---|
| `swiftbar-plugin.1m.sh` | stub copied to SwiftBar's plugin folder; runs `menu.sh` every minute |
| `menu.sh` | draws the menu, starts `ask.sh` at the prompt times |
| `ask.sh` | the "new run?" dialog (`ask.sh --force` to test) |
| `start.sh` | menu button → new Terminal window running `run-check.sh` |
| `run-check.sh` | one run: lock, stale git locks, `git pull`, `claude --chrome --model … ` |
| `lib.sh` | settings and shared functions |
| `install.sh` | one-time setup; safe to re-run |
| `claude/` | Claude Code project settings and skills, linked into `.claude/` by `install.sh` |

Outside the repo: `~/.psa10/` (links, PATH, run lock, prompt bookkeeping) and `~/mnt/psa10-tracker`
(a link to the repo, so the procedures' `$HOME/mnt/...` commands work unchanged).

**Permissions.** `widget/claude/settings.json` (linked as `.claude/settings.json` by the installer) lets the run use python3, read-only git, the
lock cleanup and Claude in Chrome without asking. Anything else still asks in the Terminal window.

**Skills.** `widget/claude/skills/` (linked as `.claude/skills/`) holds copies of the claude.ai skills `pokemon-card-price-check` and
`pokemon-tcg-card-evaluation`; `CLAUDE.md` maps their desktop-app tool names to Claude Code's. When
you change one of those skills on claude.ai, copy the new SKILL.md here too.

**Uninstall.** Delete `psa10.1m.sh` from SwiftBar's plugin folder, `~/.psa10` and `~/mnt/psa10-tracker`.

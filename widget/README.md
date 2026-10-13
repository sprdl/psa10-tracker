# PSA10 menu bar app (macOS)

A 🃏 in the menu bar that starts a price check with one click, and asks at **08:00, 14:00 and 19:00**
whether to start one, in a small bubble that drops from the icon. Runs use **Claude Code** on the
Mac (not the desktop app):

- **Full check → Sonnet**, **Quick check → Haiku** (`FULL_MODEL` / `QUICK_MODEL` in `lib.sh`)
- Each run opens a Terminal window with the session, so you can watch it and step in (PSA sign-in…)
- Git runs natively on the Mac, so no delete-permission prompts and no stale `.git/*.lock` files;
  `run-check.sh` also clears locks older than 5 minutes (only when no git is running) before each run
- One run at a time: the buttons are disabled and prompts are skipped while a check runs, including
  checks started from the desktop app (it watches `data/incoming/runclock.json`)

## The bubble

Click 🃏 (🃏⏳ while a check runs):

```
 PSA10 price check
 [Quick · Haiku] [Full · Sonnet]      ← the suggested mode is highlighted
 ───────────────────────────────
 Last snapshot: today 08:44 (full) · 5h21m ago
 Last full check: today 08:44
 Suggested: quick · next prompt 19:00
 ───────────────────────────────
 Tracker site   Run history      Quit
```

At a prompt time the same bubble opens by itself, titled **Start a new price check?**, with a
**Skip** button. It closes when you click anywhere else or after 15 minutes. No prompt if a snapshot
was published in the last 60 minutes; if the Mac was asleep at a prompt time, it still comes up
within 2 hours after. Times and windows are at the top of `lib.sh`.

## Setup (once)

1. **Command Line Tools** (for the Swift compiler), if `xcrun --find swiftc` fails: `xcode-select --install`
2. **Claude Code**, signed in with `/login` (claude.ai account) and connected to Chrome (`/chrome`)
3. **Installer**: `bash ~/Documents/"My JavaScript Projects"/psa10-tracker/widget/install.sh`
   It builds the app into `~/.psa10/PSA10Bar.app`, starts it and sets it to start at login.
   Run it again after a `git pull` that changes `app/PSA10Bar.swift`.
4. **Chrome sign-ins**: psacard.com (and SNKRDUNK) in Chrome; allow the sites in the Claude extension
5. **First click**: macOS asks whether PSA10Bar may access the Documents folder and control Terminal.
   Allow both (System Settings → Privacy & Security → Files and Folders / Automation, if missed).

## Files

| File | What |
|---|---|
| `app/PSA10Bar.swift` | the menu bar app: icon and bubble only; all logic is in the scripts |
| `status.sh` | status lines for the bubble, and whether a prompt is due (the app runs it every minute) |
| `start.sh` | bubble buttons → new Terminal window running `run-check.sh` (or the run history) |
| `run-check.sh` | one run: lock, stale git locks, `git pull`, `claude --chrome --model …` |
| `history.sh` | recent run times (`scripts/runclock.py history`) |
| `lib.sh` | settings and shared functions |
| `install.sh` | one-time setup; safe to re-run |
| `claude/` | Claude Code project settings and skills, linked into `.claude/` by `install.sh` |

Outside the repo: `~/.psa10/` (the app, links, PATH, run lock, prompt bookkeeping, build log),
`~/Library/LaunchAgents/com.psa10.bar.plist` (start at login) and `~/mnt/psa10-tracker` (a link to
the repo, so the procedures' `$HOME/mnt/...` commands work unchanged).

**Permissions.** `widget/claude/settings.json` (linked as `.claude/settings.json` by the installer)
lets the run use python3, read-only git, the lock cleanup and Claude in Chrome without asking.
Anything else still asks in the Terminal window.

**Skills.** `widget/claude/skills/` (linked as `.claude/skills/`) holds copies of the claude.ai skills
`pokemon-card-price-check` and `pokemon-tcg-card-evaluation`; `CLAUDE.md` maps their desktop-app tool
names to Claude Code's. When you change one of those skills on claude.ai, copy the new SKILL.md here too.

**Uninstall.** `launchctl bootout gui/$(id -u)/com.psa10.bar`, then delete
`~/Library/LaunchAgents/com.psa10.bar.plist`, `~/.psa10` and `~/mnt/psa10-tracker`.

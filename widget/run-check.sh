#!/bin/bash
# Runs one price check in this Terminal window with Claude Code:
#   full  -> Sonnet,  quick -> Haiku   (models are set in lib.sh)
# Started by the menu bar widget (open_run in lib.sh); can also be run by hand:
#   ~/.psa10/widget/run-check.sh quick
set -u
. "$(dirname "$0")/lib.sh"

mode="${1:-}"
case "$mode" in
  full)  model="$FULL_MODEL" ;;
  quick) model="$QUICK_MODEL" ;;
  *) echo "usage: run-check.sh full|quick"; exit 2 ;;
esac

if m=$(running_mode); then
  echo "A ${m:-price} check is already running. One run at a time (overlapping runs publish duplicate snapshots)."
  sleep 5; exit 1
fi

if ! command -v "$CLAUDE_BIN" >/dev/null 2>&1; then
  echo "Claude Code (claude) not found. Install it, then run ~/.psa10/widget/install.sh again."
  read -r -p "Press Return to close." _; exit 1
fi

echo "$$ $mode $(date +%s)" > "$PIDFILE"
trap 'rm -f "$PIDFILE"' EXIT
date "+%Y-%m-%d %H:%M $mode" >> "$STATE/runs.log"

cd "$REPO" || exit 1
printf '\033]0;PSA10 %s check (%s)\007' "$mode" "$model"
clear_stale_git_locks
git pull --ff-only --quiet || echo "(git pull failed; the check pulls again at its start)"

prompt="Run a $mode price check on my tracked cards with the pokemon-card-price-check skill (pass --mode $mode to start.py). This is a local Claude Code run: follow CLAUDE.md for how the skill's tools map here. Don't ask whether to start; the run was requested from the menu bar widget."

"$CLAUDE_BIN" --chrome --model "$model" --permission-mode acceptEdits "$prompt"

echo
echo "Session ended. You can close this window."

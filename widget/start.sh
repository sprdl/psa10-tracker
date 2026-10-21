#!/bin/bash
# Actions of the menu bar app:
#   start.sh full|quick   new Terminal window running run-check.sh (one run at a time)
#   start.sh history      Terminal window with the recent run times
#   start.sh show         bring up the running check's (minimized) window
#   start.sh resume       reopen the last run's Claude Code session (claude --resume)
. "$(dirname "$0")/lib.sh"
case "${1:-}" in
  full|quick) open_run "$1" ;;
  history)
    osascript >/dev/null <<OSA
tell application "Terminal"
  activate
  do script "/bin/bash '$WIDGET_DIR/history.sh'"
end tell
OSA
    ;;
  show)
    if ! run_window show; then
      if running_mode >/dev/null; then
        notify "The run's window isn't open any more. If the run still shows as going, it clears itself within a minute."
      else
        notify "No run is going any more (its window was closed), so the widget is back to normal."
      fi
    fi ;;
  resume)
    sid=$(cat "$STATE/last-session" 2>/dev/null) || exit 1
    osascript >/dev/null <<OSA
tell application "Terminal"
  activate
  do script "cd '$REPO' && exec '$CLAUDE_BIN' --chrome --resume $sid"
end tell
OSA
    ;;
  *) echo "usage: start.sh full|quick|history|show|resume"; exit 2 ;;
esac

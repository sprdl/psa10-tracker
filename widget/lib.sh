# Shared by the menu bar widget's scripts. Sourced, not run.
#
#   ~/.psa10/widget  -> this folder (symlink made by install.sh, so paths have no spaces)
#   ~/.psa10/state/  -> run lock, prompt bookkeeping, logs (never committed)
#   ~/.psa10/env     -> PATH and the claude binary, captured from your login shell by install.sh

WIDGET_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
REPO="$(cd "$WIDGET_DIR/.." && pwd -P)"
STATE="$HOME/.psa10/state"
mkdir -p "$STATE"
[ -f "$HOME/.psa10/env" ] && . "$HOME/.psa10/env"
CLAUDE_BIN="${CLAUDE_BIN:-claude}"

# Models per mode, and the times (JST, the Mac's local time) the widget asks about a new run.
FULL_MODEL="sonnet"
QUICK_MODEL="haiku"
PROMPT_TIMES="08:00 14:00 19:00"
PROMPT_WINDOW_MIN=120   # after waking from sleep, a missed prompt is still shown up to this long after its time
RECENT_RUN_MIN=60       # no prompt if a snapshot was published this recently

PIDFILE="$STATE/running.pid"
RUNCLOCK="$REPO/data/incoming/runclock.json"   # exists while any price check runs (desktop app runs too)

# Prints "full" / "quick" / "" if a check is running, nothing otherwise. Exit 0 = running.
running_mode() {
  # 1. A run started from the widget whose Claude session is still in its first minutes
  #    (start.py hasn't started the run clock yet).
  if [ -f "$PIDFILE" ]; then
    local pid mode started
    read -r pid mode started < "$PIDFILE"
    if kill -0 "$pid" 2>/dev/null; then
      if [ $(( $(date +%s) - ${started:-0} )) -lt 900 ] && [ ! -f "$RUNCLOCK" ]; then
        echo "$mode"; return 0
      fi
    else
      rm -f "$PIDFILE"
    fi
  fi
  # 2. The repo's run clock: start.py writes it, runclock.py end removes it. Ignore it after 3 h
  #    (a run that was abandoned without `runclock.py end`).
  if [ -f "$RUNCLOCK" ] && [ -n "$(find "$RUNCLOCK" -mmin -180 2>/dev/null)" ]; then
    python3 -c 'import json,sys;print(json.load(open(sys.argv[1])).get("mode",""))' "$RUNCLOCK" 2>/dev/null
    return 0
  fi
  return 1
}

# One JSON line: latest snapshot, last full check, suggested mode (scripts/check_status.py).
status_json() {
  (cd "$REPO" && python3 scripts/check_status.py 2>/dev/null | head -1)
}

json_get() {  # json_get '<json>' key
  python3 -c 'import json,sys
try: v=json.loads(sys.argv[1]).get(sys.argv[2])
except Exception: v=None
print("" if v is None else v)' "$1" "$2"
}

# Minutes since the latest snapshot (from its file name, YYYYMMDD-HHMM.json, JST).
minutes_since_snapshot() {
  local latest="$1"
  python3 - "$latest" <<'PY'
import sys, datetime as D
try:
    t = D.datetime.strptime(sys.argv[1][:13], "%Y%m%d-%H%M")
    print(int((D.datetime.now() - t).total_seconds() // 60))
except Exception:
    print(99999)
PY
}

# git locks left behind by an interrupted git (or by the desktop app, which can't delete files).
# Only when no git process is running and the lock is older than 5 minutes.
clear_stale_git_locks() {
  pgrep -x git >/dev/null 2>&1 && return 0
  find "$REPO/.git" -name '*.lock' -mmin +5 -print -delete 2>/dev/null | sed 's/^/removed stale git lock: /'
  find "$REPO/.git/objects" -name 'tmp_obj_*' -mmin +5 -delete 2>/dev/null
  return 0
}

notify() {  # notify "message"
  osascript -e "display notification \"$1\" with title \"PSA10 price check\"" >/dev/null 2>&1
}

# Opens a Terminal window running the check, minimized and without taking the focus. It closes by
# itself when the run is done; "Show window" in the bubble brings it up (start.sh show).
open_run() {  # open_run full|quick
  local mode="$1"
  if m=$(running_mode); then
    notify "A ${m:-price} check is already running. One run at a time."
    return 1
  fi
  osascript >/dev/null <<OSA
tell application "Terminal"
  set t to do script "exec /bin/bash '$WIDGET_DIR/run-check.sh' $mode"
  delay 0.3
  set tt to tty of t
  repeat with w in windows
    if tty of tab 1 of w is tt then set miniaturized of w to true
  end repeat
end tell
OSA
}

# The run's Terminal window (by its tty, saved by run-check.sh): show / close it.
run_window() {  # run_window show|close [tty]
  local tt="${2:-$(cat "$STATE/run-tty" 2>/dev/null)}"
  [ -n "$tt" ] || return 1
  if [ "$1" = show ]; then
    osascript >/dev/null 2>&1 <<OSA
tell application "Terminal"
  repeat with w in windows
    if tty of tab 1 of w is "$tt" then
      set miniaturized of w to false
      set index of w to 1
    end if
  end repeat
  activate
end tell
OSA
  else
    osascript >/dev/null 2>&1 <<OSA
tell application "Terminal"
  repeat with w in windows
    if tty of tab 1 of w is "$tt" then close w
  end repeat
end tell
OSA
  fi
}

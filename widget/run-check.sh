#!/bin/bash
# Runs one price check in this Terminal window with Claude Code:
#   full  -> Sonnet,  quick -> Haiku   (models are set in lib.sh)
# Started from the menu bar app (open_run in lib.sh), minimized; can also be run by hand:
#   ~/.psa10/widget/run-check.sh quick
#
# The window closes by itself when the run is done: the run clock (data/incoming/runclock.json)
# appeared and was removed again by `runclock.py end`, and Claude then finished its last message
# (the Stop hook, hooks/stop.sh). If the run needs you before that (a permission question, PSA
# sign-in, an error), the Notification hook shows a notice and the icon turns 👻❗; the window stays.
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
  run_window show "$(tty)"
  read -r -p "Press Return to close." _; exit 1
fi

me_tty=$(tty)
echo "$$ $mode $(date +%s)" > "$PIDFILE"
echo "$me_tty" > "$STATE/run-tty"
rm -f "$STATE/attention" "$STATE/stopped" "$STATE/done"
touch "$STATE/run-start"
# On any exit (run finished, Claude quit, window closed): drop this run's process marker, and its run
# clock too if the run stopped before `runclock.py end` (an API error, Chrome not connected). Otherwise
# the menu bar keeps showing "check is running" for up to 3 hours. Only a run clock written after this
# run started is removed, so a desktop-app run's clock is never touched.
cleanup() {
  rm -f "$PIDFILE" "$STATE/attention"
  if [ -f "$RUNCLOCK" ] && [ "$RUNCLOCK" -nt "$STATE/run-start" ]; then
    rm -f "$RUNCLOCK"
    date "+%Y-%m-%d %H:%M $mode stopped before the end (run clock cleared)" >> "$STATE/runs.log"
    # follow-ups committed during the run wait for `runclock.py end` to push them (scripts/deferpush.py): push them now
    (cd "$REPO" && python3 scripts/deferpush.py >> "$STATE/runs.log" 2>&1)
  fi
}
trap cleanup EXIT
trap 'exit 1' HUP INT TERM
date "+%Y-%m-%d %H:%M $mode" >> "$STATE/runs.log"

cd "$REPO" || exit 1
clear_stale_git_locks
git pull --ff-only --quiet || echo "(git pull failed; the check pulls again at its start)"

session=$(uuidgen | tr 'A-Z' 'a-z')
echo "$session" > "$STATE/last-session"
export PSA10_RUN=1   # the hooks only act inside widget runs

# Watcher: ends the Claude session once the run is done (see the header).
(
  seen=0
  while sleep 3; do
    if [ -f "$RUNCLOCK" ]; then seen=1; continue; fi
    [ "$seen" = 1 ] || continue
    ended=$(( $(date +%s) - 6 ))
    for _ in $(seq 60); do                      # Claude's final message: at most 3 minutes
      [ "$(cat "$STATE/stopped" 2>/dev/null || echo 0)" -ge "$ended" ] && break
      sleep 3
    done
    sleep 2
    touch "$STATE/done"
    pkill -TERM -P $$                           # claude (and this watcher)
    exit 0
  done
) &

prompt="Run a $mode price check on my tracked cards with the pokemon-card-price-check skill. This is a local Claude Code run in the repo root, already pulled: follow CLAUDE.md for how the skill's tools map here. Your first Bash call is exactly: python3 pricecheck/start.py --mode $mode   Write every later command the same way, without the skill's R=\$(ls -d …); cd \"\$R\" && prefix (a command with \$(…) stops the run for a permission question). Don't ask whether to start; the run was requested from the menu bar. Unattended: never ask me anything unless the check genuinely can't go on (PSA sign-in, a Cloudflare check, a site down); a tool call answered with a permission denial is not allowed here, so don't retry it in another form: use the way CLAUDE.md describes, or skip that step and name it in the chat message."

# dontAsk: anything .claude/settings.json doesn't allow is refused instead of asked, so a run you started never stops
# for a permission question; the run reports a refused step in its chat message. Older Claude Code versions without
# that mode fall back to acceptEdits (file edits in the repo go through, other unlisted actions still ask).
perm=acceptEdits
"$CLAUDE_BIN" --help 2>/dev/null | grep -q dontAsk && perm=dontAsk
"$CLAUDE_BIN" --chrome --model "$model" --permission-mode "$perm" --session-id "$session" "$prompt"

if [ -f "$STATE/done" ]; then
  summary=$(python3 -c 'import json,sys
r=json.loads(open(sys.argv[1]).read().splitlines()[-1]); t=r["total_s"]
print(r["mode"].capitalize()+" check done in %dm%02ds" % (t//60, t%60))' "$REPO/data/incoming/run_times.jsonl" 2>/dev/null || echo "Price check done")
  notify "$summary. Details: Open last run in the 👻 bubble."
  rm -f "$PIDFILE" "$STATE/attention"
  # Close this window a moment after this script has exited (no "terminate processes?" question).
  nohup /bin/bash -c "sleep 1; . '$WIDGET_DIR/lib.sh'; run_window close '$me_tty'" >/dev/null 2>&1 &
  exit 0
fi

echo
echo "Session ended. You can close this window."

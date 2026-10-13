#!/bin/bash
# The "start a new run?" dialog. The menu bar plugin starts it in the background at the prompt
# times in lib.sh (08:00, 14:00, 19:00); run it by hand to test: ~/.psa10/widget/ask.sh
set -u
. "$(dirname "$0")/lib.sh"

running_mode >/dev/null && exit 0

st=$(status_json)
suggested=$(json_get "$st" suggested_mode); suggested=${suggested:-full}
last_full=$(json_get "$st" last_full_jst)
latest=$(json_get "$st" latest)
since=$(minutes_since_snapshot "$latest")
[ "${1:-}" != "--force" ] && [ "$since" -lt "$RECENT_RUN_MIN" ] && exit 0

if [ "$suggested" = "quick" ]; then
  why="Suggested: Quick (today's full check ran at ${last_full:11:5})"
  default="Quick (Haiku)"
else
  why="Suggested: Full (no full check yet today)"
  default="Full (Sonnet)"
fi
if [ "$since" -lt 99999 ]; then
  h=$((since / 60)); mm=$((since % 60))
  ago="Last snapshot: ${latest:9:2}:${latest:11:2} (${h}h${mm}m ago)"
else
  ago=""
fi

answer=$(osascript <<OSA 2>/dev/null
with timeout of 1000 seconds
  display dialog "Start a new PSA10 price check?" & return & return & "$why" & return & "$ago" ¬
    with title "PSA10 Tracker" buttons {"Skip", "Quick (Haiku)", "Full (Sonnet)"} ¬
    default button "$default" cancel button "Skip" giving up after 900 with icon note
end timeout
OSA
)

case "$answer" in
  *"gave up:true"*) exit 0 ;;
  *"Full (Sonnet)"*)  open_run full ;;
  *"Quick (Haiku)"*) open_run quick ;;
  *) exit 0 ;;
esac

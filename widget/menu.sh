#!/bin/bash
# SwiftBar menu for the PSA10 tracker. SwiftBar runs the stub plugin (swiftbar-plugin.1m.sh) every
# minute, which runs this. Besides drawing the menu it starts the "new run?" dialog at the prompt times.
set -u
. "$(dirname "$0")/lib.sh"
SELF="$HOME/.psa10/widget"   # no spaces, for SwiftBar's bash= parameter

# ---- prompts: each prompt time once per day, while it's at most PROMPT_WINDOW_MIN old ----
today=$(date +%F); now_min=$(( 10#$(date +%H) * 60 + 10#$(date +%M) ))
asked="$STATE/asked-$today"
find "$STATE" -name 'asked-*' ! -name "asked-$today" -delete 2>/dev/null
for t in $PROMPT_TIMES; do
  tm=$(( 10#${t%:*} * 60 + 10#${t#*:} ))
  if [ "$now_min" -ge "$tm" ] && [ "$now_min" -lt $((tm + PROMPT_WINDOW_MIN)) ] && ! grep -qx "$t" "$asked" 2>/dev/null; then
    echo "$t" >> "$asked"
    nohup /bin/bash "$WIDGET_DIR/ask.sh" >/dev/null 2>&1 </dev/null &
    disown 2>/dev/null
  fi
done

# ---- next prompt time ----
next=""
for t in $PROMPT_TIMES; do
  tm=$(( 10#${t%:*} * 60 + 10#${t#*:} ))
  if [ "$tm" -gt "$now_min" ]; then next="$t"; break; fi
done
[ -z "$next" ] && next="tomorrow ${PROMPT_TIMES%% *}"

# ---- menu ----
st=$(status_json)
latest=$(json_get "$st" latest)
latest_mode=$(json_get "$st" latest_mode)
suggested=$(json_get "$st" suggested_mode)
last_full=$(json_get "$st" last_full_jst)

if rm_=$(running_mode); then
  echo "🃏⏳ | sfsize=13"
  echo "---"
  echo "${rm_:-Price} check running… | color=#888888"
  echo "Full check (Sonnet) | color=#888888"
  echo "Quick check (Haiku) | color=#888888"
else
  echo "🃏"
  echo "---"
  echo "Full check (Sonnet) | bash=$SELF/start.sh param1=full terminal=false refresh=true"
  echo "Quick check (Haiku) | bash=$SELF/start.sh param1=quick terminal=false refresh=true"
fi
echo "---"
[ -n "$latest" ] && echo "Last snapshot: ${latest:4:2}/${latest:6:2} ${latest:9:2}:${latest:11:2} (${latest_mode}) | size=12"
[ -n "$last_full" ] && echo "Last full check: ${last_full:5:5} ${last_full:11:5} | size=12"
[ -n "$suggested" ] && echo "Suggested now: $suggested | size=12"
echo "Next prompt: $next | size=12"
echo "---"
echo "Ask me now… | bash=$SELF/ask.sh param1=--force terminal=false"
echo "Open tracker site | href=https://sprdl.github.io/psa10-tracker/"
echo "Run history | bash=$SELF/history.sh terminal=true"

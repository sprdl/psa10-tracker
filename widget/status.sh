#!/bin/bash
# Status for the menu bar app (PSA10Bar), as key=value lines. The app runs this every minute.
# It also decides when a prompt is due: each prompt time in lib.sh once per day, within
# PROMPT_WINDOW_MIN after it, and only if no check is running and none ran in the last RECENT_RUN_MIN.
set -u
. "$(dirname "$0")/lib.sh"

today=$(date +%F); now_min=$(( 10#$(date +%H) * 60 + 10#$(date +%M) ))
asked="$STATE/asked-$today"
find "$STATE" -name 'asked-*' ! -name "asked-$today" -delete 2>/dev/null

st=$(status_json)
latest=$(json_get "$st" latest)
suggested=$(json_get "$st" suggested_mode)
last_full=$(json_get "$st" last_full_jst)
since=$(minutes_since_snapshot "$latest")

if rmode=$(running_mode); then running=1; else running=0; rmode=""; fi

due=0; next=""
for t in $PROMPT_TIMES; do
  tm=$(( 10#${t%:*} * 60 + 10#${t#*:} ))
  if [ "$now_min" -ge "$tm" ] && [ "$now_min" -lt $((tm + PROMPT_WINDOW_MIN)) ] && ! grep -qx "$t" "$asked" 2>/dev/null; then
    echo "$t" >> "$asked"
    [ "$running" = 0 ] && [ "$since" -ge "$RECENT_RUN_MIN" ] && due=1
  fi
  [ -z "$next" ] && [ "$tm" -gt "$now_min" ] && next="$t"
done
[ -z "$next" ] && next="tomorrow ${PROMPT_TIMES%% *}"

if [ -n "$latest" ]; then
  if [ "${latest:0:8}" = "$(date +%Y%m%d)" ]; then d="today"; else d="${latest:4:2}/${latest:6:2}"; fi
  latest_label="$d ${latest:9:2}:${latest:11:2} ($(json_get "$st" latest_mode))"
else
  latest_label=""
fi
if [ -n "$last_full" ]; then
  if [ "${last_full:0:10}" = "$today" ]; then lf="today ${last_full:11:5}"; else lf="${last_full:5:2}/${last_full:8:2} ${last_full:11:5}"; fi
else
  lf=""
fi
if [ "$since" -lt 99999 ]; then ago="$((since / 60))h$(printf %02d $((since % 60)))m ago"; else ago=""; fi

attention=0
[ "$running" = 1 ] && [ -f "$STATE/attention" ] && attention=1
last_run=$(python3 - "$REPO/data/incoming/run_times.jsonl" <<'PY2' 2>/dev/null
import json, sys, datetime as D
try:
    r = json.loads(open(sys.argv[1], encoding="utf-8").read().splitlines()[-1])
    s = D.datetime.fromisoformat(r["start"]); t = int(r["total_s"]); e = s + D.timedelta(seconds=t)
    day = "today" if s.date() == D.datetime.now(s.tzinfo).date() else s.strftime("%m/%d")
    print(f"{r['mode']} · {t // 60}m{t % 60:02d}s · {day} {s:%H:%M}–{e:%H:%M}")
except Exception:
    pass
PY2
)
can_resume=0; [ -s "$STATE/last-session" ] && can_resume=1

echo "running=$running"
echo "attention=$attention"
echo "last_run=$last_run"
echo "can_resume=$can_resume"
echo "running_mode=$rmode"
echo "suggested=${suggested:-full}"
echo "latest=$latest_label"
echo "ago=$ago"
echo "last_full=$lf"
echo "next=$next"
echo "due=$due"

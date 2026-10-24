#!/bin/bash
# Claude Code Notification hook: Claude needs you (permission question, or waiting for an answer).
# Only inside menu bar runs (PSA10_RUN=1): marks the run (icon 👻❗, "The run needs you" in the
# bubble) and shows a macOS notification. Prints nothing.
[ "${PSA10_RUN:-}" = 1 ] || exit 0
msg=$(python3 -c 'import json,sys
try: print(json.load(sys.stdin).get("message","")[:120])
except Exception: print("")' 2>/dev/null)
touch "$HOME/.psa10/state/attention"
msg=${msg:-Claude is waiting for you}
# passed as an argument, never spliced into the AppleScript (2026-10-24 security audit)
osascript -e 'on run argv' -e 'display notification ((item 1 of argv) & " — click 👻 → Show window") with title "Ghost Bid: price check needs you" sound name "Glass"' -e 'end run' "$msg" >/dev/null 2>&1
exit 0

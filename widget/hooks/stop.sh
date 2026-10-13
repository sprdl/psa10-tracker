#!/bin/bash
# Claude Code Stop hook: Claude finished a turn. Only inside menu bar runs (PSA10_RUN=1):
# records the time, so run-check.sh can close the session once the run is done.
[ "${PSA10_RUN:-}" = 1 ] || exit 0
cat >/dev/null
date +%s > "$HOME/.psa10/state/stopped"
exit 0

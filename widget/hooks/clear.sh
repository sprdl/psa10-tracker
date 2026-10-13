#!/bin/bash
# Claude Code UserPromptSubmit / PostToolUse hook: you answered or a tool ran, so the run no longer
# waits for you. Clears the 🃏❗ mark. Prints nothing (a UserPromptSubmit hook's output would be
# added to the conversation).
[ "${PSA10_RUN:-}" = 1 ] || exit 0
cat >/dev/null
rm -f "$HOME/.psa10/state/attention"
exit 0

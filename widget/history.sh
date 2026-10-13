#!/bin/bash
# Menu item "Run history": how long recent runs took (scripts/runclock.py).
. "$(dirname "$0")/lib.sh"
cd "$REPO" && python3 scripts/runclock.py history 15

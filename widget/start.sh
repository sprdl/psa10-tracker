#!/bin/bash
# Menu button: start a full or quick check in a new Terminal window.
. "$(dirname "$0")/lib.sh"
open_run "${1:-quick}"

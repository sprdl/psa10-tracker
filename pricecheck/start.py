#!/usr/bin/env python3
"""
First (and only) setup call of a price check: one device_bash call instead of four.

    R=$(ls -d "$HOME"/mnt/*/psa10-tracker "$HOME"/mnt/psa10-tracker 2>/dev/null | head -1); cd "$R" && git pull --ff-only --quiet; python3 pricecheck/start.py [--mode full|quick]

It prints, in order:
  1. the status line (scripts/check_status.py) and open card requests (scripts/card_requests.py list);
  2. MODE: the mode to run (the one asked for with --mode, else full for the JST day's first check, quick after);
  3. the procedure to follow for that mode (pricecheck/FULL-CHECK.md or pricecheck/QUICK-CHECK.md), in full;
  4. full: today's plan (pricecheck/plan.py), the browser calls (pricecheck/jsrun.py full) and the
     PSA backlog schedule (scripts/psa_backlog.py due); quick: the browser call (pricecheck/jsrun.py quick).
It also starts the run clock (scripts/runclock.py). Nothing is published or changed in the repo.
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def sh(*cmd):
    r = subprocess.run([sys.executable, *cmd], cwd=ROOT, text=True, capture_output=True)
    out = (r.stdout or "") + (r.stderr or "")
    if r.returncode:
        out += f"\n(!) {' '.join(cmd)} exited with {r.returncode}"
    return out.rstrip("\n")


def main():
    a = sys.argv[1:]
    asked = None
    for i, x in enumerate(a):
        if x == "--mode" and i + 1 < len(a):
            asked = a[i + 1]
        elif x.startswith("--mode="):
            asked = x[7:]
    if asked not in (None, "full", "quick"):
        sys.exit("ERROR: --mode must be full or quick")

    status = sh("scripts/check_status.py")
    print(status)
    print(sh("scripts/card_requests.py", "list"))
    try:
        st = json.loads(status.splitlines()[0])
    except Exception:  # noqa: BLE001
        st = {}
    mode = asked or st.get("suggested_mode") or "full"
    why = "asked for" if asked else ("first check of the JST day" if mode == "full" else f"today's full check already ran ({st.get('last_full_jst')})")
    print(f"\nMODE: {mode} ({why})")
    print(sh("scripts/runclock.py", "start", mode))

    doc = ROOT / "pricecheck" / ("FULL-CHECK.md" if mode == "full" else "QUICK-CHECK.md")
    print(f"\n======== {doc.relative_to(ROOT)} (follow it) ========\n")
    print(doc.read_text(encoding="utf-8").rstrip("\n"))
    print("\n======== today's setup output ========\n")
    if mode == "full":
        print(sh("pricecheck/plan.py"))
        print()
        print(sh("pricecheck/jsrun.py", "full"))
        print()
        print(sh("scripts/psa_backlog.py", "due"))
    else:
        print(sh("pricecheck/jsrun.py", "quick"))


if __name__ == "__main__":
    main()

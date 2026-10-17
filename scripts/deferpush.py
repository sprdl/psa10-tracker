#!/usr/bin/env python3
"""
One push per price check for the follow-up steps (2026-10-16).

During a run (the run clock data/incoming/runclock.json exists, started by pricecheck/start.py within the last
MAX_HOURS), the follow-up scripts (apply_analysis.py, set_insight.py, set_story.py, hype.py) commit locally and
don't pull or push: before, each one pushed on its own, up to six pushes in 90 seconds, and every push redeployed the
whole site. `runclock.py end`, the run's last step, then pushes them all at once (push_pending).
full_update.py / quick_update.py still push the snapshot right away, so prices reach the site without waiting.

Outside a run (no run clock, or a stale one from a run that stopped) everything pushes as before. Commits left
unpushed by a run that stopped are pushed by the next script that pushes (git push sends them all), or by hand:

    python3 scripts/deferpush.py          # push any local commits now
"""
import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JST = timezone(timedelta(hours=9))
MAX_HOURS = 3


def active(root=ROOT):
    """True inside a price-check run: commit now, push at the end."""
    p = Path(root) / "data" / "incoming" / "runclock.json"
    try:
        start = datetime.fromisoformat(json.loads(p.read_text(encoding="utf-8"))["start"])
    except Exception:  # noqa: BLE001  (no clock, unreadable: not in a run)
        return False
    return datetime.now(JST) - start < timedelta(hours=MAX_HOURS)


def git(root, *a):
    return subprocess.run(["git", *a], cwd=root, text=True, capture_output=True)


def push_pending(root=ROOT):
    """Push local commits, if any (pull --rebase first: a GitHub Action may have committed meanwhile)."""
    ahead = git(root, "rev-list", "--count", "@{u}..HEAD")
    n = int(ahead.stdout.strip() or 0) if ahead.returncode == 0 else 0
    if not n:
        return "nothing to push"
    pull = git(root, "pull", "--rebase", "--quiet")
    if pull.returncode != 0:
        git(root, "rebase", "--abort")
        return f"{n} commit(s) NOT pushed: git pull --rebase failed ({(pull.stderr or pull.stdout).strip()[:200]}). Run `git pull --rebase && git push` in the repo."
    p = git(root, "push", "-q")
    return f"pushed {n} follow-up commit(s)" if p.returncode == 0 else f"{n} commit(s) NOT pushed: {(p.stderr or p.stdout).strip()[:200]}"


if __name__ == "__main__":
    print(push_pending())

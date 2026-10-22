#!/usr/bin/env python3
"""
Health check for the tracker repo: the things that have made a price check or the menu-bar widget stall before.

    python3 scripts/doctor.py          # every check, one line each (✓ / ⚠)
    python3 scripts/doctor.py --brief  # only the problems, nothing when all is well (start.py prints this)
    python3 scripts/doctor.py --fix    # also clear what is safe to clear: stale git locks, a dead run clock

Checks (2026-10-23):
- git lock files left in .git by an interrupted git command (later commits then fail with "File exists");
- a run clock (data/incoming/runclock.json) whose run is gone: its pid has exited, or it is over 45 minutes old;
- tracked changes that are not committed, and commits that are not pushed (the site doesn't show them yet);
- data sources older than their cadence (scripts/freshness.py), full listing only.
Reads local files and local git state only: no network, nothing changed without --fix.
"""
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JST = timezone(timedelta(hours=9))
CLOCK = ROOT / "data" / "incoming" / "runclock.json"
LOCK_AGE = 10 * 60        # a lock this old with no git running is left over
CLOCK_AGE = 45 * 60       # no price check takes this long


def git(*a):
    r = subprocess.run(["git", *a], cwd=ROOT, text=True, capture_output=True)
    return r.returncode, (r.stdout or "").strip()


def git_running():
    try:
        return subprocess.run(["pgrep", "-x", "git"], capture_output=True).returncode == 0
    except Exception:  # noqa: BLE001
        return False


def pid_alive(pid):
    try:
        os.kill(int(pid), 0)
        return True
    except ProcessLookupError:
        return False
    except Exception:  # noqa: BLE001  (no permission = it exists)
        return True


def check_locks(fix):
    gd = ROOT / ".git"
    if not gd.is_dir():
        return []
    now = time.time()
    locks = [p for p in list(gd.glob("*.lock")) + list((gd / "refs").rglob("*.lock")) if now - p.stat().st_mtime > LOCK_AGE]
    if not locks:
        return [("ok", "git: no leftover lock files")]
    names = ", ".join(str(p.relative_to(gd)) for p in locks)
    if fix and not git_running():
        for p in locks:
            try:
                p.unlink()
            except Exception:  # noqa: BLE001
                p.rename(p.with_name(p.name + f".stale-{int(now)}"))
        return [("fixed", f"git: removed leftover lock files ({names})")]
    return [("warn", f"git: leftover lock files in .git ({names}); git commits will fail until they're removed "
                     "(python3 scripts/doctor.py --fix)")]


def check_clock(fix):
    try:
        c = json.loads(CLOCK.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return [("ok", "run clock: no run in progress")]
    except Exception:  # noqa: BLE001
        c = {}
    try:
        age = (datetime.now(JST) - datetime.fromisoformat(c["start"])).total_seconds()
    except Exception:  # noqa: BLE001
        age = CLOCK_AGE + 1
    pid = c.get("pid")
    gone = (pid is not None and not pid_alive(pid)) or age > CLOCK_AGE
    if not gone:
        return [("ok", f"run clock: a {c.get('mode', '?')} check is running ({int(age // 60)} min)")]
    why = "its process has exited" if pid is not None and not pid_alive(pid) else f"started {int(age // 60)} min ago"
    if fix:
        CLOCK.rename(CLOCK.with_name(f"runclock-stale-{datetime.now(JST):%Y%m%d-%H%M}.json"))
        return [("fixed", f"run clock: cleared a stale {c.get('mode', '?')} run ({why})")]
    return [("warn", f"run clock: a {c.get('mode', '?')} run never ended ({why}); the widget may show it as running "
                     "(python3 scripts/doctor.py --fix)")]


def check_git():
    out = []
    rc, st = git("status", "--porcelain", "--untracked-files=no")
    if rc == 0:
        n = len([l for l in st.splitlines() if l.strip()])
        out.append(("warn", f"git: {n} tracked file(s) changed but not committed") if n else ("ok", "git: nothing uncommitted"))
    rc, ahead = git("rev-list", "--count", "@{u}..HEAD")
    if rc == 0 and ahead.isdigit():
        n = int(ahead)
        out.append(("warn", f"git: {n} commit(s) not pushed, so the site doesn't show them yet (git push)") if n
                   else ("ok", "git: everything pushed (as of the last fetch)"))
    return out


def check_fresh():
    try:
        sys.path.insert(0, str(ROOT / "scripts"))
        import freshness
        st = freshness.stale(ROOT)
    except Exception as e:  # noqa: BLE001
        return [("warn", f"freshness: couldn't check ({e})")]
    if not st:
        return [("ok", "data: every source is within its cadence")]
    return [("warn", "data: stale: " + "; ".join(str(x[0]) if isinstance(x, (list, tuple)) else str(x) for x in st))]


def run(brief=False, fix=False):
    res = check_locks(fix) + check_clock(fix) + check_git()
    if not brief:
        res += check_fresh()
    mark = {"ok": "✓", "warn": "⚠", "fixed": "✔"}
    lines = [f"{mark[k]} {t}" for k, t in res if not (brief and k == "ok")]
    return lines


def main():
    a = sys.argv[1:]
    lines = run(brief="--brief" in a, fix="--fix" in a)
    if lines:
        print(("DOCTOR:\n" if "--brief" in a else "") + "\n".join(lines))


if __name__ == "__main__":
    main()

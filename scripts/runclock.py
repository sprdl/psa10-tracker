#!/usr/bin/env python3
"""
How long a price check takes, step by step (local only: data/incoming/ is not committed).

    python3 scripts/runclock.py start <mode>     # pricecheck/start.py calls this
    python3 scripts/runclock.py lap <label>      # full_update.py / quick_update.py call it when they publish
    python3 scripts/runclock.py end              # last step of a run: prints the total and the laps
                                                 # (quick_update.py calls it itself when no follow-ups are left;
                                                 # a second `end` then just repeats that line)
    python3 scripts/runclock.py history [N]      # the last N runs (default 10)

`end` appends one line per run to data/incoming/run_times.jsonl, so runs can be compared over time.
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

JST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parent.parent
DIR = ROOT / "data" / "incoming"
CUR = DIR / "runclock.json"
LOG = DIR / "run_times.jsonl"
LAST = DIR / "runclock-last.json"   # the last `end` line, so a repeated `end` can say it again


def now():
    return datetime.now(JST)


def fmt(sec):
    sec = int(round(sec))
    return f"{sec // 60}m{sec % 60:02d}s"


def load():
    try:
        return json.loads(CUR.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def start(mode):
    DIR.mkdir(parents=True, exist_ok=True)
    c = {"mode": mode, "start": now().isoformat(timespec="seconds"), "laps": []}
    pid = os.environ.get("PSA10_RUN_PID", "")
    if pid.isdigit():   # a menu-bar run: its run-check.sh process, so the widget can tell when the run is gone
        c["pid"] = int(pid)
    CUR.write_text(json.dumps(c), encoding="utf-8")
    LAST.unlink(missing_ok=True)   # a new run: a repeated `end` must not report the previous one
    print(f"⏱ run clock started {now():%H:%M:%S} JST ({mode} check)")


def lap(label):
    """Never fails the caller: timing is a convenience."""
    try:
        c = load()
        if not c:
            return
        t = now()
        c["laps"].append([label, t.isoformat(timespec="seconds")])
        CUR.write_text(json.dumps(c), encoding="utf-8")
        print(f"⏱ {label} at +{fmt((t - datetime.fromisoformat(c['start'])).total_seconds())} since the run started")
    except Exception:  # noqa: BLE001
        pass


def _push_followups():
    try:   # the follow-ups committed locally during the run (scripts/deferpush.py): one push for all of them
        import deferpush
        print("⏱ follow-ups: " + deferpush.push_pending(ROOT))
    except Exception as e:  # noqa: BLE001
        print(f"⏱ follow-ups: push failed ({e}); run `python3 scripts/deferpush.py`")


def end():
    c = load()
    if not c:
        try:   # already ended this run (quick_update.py ends it when no follow-ups are left): repeat that line
            last = json.loads(LAST.read_text(encoding="utf-8"))
            if (now() - datetime.fromisoformat(last["ended"])).total_seconds() < 3 * 3600:
                print(f"{last['line']} (the run clock was already ended at {datetime.fromisoformat(last['ended']):%H:%M:%S} JST)")
                _push_followups()
                return
        except Exception:  # noqa: BLE001
            pass
        print("⏱ no run clock (start.py wasn't used for this run)")
        return
    t = now()
    s = datetime.fromisoformat(c["start"])
    total = (t - s).total_seconds()
    laps = [(lab, (datetime.fromisoformat(ts) - s).total_seconds()) for lab, ts in c["laps"]]
    line = (f"⏱ {c['mode']} check: {fmt(total)} total (started {s:%H:%M} JST)"
            + "".join(f" · {lab} at +{fmt(x)}" for lab, x in laps))
    print(line)
    try:
        LAST.write_text(json.dumps({"line": line, "ended": t.isoformat(timespec="seconds")}, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"mode": c["mode"], "start": c["start"], "total_s": round(total),
                            "laps": {lab: round(x) for lab, x in laps}}, ensure_ascii=False) + "\n")
    CUR.unlink(missing_ok=True)
    _push_followups()


def history(n=10):
    if not LOG.exists():
        print("no runs logged yet")
        return
    for ln in LOG.read_text(encoding="utf-8").splitlines()[-n:]:
        r = json.loads(ln)
        print(f"{r['start'][:16]}  {r['mode']:5}  {fmt(r['total_s'])}  " + " ".join(f"{k}+{fmt(v)}" for k, v in r["laps"].items()))


if __name__ == "__main__":
    a = sys.argv[1:]
    cmd = a[0] if a else ""
    if cmd == "start":
        start(a[1] if len(a) > 1 else "?")
    elif cmd == "lap":
        lap(" ".join(a[1:]) or "lap")
    elif cmd == "end":
        end()
    elif cmd == "history":
        history(int(a[1]) if len(a) > 1 else 10)
    else:
        print(__doc__)

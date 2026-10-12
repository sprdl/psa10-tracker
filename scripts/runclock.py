#!/usr/bin/env python3
"""
How long a price check takes, step by step (local only: data/incoming/ is not committed).

    python3 scripts/runclock.py start <mode>     # pricecheck/start.py calls this
    python3 scripts/runclock.py lap <label>      # full_update.py / quick_update.py call it when they publish
    python3 scripts/runclock.py end              # last step of a run: prints the total and the laps
    python3 scripts/runclock.py history [N]      # the last N runs (default 10)

`end` appends one line per run to data/incoming/run_times.jsonl, so runs can be compared over time.
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

JST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parent.parent
DIR = ROOT / "data" / "incoming"
CUR = DIR / "runclock.json"
LOG = DIR / "run_times.jsonl"


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
    CUR.write_text(json.dumps({"mode": mode, "start": now().isoformat(timespec="seconds"), "laps": []}), encoding="utf-8")
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


def end():
    c = load()
    if not c:
        print("⏱ no run clock (start.py wasn't used for this run)")
        return
    t = now()
    s = datetime.fromisoformat(c["start"])
    total = (t - s).total_seconds()
    laps = [(lab, (datetime.fromisoformat(ts) - s).total_seconds()) for lab, ts in c["laps"]]
    print(f"⏱ {c['mode']} check: {fmt(total)} total (started {s:%H:%M} JST)"
          + "".join(f" · {lab} at +{fmt(x)}" for lab, x in laps))
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"mode": c["mode"], "start": c["start"], "total_s": round(total),
                            "laps": {lab: round(x) for lab, x in laps}}, ensure_ascii=False) + "\n")
    CUR.unlink(missing_ok=True)


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

#!/usr/bin/env python3
"""
PSA grading backlog and the reopening of the Value tiers (data/psa_backlog.json). See "about" in that file.

    python3 scripts/psa_backlog.py status                          latest reading, drops and the projection
    python3 scripts/psa_backlog.py add YYYY-MM-DD 7.6 [--note TEXT] [--no-push]
                                                                   add (or replace) a reading in millions of units,
                                                                   recompute the projection, push
    python3 scripts/psa_backlog.py recompute [--no-push]           recompute the projection from the stored readings

PSA publishes the backlog every other Tuesday (its "PSA Backlog Tracker" page and update notes). Read the page in
your own browser (one page load) or copy the figure from the update; nothing here fetches PSA automatically.

The projection is plain arithmetic on PSA's own figures, not a forecast: three scenarios for how the next
fortnightly drops could look, and the first update date on which each one gets below the threshold. The site only
displays what is stored here, so the rule exists in one place.
"""
import argparse, json, os, subprocess, sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILE = ROOT / "data" / "psa_backlog.json"
JST = timezone(timedelta(hours=9))
STEP_DAYS = 14        # PSA updates the tracker every other Tuesday
MAX_UPDATES = 26      # a year of updates; a scenario that is still above the threshold then counts as "not within a year"
PATH_SHOWN = 8        # updates of each scenario's path kept in the file (the site lists a few of them)


def load():
    return json.loads(FILE.read_text(encoding="utf-8"))


def save(d):
    d["readings"].sort(key=lambda r: r["d"])
    FILE.write_text(json.dumps(d, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def project(readings, threshold):
    """Scenarios from the stored readings. Returns the 'projection' dict."""
    rs = sorted(readings, key=lambda r: r["d"])
    if len(rs) < 3:
        return {"error": "need at least 3 readings"}
    last = rs[-1]
    drops = [round(a["m"] - b["m"], 3) for a, b in zip(rs, rs[1:])]
    recent = drops[-3:]
    avg = sum(recent) / len(recent)
    latest = drops[-1]
    # how much the fortnightly drop shrank per update over the same stretch (0 if it isn't shrinking)
    step = max(0.0, (recent[0] - recent[-1]) / (len(recent) - 1)) if len(recent) > 1 else 0.0
    t0 = date.fromisoformat(last["d"])

    def run(drop_at):
        lvl, path, under = last["m"], [], None
        for k in range(1, MAX_UPDATES + 1):
            lvl = max(0.0, lvl - drop_at(k))
            d = (t0 + timedelta(days=STEP_DAYS * k)).isoformat()
            if k <= PATH_SHOWN:
                path.append({"d": d, "m": round(lvl, 2)})
            if under is None and lvl < threshold - 1e-9:
                under = d
        return {"under_on": under, "floor_m": None if under else round(lvl, 2), "path": path}

    scen = [
        dict(key="avg", label="Average pace holds", rule=f"each update drops {avg:.2f}M, the average of the last {len(recent)} drops", **run(lambda k: avg)),
        dict(key="latest", label="Latest pace holds", rule=f"each update drops {latest:.2f}M, like the last one", **run(lambda k: latest)),
        dict(key="slow", label="Slowdown continues",
             rule=f"the drop keeps shrinking by {step:.2f}M per update until it reaches zero" if step > 0 else "no slowdown in the last drops, same as the latest pace",
             **run(lambda k: max(0.0, latest - step * k))),
    ]
    return {
        "as_of": last["d"], "backlog_m": last["m"], "gap_m": round(last["m"] - threshold, 2),
        "next_update": (t0 + timedelta(days=STEP_DAYS)).isoformat(),
        "drops_m": drops, "avg_drop_m": round(avg, 3), "last_drop_m": round(latest, 3), "drop_step_m": round(step, 3),
        "scenarios": scen,
    }


def recompute(d):
    d["projection"] = project(d["readings"], d["threshold_m"])
    d["updated_jst"] = datetime.now(JST).strftime("%Y-%m-%d %H:%M")
    return d


def describe(d):
    p = d["projection"]
    print(f"Backlog {p['backlog_m']}M on {p['as_of']} ({p['gap_m']}M above the {d['threshold_m']}M line); next update {p['next_update']}")
    print("Drops per update (M): " + ", ".join(f"{x:+.1f}".replace("+", "-") for x in p["drops_m"]))
    for s in p["scenarios"]:
        end = f"under {d['threshold_m']}M on the {s['under_on']} update" if s["under_on"] else f"never under {d['threshold_m']}M within a year (levels off near {s['floor_m']}M)"
        print(f"  {s['label']}: {end} - {s['rule']}")


def push(msg, no_push):
    if no_push:
        return
    run = lambda *a, check=True: subprocess.run(["git", *a], cwd=ROOT, text=True, capture_output=True, check=check,
                                                env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
    run("add", "data/psa_backlog.json")
    if run("commit", "-m", msg, check=False).returncode != 0:
        print("Nothing to commit."); return
    p = run("push", check=False)
    if p.returncode != 0:
        sys.exit("git push failed:\n" + (p.stderr or p.stdout))
    print("Pushed.")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    a = sub.add_parser("add"); a.add_argument("d"); a.add_argument("m", type=float)
    a.add_argument("--note"); a.add_argument("--no-push", action="store_true")
    r = sub.add_parser("recompute"); r.add_argument("--no-push", action="store_true")
    args = ap.parse_args()
    d = load()

    if args.cmd == "status":
        describe(d); return
    if args.cmd == "add":
        date.fromisoformat(args.d)
        if not 0 < args.m < 100:
            sys.exit("ERROR: the backlog is given in millions of units, e.g. 7.6")
        d["readings"] = [x for x in d["readings"] if x["d"] != args.d]
        e = {"d": args.d, "m": args.m}
        if args.note: e["note"] = args.note
        d["readings"].append(e)
        save(recompute(d)); describe(load())
        push(f"psa backlog: {args.m}M on {args.d}", args.no_push); return
    if args.cmd == "recompute":
        save(recompute(d)); describe(load()); push("psa backlog: recompute projection", args.no_push); return


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
PSA grading backlog and the reopening of the Value tiers (data/psa_backlog.json). See "about" in that file.

    python3 scripts/psa_backlog.py status                          latest reading, drops and the projection
    python3 scripts/psa_backlog.py due                             is today's full check due to look at PSA's page?
    python3 scripts/psa_backlog.py from-page -  < text             save the newest update from text copied off PSA's page
    python3 scripts/psa_backlog.py add YYYY-MM-DD 7.6 [--note TEXT] [--no-push]
                                                                   add (or replace) a reading by hand, in millions of units
    python3 scripts/psa_backlog.py recompute [--no-push]           recompute the projection from the stored readings

PSA publishes an update every other Tuesday at https://www.psacard.com/info/backlog-tracker (a heading "October 6, 2026
Update" over a paragraph with the figure). The full check (FULL-CHECK.md step 8i) reads it with one page fetch, and only
when this script says it is due:

  * an update is expected 14 days after the newest stored one (2026-10-06 -> 2026-10-20);
  * the first check is the day after (2026-10-21), on that day's first full check;
  * if the page has nothing newer, the check repeats on every day's first full check until it does;
  * once the new update is saved the next one is expected 14 days after ITS date, so the cadence returns to every
    other Tuesday (an update posted late still carries its own heading date).

The projection is plain arithmetic on PSA's figures, not a forecast: three scenarios for how the next fortnightly drops
could look, and the first update date on which each one gets below the threshold. The site only displays what is stored
here, so the rule exists in one place.
"""
import argparse, json, os, re, subprocess, sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JST = timezone(timedelta(hours=9))
STEP_DAYS = 14        # PSA updates the tracker every other Tuesday
MAX_UPDATES = 26      # a year of updates; a scenario that is still above the threshold then counts as "not within a year"
PATH_SHOWN = 8        # updates of each scenario's path kept in the file (the site lists a few of them)
MAX_JUMP_M = 3.0      # a new figure further than this from the last one is not saved automatically
URL = "https://www.psacard.com/info/backlog-tracker"


def file_for(root):
    return Path(root) / "data" / "psa_backlog.json"


def load(root=ROOT):
    return json.loads(file_for(root).read_text(encoding="utf-8"))


def save(d, root=ROOT):
    d["readings"].sort(key=lambda r: r["d"])
    file_for(root).write_text(json.dumps(d, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def today():
    return datetime.now(JST).date()


# ---------- projection ----------

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


# ---------- reading PSA's page ----------

HEAD = re.compile(r"\b([A-Z][a-z]+)\s+(\d{1,2}),\s*(\d{4})\s+Update\b")
# "Our active grading backlog is now 8.2 million units", "backlog is down to approximately 9 million", "Backlog fell to 11.85 million"
FIGURE = re.compile(r"backlog(?:\s+(?:is|was|now|down|up|to|at|near|approximately|about|roughly|around|currently|rose|fell|dropped|climbed|has|have|been|reduced|stands)){0,8}\s+(\d+(?:\.\d+)?)\s+million", re.I)
PREVIOUS = re.compile(r"\bfrom\s+(\d+(?:\.\d+)?)\s+million", re.I)


def parse_update(text):
    """The newest update in text copied off PSA's page (the first heading): (date, millions, previous millions or None, paragraph)."""
    m = HEAD.search(text)
    if not m:
        return None
    try:
        d = datetime.strptime(f"{m[1]} {m[2]} {m[3]}", "%B %d %Y").date()
    except ValueError:
        return None
    rest = text[m.end():]
    nxt = HEAD.search(rest)
    para = re.sub(r"\s+", " ", rest[:nxt.start()] if nxt else rest[:900]).strip()
    f = FIGURE.search(para)
    prev = PREVIOUS.search(para[f.end():]) if f else None
    return d, (float(f[1]) if f else None), (float(prev[1]) if prev else None), para


def due_state(d, now=None):
    """(due?, why). Due from the day after the expected update until a newer reading is stored; once per JST day."""
    t = now or today()
    last = date.fromisoformat(d["readings"][-1]["d"])
    expected = last + timedelta(days=STEP_DAYS)
    start = expected + timedelta(days=1)
    if t < start:
        return False, f"next update expected {expected}; the check starts {start}"
    if (d.get("check") or {}).get("last_checked") == t.isoformat():
        return False, f"already checked today; the update dated {expected} isn't on PSA's page yet, checking again tomorrow"
    late = (t - start).days
    return True, (f"an update dated about {expected} should be on PSA's page (first check {start}"
                  + (f", {late} day{'s' if late != 1 else ''} later and still nothing newer stored" if late else "") + ")")


def print_due(root=ROOT):
    try:
        d = load(root)
        ok, why = due_state(d)
    except Exception as e:  # noqa: BLE001  never break a price check over this
        print(f"\nPSA BACKLOG: skipped ({e})")
        return False
    if not ok:
        print(f"\nPSA BACKLOG: none due ({why}).")
        return False
    print(f"\nPSA BACKLOG NOW (FULL-CHECK step 8i) — {why}.")
    print(f"  Read {URL} (WebFetch first), then save the newest update: python3 scripts/psa_backlog.py from-page -")
    return True


def due_count(root=ROOT):
    try:
        return 1 if due_state(load(root))[0] else 0
    except Exception:  # noqa: BLE001
        return 0


# ---------- output ----------

def describe(d):
    p = d["projection"]
    print(f"Backlog {p['backlog_m']}M on {p['as_of']} ({p['gap_m']}M above the {d['threshold_m']}M line); next update {p['next_update']}")
    print("Drops per update (M): " + ", ".join(f"-{x:.1f}" if x >= 0 else f"+{-x:.1f}" for x in p["drops_m"]))
    for s in p["scenarios"]:
        end = f"under {d['threshold_m']}M on the {s['under_on']} update" if s["under_on"] else f"never under {d['threshold_m']}M within a year (levels off near {s['floor_m']}M)"
        print(f"  {s['label']}: {end} - {s['rule']}")
    c = d.get("check") or {}
    if c.get("last_checked"):
        print(f"Last looked at PSA's page: {c['last_checked']} ({c.get('result', '?')})")


def push(msg, no_push, root=ROOT):
    if no_push:
        return
    run = lambda *a, check=True: subprocess.run(["git", *a], cwd=root, text=True, capture_output=True, check=check,
                                                env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
    run("add", "data/psa_backlog.json")
    if run("commit", "-m", msg, check=False).returncode != 0:
        print("Nothing to commit."); return
    p = run("push", check=False)
    if p.returncode != 0:
        sys.exit("git push failed:\n" + (p.stderr or p.stdout))
    print("Pushed.")


def note_check(d, result):
    d["check"] = {"last_checked": today().isoformat(), "result": result}


def from_page(text, root=ROOT, no_push=False):
    d = load(root)
    got = parse_update(text)
    if not got:
        print("CHECK BY HAND: no 'Month D, YYYY Update' heading found in the text. Paste the newest update's heading and its first paragraph.")
        return 2
    when, m, prev, para = got
    last = d["readings"][-1]
    if when.isoformat() <= last["d"]:
        note_check(d, f"no new update (page's newest: {when})")
        save(d, root)
        print(f"NO NEW UPDATE: the page's newest update is {when}, already stored ({last['m']}M). Checking again on the next full check.")
        push(f"psa backlog: checked {today()}, nothing new", no_push, root)
        return 0
    if m is None:
        print(f"CHECK BY HAND: update {when} found but no 'backlog … N million' figure in its text:\n  {para[:300]}")
        return 2
    if abs(m - last["m"]) > MAX_JUMP_M:
        print(f"CHECK BY HAND: {m}M on {when} is {abs(m - last['m']):.1f}M from the last stored reading ({last['m']}M); not saved. "
              f"Look at the page, then `python3 scripts/psa_backlog.py add {when} {m}` if it is right.")
        return 2
    if prev is not None and abs(prev - last["m"]) > max(0.06, 0.02 * last["m"]):
        print(f"CHECK BY HAND: the update says it is down from {prev}M, but the last stored reading is {last['m']}M ({last['d']}): "
              f"an update in between may have been missed. Read the page's earlier updates, add them with `add`, then save this one. Not saved.")
        return 2
    d["readings"] = [x for x in d["readings"] if x["d"] != when.isoformat()]
    note = para.split(". ")[0][:160].rstrip(".")
    d["readings"].append({"d": when.isoformat(), "m": m, "note": note})
    note_check(d, f"new update {when}")
    save(recompute(d), root)
    print(f"SAVED: {m}M on {when} (was {last['m']}M on {last['d']}).")
    describe(load(root))
    push(f"psa backlog: {m}M on {when}", no_push, root)
    return 0


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    sub.add_parser("due")
    f = sub.add_parser("from-page"); f.add_argument("file", nargs="?", default="-"); f.add_argument("--no-push", action="store_true")
    a = sub.add_parser("add"); a.add_argument("d"); a.add_argument("m", type=float)
    a.add_argument("--note"); a.add_argument("--no-push", action="store_true")
    r = sub.add_parser("recompute"); r.add_argument("--no-push", action="store_true")
    args = ap.parse_args()
    d = load()

    if args.cmd == "status":
        describe(d); return
    if args.cmd == "due":
        ok, why = due_state(d)
        print(("DUE: " if ok else "none due: ") + why); return
    if args.cmd == "from-page":
        text = sys.stdin.read() if args.file == "-" else Path(args.file).read_text(encoding="utf-8")
        sys.exit(from_page(text, ROOT, args.no_push))
    if args.cmd == "add":
        date.fromisoformat(args.d)
        if not 0 < args.m < 100:
            sys.exit("ERROR: the backlog is given in millions of units, e.g. 7.6")
        d["readings"] = [x for x in d["readings"] if x["d"] != args.d]
        e = {"d": args.d, "m": args.m}
        if args.note: e["note"] = args.note
        d["readings"].append(e)
        note_check(d, f"added by hand {args.d}")
        save(recompute(d)); describe(load())
        push(f"psa backlog: {args.m}M on {args.d}", args.no_push); return
    if args.cmd == "recompute":
        save(recompute(d)); describe(load()); push("psa backlog: recompute projection", args.no_push); return


if __name__ == "__main__":
    main()

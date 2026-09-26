#!/usr/bin/env python3
"""
Event calendar for the event rule (data/events.json). See "about" in that file.

    python3 scripts/events.py list [--all]          upcoming (and undated) events; --all includes past ones
    python3 scripts/events.py window                events inside the rule window right now (JST), for the evaluation skill
    python3 scripts/events.py add YYYY-MM-DD "name" [--scope all|M6a,M7] [--minor] [--kind release|announcement|psa] [--source URL] [--note TEXT] [--no-push]
    python3 scripts/events.py date "name part" YYYY-MM-DD [--no-push]     give a rumoured event its official date
    python3 scripts/events.py remove "name part" [--no-push]
"""
import argparse, json, os, subprocess, sys
from datetime import datetime, timedelta, timezone, date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILE = ROOT / "data" / "events.json"
JST = timezone(timedelta(hours=9))


def load():
    return json.loads(FILE.read_text(encoding="utf-8"))


def save(d):
    d["events"].sort(key=lambda e: (e.get("d") is None, e.get("d") or "", e["name"]))
    FILE.write_text(json.dumps(d, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def today():
    return datetime.now(JST).date()


def fmt(e, t):
    scope = e.get("scope", "all")
    scope = "all cards" if scope == "all" else "sets " + ", ".join(scope)
    if e.get("d"):
        days = (date.fromisoformat(e["d"]) - t).days
        when = f"{e['d']} ({'today' if days == 0 else f'in {days}d' if days > 0 else f'{-days}d ago'})"
    else:
        when = f"undated: {e.get('when', '?')}"
    return f"{when} · {e['name']} · {'major' if e.get('major', True) else 'minor'} · {scope}"


def find(d, part):
    hits = [e for e in d["events"] if part.lower() in e["name"].lower()]
    if len(hits) != 1:
        sys.exit(f"ERROR: {len(hits)} events match {part!r}")
    return hits[0]


def push(msg, no_push):
    if no_push:
        return
    run = lambda *a, check=True: subprocess.run(["git", *a], cwd=ROOT, text=True, capture_output=True, check=check,
                                                env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
    run("add", "data/events.json")
    if run("commit", "-m", msg, check=False).returncode != 0:
        print("Nothing to commit."); return
    p = run("push", check=False)
    if p.returncode != 0:
        sys.exit("git push failed:\n" + (p.stderr or p.stdout))
    print("Pushed.")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    l = sub.add_parser("list"); l.add_argument("--all", action="store_true")
    sub.add_parser("window")
    a = sub.add_parser("add")
    a.add_argument("d"); a.add_argument("name")
    a.add_argument("--scope", default="all"); a.add_argument("--minor", action="store_true")
    a.add_argument("--kind", default="release"); a.add_argument("--source"); a.add_argument("--note")
    a.add_argument("--no-push", action="store_true")
    s = sub.add_parser("date"); s.add_argument("part"); s.add_argument("d"); s.add_argument("--no-push", action="store_true")
    r = sub.add_parser("remove"); r.add_argument("part"); r.add_argument("--no-push", action="store_true")
    args = ap.parse_args()
    d = load(); t = today(); win = d.get("window_days", 3)

    if args.cmd == "list":
        for e in d["events"]:
            if args.all or not e.get("d") or e["d"] >= t.isoformat():
                print(fmt(e, t))
        return
    if args.cmd == "window":
        hits = [e for e in d["events"] if e.get("d") and e.get("major", True)
                and 0 <= (date.fromisoformat(e["d"]) - t).days <= win]
        print(f"Event rule ({win} days, JST {t}): " + ("ON" if hits else "off"))
        for e in hits:
            print("  " + fmt(e, t))
        return
    if args.cmd == "add":
        date.fromisoformat(args.d)
        e = {"d": args.d, "name": args.name, "kind": args.kind, "major": not args.minor,
             "scope": "all" if args.scope == "all" else [x.strip() for x in args.scope.split(",") if x.strip()]}
        if args.source: e["source"] = args.source
        if args.note: e["note"] = args.note
        d["events"].append(e); save(d)
        print("Added: " + fmt(e, t)); push(f"events: add {args.d} {args.name}", args.no_push); return
    if args.cmd == "date":
        date.fromisoformat(args.d)
        e = find(d, args.part); e["d"] = args.d; e.pop("tentative", None); e.pop("when", None); save(d)
        print("Dated: " + fmt(e, t)); push(f"events: {e['name']} on {args.d}", args.no_push); return
    if args.cmd == "remove":
        e = find(d, args.part); d["events"].remove(e); save(d)
        print("Removed: " + e["name"]); push(f"events: remove {e['name']}", args.no_push); return


if __name__ == "__main__":
    main()

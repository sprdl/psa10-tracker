#!/usr/bin/env python3
"""
Weekly recap notes (data/recaps.json) for the site's Weekly recap page (#/recap) and its Overview card.

The page computes the numbers itself for any Mon–Sun (JST) week from history.json, custom_index.json, the
holdings and events.json: how owned and watched cards moved, the indices, your purchases, scheduled releases.
What it can't compute is the news. This file holds a short written note per week, researched by the first full
check on Monday (FULL-CHECK step 8j) for the week that just ended:

    python3 scripts/recap.py due              # "DUE 2026-10-05" (Monday of the week to write) or "none due"
    python3 scripts/recap.py facts [MONDAY]   # the week's numbers to write from (default: the week due / last week)
    python3 scripts/recap.py save - [--no-push] <<'JSON'
    {"week": "2026-10-05",
     "headline": "One sentence: what defined the week for Philipp's cards.",
     "takeaway": "Optional 1-3 sentences: what it means for buying/selling.",
     "happened": [{"d": "2026-10-09", "title": "…", "text": "…", "source": "https://…"}],
     "ahead":    [{"d": "2026-10-16", "title": "…", "text": "…", "source": "https://…"}]}
    JSON

Rules (checked by `save`): week is a Monday; `happened` dates fall inside that week, `ahead` dates in the next
7 days after it (or null for "date not announced"); every item has a title; a source URL when it's news from the
web. Only official or well-sourced items: label rumours as rumours in the text. Don't restate numbers the page
already shows (price moves, index changes, purchases, events.json releases); explain them instead.
"""
import json
import os
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

JST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parent.parent
PATH = ROOT / "data" / "recaps.json"
ABOUT = ("Weekly recap notes for the site's Weekly recap page: per week (key = Monday, JST) a headline, an optional "
         "takeaway, what happened (news) and what to watch next week. Written by FULL-CHECK step 8j with scripts/recap.py; "
         "the page computes all numbers itself.")


def load(root=ROOT):
    p = root / "data" / "recaps.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"about": ABOUT, "weeks": {}}


def monday(d):
    return d - timedelta(days=d.weekday())


def due(root=ROOT, now=None):
    """Monday (date) of the last full week if it has no note yet and checks exist for it, else None."""
    now = now or datetime.now(JST)
    last = monday(now.date()) - timedelta(days=7)
    if last.isoformat() in load(root).get("weeks", {}):
        return None
    h = root / "data" / "history.json"
    if not h.exists():
        return None
    snaps = json.loads(h.read_text(encoding="utf-8")).get("snapshots", [])
    lo, hi = last.isoformat(), (last + timedelta(days=7)).isoformat()
    return last if any(lo <= s["d"][:10] < hi for s in snaps) else None


def facts(week, root=ROOT):
    """Plain-text numbers for the week (what the page will show), to write the note against."""
    h = json.loads((root / "data" / "history.json").read_text(encoding="utf-8"))
    snaps = sorted(h["snapshots"], key=lambda s: s["d"])
    lo, hi = week.isoformat(), (week + timedelta(days=7)).isoformat()
    inw = [s for s in snaps if lo <= s["d"][:10] < hi]
    if not inw:
        return f"No checks in the week of {lo}."
    before = [s for s in snaps if s["d"][:10] < lo]
    a, b = (before[-1] if before else inw[0]), inw[-1]
    out = [f"Week {lo} – {(week + timedelta(days=6)).isoformat()}: {len(inw)} checks, {a['d'][:16]} → {b['d'][:16]} JST"]
    for k, name in (("i", "PSA10 index"), ("ri", "Raw A-rank index")):
        if a.get(k) and b.get(k):
            out.append(f"{name}: {a[k]:,} → {b[k]:,} ({(b[k] / a[k] - 1) * 100:+.1f}%)")
    ci = json.loads((root / "data" / "custom_index.json").read_text(encoding="utf-8")).get("series", [])
    c0 = [e for e in ci if e["d"] < lo] or [e for e in ci if e["d"] >= lo]
    c1 = [e for e in ci if e["d"] < hi]
    if c0 and c1:
        out.append(f"My-tier index: {c0[-1]['level']} → {c1[-1]['level']} ({(c1[-1]['level'] / c0[-1]['level'] - 1) * 100:+.1f}%)")
    names = {}
    m = json.loads((root / "data" / "manifest.json").read_text(encoding="utf-8"))
    latest = sorted(m["snapshots"], key=lambda s: s["collected_at_jst"])[-1]["file"]
    for c in json.loads((root / "data" / "snapshots" / latest).read_text(encoding="utf-8")).get("cards", []):
        names[c["url"]] = c.get("card_name_ja", c["url"])[:40]
    held = {x.get("card_url") for x in json.loads((root / "data" / "holdings.json").read_text(encoding="utf-8")).get("holdings", [])}
    rows = []
    for url in names:
        p0 = (a.get("p") or {}).get(url) or next(((s.get("p") or {}).get(url) for s in inw if (s.get("p") or {}).get(url)), None)
        p1 = (b.get("p") or {}).get(url)
        if p0 and p1 and p0[0] and p1[0]:
            rows.append(((p1[0] / p0[0] - 1) * 100, url, p0[0], p1[0]))
    rows.sort(reverse=True)
    out.append("Card moves (PSA10 price, start → end of week; * = owned):")
    out += [f"  {pct:+6.1f}%  {'*' if url in held else ' '} {names[url]}  ¥{p0:,} → ¥{p1:,}" for pct, url, p0, p1 in rows]
    ev = json.loads((root / "data" / "events.json").read_text(encoding="utf-8")).get("events", [])
    nxt = (week + timedelta(days=14)).isoformat()
    out.append("events.json (already shown on the page): " + ("; ".join(f"{e['d']} {e['name']}" for e in ev if e.get("d") and lo <= e["d"] < nxt) or "none"))
    return "\n".join(out)


def _check_items(items, lo, hi, what, allow_null):
    if not isinstance(items, list):
        sys.exit(f"'{what}' must be a list")
    for it in items:
        if not isinstance(it, dict) or not (it.get("title") or "").strip():
            sys.exit(f"every '{what}' item needs a title: {it!r}")
        d = it.get("d")
        if d is None and allow_null:
            continue
        try:
            dd = date.fromisoformat(str(d))
        except ValueError:
            sys.exit(f"'{what}' item has a bad date {d!r} (YYYY-MM-DD{' or null' if allow_null else ''})")
        if not (lo <= dd < hi):
            sys.exit(f"'{what}' item {it['title']!r} dated {dd} is outside {lo} … {hi - timedelta(days=1)}")
        src = it.get("source")
        if src and not str(src).startswith(("https://", "http://")):
            sys.exit(f"source must be a URL: {src!r}")
        for k in list(it):
            if k not in ("d", "title", "text", "source"):
                sys.exit(f"unknown key {k!r} in a '{what}' item")


def save(note, root=ROOT, push=True):
    try:
        wk = date.fromisoformat(note.get("week", ""))
    except ValueError:
        sys.exit("'week' must be the Monday of the week, YYYY-MM-DD")
    if wk.weekday() != 0:
        sys.exit(f"'week' {wk} is not a Monday")
    if not (note.get("headline") or "").strip():
        sys.exit("'headline' is required")
    _check_items(note.get("happened", []), wk, wk + timedelta(days=7), "happened", False)
    _check_items(note.get("ahead", []), wk + timedelta(days=7), wk + timedelta(days=14), "ahead", True)
    data = load(root)
    entry = {k: note[k] for k in ("headline", "takeaway", "happened", "ahead") if note.get(k)}
    entry["written"] = datetime.now(JST).replace(microsecond=0).isoformat()
    data.setdefault("weeks", {})[wk.isoformat()] = entry
    data["about"] = ABOUT
    data["weeks"] = dict(sorted(data["weeks"].items()))
    (root / "data" / "recaps.json").write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"Saved the recap note for the week of {wk}.")
    if not push:
        return
    run = lambda *a, check=True: subprocess.run(["git", *a], cwd=root, text=True, capture_output=True, check=check,
                                                env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
    run("pull", "--ff-only", "-q", check=False)
    run("add", "data/recaps.json")
    if run("commit", "-m", f"recap: week of {wk}", check=False).returncode != 0:
        print("Nothing to commit."); return
    p = run("push", "-q", check=False)
    if p.returncode != 0:
        sys.exit("git push failed:\n" + (p.stderr or p.stdout))
    print("Pushed.")


def print_due(root=ROOT):
    try:
        wk = due(root)
    except Exception as e:  # noqa: BLE001 - never break a price check over this
        print(f"\nWEEKLY RECAP: skipped ({e})")
        return
    if not wk:
        print("\nWEEKLY RECAP: none due (last week's note is written, or it isn't Monday's turn yet).")
        return
    print(f"\nWEEKLY RECAP NOW (FULL-CHECK step 8j): write the note for the week of {wk} "
          f"(python3 scripts/recap.py facts {wk}, research, then recap.py save -).")


def main():
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    if not a:
        sys.exit(__doc__)
    if a[0] == "due":
        wk = due()
        print(f"DUE {wk}" if wk else "none due")
    elif a[0] == "facts":
        wk = date.fromisoformat(a[1]) if len(a) > 1 else (due() or monday(datetime.now(JST).date()) - timedelta(days=7))
        print(facts(wk))
    elif a[0] == "save":
        src = a[1] if len(a) > 1 else "-"
        text = sys.stdin.read() if src == "-" else Path(src).read_text(encoding="utf-8")
        save(json.loads(text), push="--no-push" not in sys.argv)
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()

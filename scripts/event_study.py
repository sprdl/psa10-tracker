#!/usr/bin/env python3
"""
Do prices really dip around releases? Measures the event rule on our own price checks.

    python3 scripts/event_study.py            # summary per event and overall
    python3 scripts/event_study.py --json     # same, machine-readable

Why our own checks: pokeca-chart keeps only ~30-day average points for older history (weekly for a
card's first two months, daily only for the most recent week), so a release-day dip can't be seen
in its history (checked 2026-10-02). Our snapshots (data/history.json) are roughly daily since
2026-09-15, so every release from now on adds evidence.

Question, matching the rule: if you buy at the lowest ask during the rule window (from 3 days before
a major release to the release day), how often and how far does a listing drop in the next 4 days?
Compared with the same measure on every other day (starts whose next 4 days hold no event).

  dip = lowest ask over the next 4 days / ask at the start - 1   (only starts with a check 3-5 days later)
  event start = a check in [release - 3 days, release day], for cards in the event's scope
  baseline    = all other starts more than 4 days away from any event

Events limited to some sets (e.g. the 10/16 カードセット, M6a only) are also measured on the other
cards, reported separately as "outside scope", to see whether a release moves the whole market.
Each card counts once per event (its earliest start in the window), so one busy day can't swamp it.
Read with care until several events are in: one release is one market mood.
"""
import json
import re
import statistics as st
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JST = timezone(timedelta(hours=9))
WINDOW_BEFORE, AHEAD, MIN_AHEAD, MAX_AHEAD = 3, 4, 3, 5
DIP = -0.05          # "a real dip": 5% or more below the start


def ts(s):
    d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    return d if d.tzinfo else d.replace(tzinfo=JST)


def set_code(name):
    m = re.search(r"\[([^\]]+)\]", name or "")
    return (m.group(1).split()[0] if m else "").lower()


def main():
    hist = json.loads((ROOT / "data" / "history.json").read_text(encoding="utf-8"))["snapshots"]
    ev = json.loads((ROOT / "data" / "events.json").read_text(encoding="utf-8"))
    man = json.loads((ROOT / "data" / "manifest.json").read_text(encoding="utf-8"))
    latest = sorted(man["snapshots"], key=lambda s: s["collected_at_jst"])[-1]["file"]
    names = {c["url"]: c.get("card_name_ja", "") for c in json.loads((ROOT / "data" / "snapshots" / latest).read_text(encoding="utf-8"))["cards"]}
    now = ts(hist[-1]["d"])
    events = [e for e in ev["events"] if e.get("d") and e.get("major") and e.get("kind", "release") == "release"
              and datetime.fromisoformat(e["d"]).replace(tzinfo=JST) + timedelta(days=AHEAD) <= now]
    ev_days = [datetime.fromisoformat(e["d"]).replace(tzinfo=JST) for e in events]

    series = {}
    for e in hist:
        for url, v in (e.get("p") or {}).items():
            if v and v[0]:
                series.setdefault(url, []).append((ts(e["d"]), v[0]))

    def dip_from(pts, i):
        t0, a0 = pts[i]
        ahead = [(t, a) for t, a in pts[i + 1:] if t <= t0 + timedelta(days=AHEAD)]
        later = [t for t, _ in pts[i + 1:] if t0 + timedelta(days=MIN_AHEAD) <= t <= t0 + timedelta(days=MAX_AHEAD)]
        if not ahead or not later:
            return None
        return min(a for _, a in ahead) / a0 - 1

    base, per_event = [], {e["d"]: {"name": e["name"], "cards": [], "outside": []} for e in events}
    for url, pts in series.items():
        pts.sort()
        code = set_code(names.get(url, ""))
        done = set()
        for i, (t, _) in enumerate(pts):
            d = dip_from(pts, i)
            if d is None:
                continue
            hit, scope_ok = None, False
            for e, day in zip(events, ev_days):
                if day - timedelta(days=WINDOW_BEFORE) <= t <= day + timedelta(hours=23, minutes=59):
                    hit, scope_ok = e, e.get("scope", "all") == "all" or code in [s.lower() for s in e["scope"]]
            if hit:
                if hit["d"] not in done:
                    done.add(hit["d"])
                    per_event[hit["d"]]["cards" if scope_ok else "outside"].append(
                        {"card": (names.get(url) or "card " + url.rstrip("/").split("/")[-1])[:24], "dip": round(d, 4)})
            elif all(abs((t - day).total_seconds()) > AHEAD * 86400 for day in ev_days):
                base.append(d)

    def summ(xs):
        return {"n": len(xs), "median_dip": round(st.median(xs), 4) if xs else None,
                "share_dip_5pct": round(sum(x <= DIP for x in xs) / len(xs), 3) if xs else None}

    ev_all = [c["dip"] for v in per_event.values() for c in v["cards"]]
    out = {"computed": hist[-1]["d"], "events": {k: {**v, **summ([c["dip"] for c in v["cards"]]), "outside_scope": summ([c["dip"] for c in v["outside"]])} for k, v in per_event.items()},
           "event_starts": summ(ev_all), "baseline": summ(base)}
    if "--json" in sys.argv:
        print(json.dumps(out, ensure_ascii=False, indent=1))
        return
    print(f"Event study (rule window: {WINDOW_BEFORE} days before → release day; dip = lowest ask over the next {AHEAD} days)")
    for d, v in out["events"].items():
        print(f"  {d} {v['name'][:50]}: {v['n']} cards, median {v['median_dip']:+.1%}, ≥5% dip {v['share_dip_5pct']:.0%}" if v["n"] else f"  {d} {v['name'][:50]}: no checks in the window")
        for c in sorted(v["cards"], key=lambda c: c["dip"]):
            print(f"      {c['card']:<24} {c['dip']:+.1%}")
        o = v["outside_scope"]
        if o["n"]:
            print(f"    outside scope: {o['n']} cards, median {o['median_dip']:+.1%}, ≥5% dip {o['share_dip_5pct']:.0%}")
    e, b = out["event_starts"], out["baseline"]
    if e["n"]:
        print(f"All event starts: {e['n']}, median {e['median_dip']:+.1%}, ≥5% dip {e['share_dip_5pct']:.0%}")
    if b["n"]:
        print(f"Other days:       {b['n']}, median {b['median_dip']:+.1%}, ≥5% dip {b['share_dip_5pct']:.0%}")
    n_ev = sum(1 for v in out["events"].values() if v["n"])
    print(f"{n_ev} event(s) with data. Treat as anecdote until at least 4–5 releases are in.")


if __name__ == "__main__":
    main()

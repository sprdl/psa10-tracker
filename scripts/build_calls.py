#!/usr/bin/env python3
"""
Rebuild data/calls.json: the track record of the tracker's buy/watch calls and
stated odds, scored against what the price actually did afterwards.

    python3 scripts/build_calls.py      # build_history.build() also runs this

Everything is measured on the lowest PSA10 ask: what you could actually have
bought at. It's the one price every snapshot has, quick or full.
A lone reading more than 15% below both of its neighbours is treated as a
mispriced listing and ignored.

Calls
  A call starts when a card's verdict tag changes (Buy → Watch etc.). Rewrites
  that keep the same tag count as "reaffirmed", not as new calls, so one opinion
  isn't scored five times. Each call is judged over the WINDOW_DAYS after it was
  made, against its price at the time. "Drops below" uses the card's own threshold
  (see Noise below) and needs CONFIRM_READINGS readings in a row under it:
    Buy / Definitely buy: wrong as soon as the ask drops more than the threshold below
        the call price (you could have bought meaningfully cheaper). Right if that
        never happens in the window.
    Watch / Don't buy: right as soon as the ask drops more than the threshold below
        the call price (waiting paid off). Wrong if the window ends with the
        price more than the threshold above it and no such dip. Otherwise neutral.
    Defer: not scored.

Noise (added 2026-09-26)
  The lowest ask moves 1–2% between checks on a normal day and 3–5% often, so a
  flat 5% line was deciding calls on one stray listing. Each card's threshold is
  the larger of THRESHOLD and the NOISE_PCTL percentile of its own check-to-check
  moves (capped at NOISE_CAP; needs NOISE_MIN_MOVES moves, else THRESHOLD), and a
  dip only counts once CONFIRM_READINGS consecutive readings are below the line.
  A dip seen in only the latest reading waits for the next check.

Scoring only finished windows (added 2026-10-09)
  A Watch call can turn out right early (the dip came) but only wrong at the end of
  its window, and a Buy the other way round, so counting calls as they are decided
  over-weights whatever can be decided early. The summary score ("closed") only counts
  calls whose WINDOW_DAYS are over; calls decided before that show their outcome but
  are counted when their window ends. The same goes for stated odds and the model's
  logged odds: "happened" can be known early, "didn't happen" only at the deadline,
  so only forecasts whose deadline has passed are scored.

Baseline and return vs the market (added 2026-10-09)
  baseline: the same rules applied to a call on every day (the first check of each JST
  day, for every card that had a scored call), Buy and Watch alike, closed windows only.
  It shows what the right/wrong rates look like with no judgment at all.
  Return: for each closed call, the lowest ask at the end of its window vs the call
  price, minus the My-tier index's change over the same days (points). A Buy is good
  when the card then beat the market, a Watch / Don't buy when it lagged; "edge" is that
  signed difference. The baseline gives the same numbers for a call on every day.

Stated odds (analysis.verdict.predictions)
  [{"text": "...", "p": 0.45, "type": "touch_below" | "touch_above",
    "price": 70000, "by": "2026-12-25", "made": "2026-09-25T10:03:18+09:00"}]
  Happened if the lowest ask reaches the price after `made` and on or before `by`
  (end of day JST); didn't happen once a snapshot after `by` exists without it.
  A prediction that was already true when made is marked void and not scored.
  Scored with the Brier score (0 = perfect, 0.25 = always saying 50%), once its deadline
  has passed ("final"). The limit-odds model's logged forecasts are scored the same way,
  the 30-day and the 90-day forecasts separately (each logged price counts once in each).
"""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JST = timezone(timedelta(hours=9))
WINDOW_DAYS = 30
THRESHOLD = 0.05
BUYISH = {"buy", "definitely_buy"}
WAITISH = {"watch", "dont_buy"}
PRED_TYPES = {"touch_below", "touch_above"}
OUTLIER = 0.15  # a lone reading this far below both neighbours is ignored
NOISE_PCTL = 0.9       # per-card threshold = this percentile of its check-to-check moves...
NOISE_CAP = 0.10       # ...but never more than this
NOISE_MIN_MOVES = 6    # fewer moves than this -> use THRESHOLD
CONFIRM_READINGS = 2   # consecutive readings below the line needed to count a dip


def _dt(s):
    d = datetime.fromisoformat(s)
    return d if d.tzinfo else d.replace(tzinfo=JST)


def _load(root):
    manifest = json.loads((root / "data" / "manifest.json").read_text(encoding="utf-8"))
    snaps = sorted([s for s in manifest.get("snapshots", []) if s.get("collected_at_jst")],
                   key=lambda s: s["collected_at_jst"])
    out = []
    for s in snaps:
        try:
            d = json.loads((root / "data" / "snapshots" / s["file"]).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        out.append((d.get("collected_at_jst", s["collected_at_jst"]), d.get("cards", [])))
    return out


def _mytier(root):
    p = root / "data" / "custom_index.json"
    try:
        return sorted((e["d"], e["level"]) for e in json.loads(p.read_text(encoding="utf-8")).get("series", []) if e.get("level"))
    except (OSError, json.JSONDecodeError):
        return []


def _level_at(ci, when):
    """My-tier index level on the JST day of `when` (the last reading on or before it)."""
    day = _dt(when).astimezone(JST).date().isoformat()
    v = None
    for d, lv in ci:
        if d <= day:
            v = lv
        else:
            break
    return v


def _r1(x):
    return round(x, 1) if x is not None else None


def _pct(a, b):
    return round((a - b) / b * 100, 1) if b else None


def build(root: Path = ROOT, now: datetime = None) -> Path:
    """now: score as if it were this time (tests); default = the latest snapshot."""
    snaps = _load(root)
    series, names, runs, preds = {}, {}, {}, {}
    for d, cards in snaps:
        for c in cards:
            url = c.get("url")
            if not url:
                continue
            names[url] = c.get("card_name_ja") or names.get(url, url)
            ask = ((c.get("grades") or {}).get("psa10") or {}).get("lowest_price")
            if ask is not None:
                series.setdefault(url, []).append((d, ask))
            v = (c.get("analysis") or {}).get("verdict") or {}
            tag, label = v.get("tag"), v.get("label")
            if tag:
                lst = runs.setdefault(url, [])
                cur = lst[-1] if lst else None
                if cur is None or cur["tag"] != tag:
                    lst.append({"url": url, "tag": tag, "label": label, "made": d, "price": ask,
                                "reaffirmed": 0, "latest_label": label})
                else:
                    if label != cur["latest_label"]:
                        cur["reaffirmed"] += 1
                        cur["latest_label"] = label
                    if cur["price"] is None and ask is not None:  # no ask when the tag appeared
                        cur["price"], cur["made"] = ask, d
            for p in (v.get("predictions") or []) + (((c.get("analysis") or {}).get("sell_verdict") or {}).get("predictions") or []):
                if not isinstance(p, dict) or p.get("type") not in PRED_TYPES:
                    continue
                key = (url, p.get("text"), p.get("price"), p.get("by"))
                if key not in preds:
                    preds[key] = {**p, "url": url, "made": p.get("made") or d}

    # A single mispriced listing (e.g. ¥28,000 between two ¥42k readings) would
    # decide a call on its own; drop points far below both neighbours.
    for url, pts in series.items():
        series[url] = [pts[i] for i in range(len(pts))
                       if not (0 < i < len(pts) - 1
                               and pts[i][1] < pts[i - 1][1] * (1 - OUTLIER)
                               and pts[i][1] < pts[i + 1][1] * (1 - OUTLIER))]

    noise = {}
    for url, pts in series.items():
        moves = sorted(abs(pts[i][1] / pts[i - 1][1] - 1) for i in range(1, len(pts)) if pts[i - 1][1])
        if len(moves) >= NOISE_MIN_MOVES:
            q = moves[min(len(moves) - 1, int(NOISE_PCTL * len(moves)))]
            noise[url] = round(min(NOISE_CAP, max(THRESHOLD, q)), 3)

    def confirmed_run(pts, test):
        """First point that completes CONFIRM_READINGS consecutive readings passing test."""
        run = []
        for d, p in pts:
            run = run + [(d, p)] if test(p) else []
            if len(run) >= CONFIRM_READINGS:
                return min(run, key=lambda x: x[1]), run[-1]
        return None

    as_of = snaps[-1][0] if snaps else None
    now = now or (_dt(as_of) if as_of else datetime.now(JST))

    ci = _mytier(root)

    def judge(url, tag, price, made_s):
        """Outcome of a call (tag at price, made at made_s): the same rules for real calls and the baseline."""
        made = _dt(made_s)
        end = made + timedelta(days=WINDOW_DAYS)
        after = [(d, p) for d, p in series.get(url, []) if made < _dt(d) <= end]
        low = min(after, key=lambda x: x[1]) if after else None
        last = after[-1] if after else None
        th = noise.get(url, THRESHOLD)
        floor = price * (1 - th)
        run = confirmed_run(after, lambda p: p <= floor)
        dipped = run[0] if run else None
        matured = now >= end
        status, why = "pending", ""
        if tag in BUYISH:
            if dipped:
                status, why = "wrong", f"dropped to ¥{dipped[1]:,} on {dipped[0][:10]} (held under −{th:.0%} for {CONFIRM_READINGS} checks)"
            elif matured:
                status, why = "right", f"never held more than {th:.0%} cheaper in {WINDOW_DAYS} days"
        elif tag in WAITISH:
            if dipped:
                status, why = "right", f"dropped to ¥{dipped[1]:,} on {dipped[0][:10]} (held under −{th:.0%} for {CONFIRM_READINGS} checks)"
            elif matured:
                if last and last[1] >= price * (1 + th):
                    status, why = "wrong", f"rose to ¥{last[1]:,} without a dip"
                else:
                    status, why = "neutral", "no clear move either way"
        else:
            status, why = "unscored", "Defer isn't scored"
        ret = mkt = rel = edge = None
        if matured and last:
            ret = (last[1] / price - 1) * 100
            a, b = _level_at(ci, made_s), _level_at(ci, end.isoformat())
            if a and b:
                mkt = (b / a - 1) * 100
                rel = ret - mkt
                edge = rel if tag in BUYISH else -rel if tag in WAITISH else None
        return {"made": made, "end": end, "low": low, "last": last, "th": th, "status": status, "why": why, "final": matured,
                "ret": ret, "mkt": mkt, "rel": rel, "edge": edge}

    calls = []
    for lst in runs.values():
        for r in lst:
            if r["price"] is None:
                continue
            j = judge(r["url"], r["tag"], r["price"], r["made"])
            low, last = j["low"], j["last"]
            calls.append({
                "url": r["url"], "name": names.get(r["url"], r["url"]), "tag": r["tag"],
                "label": r["label"], "latest_label": r["latest_label"], "reaffirmed": r["reaffirmed"],
                "made": r["made"], "price": r["price"], "window_end": j["end"].isoformat(),
                "days_in": min(WINDOW_DAYS, max(0, (now - j["made"]).days)),
                "low": low[1] if low else None, "low_pct": _pct(low[1], r["price"]) if low else None,
                "now": last[1] if last else None, "now_pct": _pct(last[1], r["price"]) if last else None,
                "status": j["status"], "why": j["why"], "threshold": j["th"], "final": j["final"],
                "ret_pct": _r1(j["ret"]), "mkt_pct": _r1(j["mkt"]), "rel_pts": _r1(j["rel"]), "edge_pts": _r1(j["edge"]),
            })

    # Baseline: a Buy and a Watch call on every day (first check of each JST day) for every card that had a scored call.
    base = {"buy": [], "watch": []}
    for url in {c["url"] for c in calls if c["tag"] in BUYISH | WAITISH}:
        seen = set()
        for d, p in series.get(url, []):
            day = _dt(d).astimezone(JST).date()
            if day in seen:
                continue
            seen.add(day)
            for grp, tag in (("buy", "buy"), ("watch", "watch")):
                j = judge(url, tag, p, d)
                if j["final"]:
                    base[grp].append(j)

    calls.sort(key=lambda c: c["made"], reverse=True)

    predictions = []
    for p in preds.values():
        made = _dt(p["made"])
        by = datetime.fromisoformat(p["by"]).replace(tzinfo=JST) + timedelta(days=1)  # end of that day
        pts = series.get(p["url"], [])
        below = p["type"] == "touch_below"
        hit_fn = (lambda x: x <= p["price"]) if below else (lambda x: x >= p["price"])
        at_made = [x for d, x in pts if _dt(d) <= made]
        after = [(d, x) for d, x in pts if made < _dt(d) < by]
        hit = next(((d, x) for d, x in after if hit_fn(x)), None)
        latest = pts[-1][1] if pts else None
        if at_made and hit_fn(at_made[-1]):
            status, why = "void", "already true when made"
        elif hit:
            status, why = "yes", f"¥{hit[1]:,} on {hit[0][:10]}"
        elif now >= by:
            status, why = "no", "deadline passed"
        else:
            status, why = "open", f"{(by - now).days} days left"
        predictions.append({
            "url": p["url"], "name": names.get(p["url"], p["url"]), "text": p.get("text", ""),
            "p": p.get("p"), "type": p["type"], "price": p["price"], "by": p["by"], "made": p["made"],
            "status": status, "why": why, "now": latest, "final": now >= by,
            "gap_pct": _pct(p["price"], latest) if latest else None,
        })
    predictions.sort(key=lambda x: (x["by"], x["name"]))

    # Limit-odds model (data/odds_log.json, written by odds_model.py on each full check):
    # each entry is two forecasts, "a listing at <= price within 30 / 90 days".
    model_odds = []
    log_path = root / "data" / "odds_log.json"
    if log_path.exists():
        for e in json.loads(log_path.read_text(encoding="utf-8")).get("entries", []):
            made = _dt(e["made"])
            pts = series.get(e["url"], [])
            for days, pk in ((30, "p30"), (90, "p90")):
                by = made + timedelta(days=days)
                hit = next(((d, x) for d, x in pts if made < _dt(d) <= by and x <= e["price"]), None)
                status = "yes" if hit else ("no" if now >= by else "open")
                model_odds.append({"url": e["url"], "name": names.get(e["url"], e["url"]), "kind": e.get("kind"),
                                   "price": e["price"], "ask": e.get("ask"), "days": days, "p": e[pk],
                                   "made": e["made"], "by": by.date().isoformat(), "status": status, "final": now >= by,
                                   "why": f"¥{hit[1]:,} on {hit[0][:10]}" if hit else ""})
    def brier(rows):
        """Brier score of final yes/no forecasts: {n, brier, expected_yes, actual_yes}."""
        rows = [x for x in rows if x.get("final") and x["status"] in ("yes", "no") and isinstance(x.get("p"), (int, float))]
        if not rows:
            return {"n": 0, "brier": None, "expected_yes": None, "actual_yes": 0}
        return {"n": len(rows), "brier": round(sum((x["p"] - (x["status"] == "yes")) ** 2 for x in rows) / len(rows), 3),
                "expected_yes": round(sum(x["p"] for x in rows), 1), "actual_yes": sum(1 for x in rows if x["status"] == "yes")}

    def rates(js):
        n = len(js)
        out = {k: sum(1 for j in js if j["status"] == k) for k in ("right", "wrong", "neutral")}
        out["n"] = n
        out["right_pct"] = round(out["right"] / n * 100, 1) if n else None
        rel = [j["rel"] for j in js if j["rel"] is not None]
        out["rel_pts"] = round(sum(rel) / len(rel), 1) if rel else None
        return out

    def group(cs):
        js = [{"status": c["status"], "rel": c["rel_pts"]} for c in cs]
        out = rates(js)
        edge = [c["edge_pts"] for c in cs if c["edge_pts"] is not None]
        out["edge_pts"] = round(sum(edge) / len(edge), 1) if edge else None
        return out

    closed = [c for c in calls if c["final"] and c["status"] in ("right", "wrong", "neutral")]
    early = [c for c in calls if not c["final"] and c["status"] in ("right", "wrong")]
    pending_calls = [c for c in calls if c["status"] == "pending"]
    next_close = min((c["window_end"] for c in calls if not c["final"] and c["tag"] in BUYISH | WAITISH), default=None)
    pred_open = [x for x in predictions if not x["final"] and x["status"] != "void"]
    mo30, mo90 = [x for x in model_odds if x["days"] == 30], [x for x in model_odds if x["days"] == 90]
    summary = {
        "calls": {k: sum(1 for c in calls if c["status"] == k) for k in ("right", "wrong", "neutral", "pending")},
        "calls_scored": len(closed),
        "closed": {"right": sum(1 for c in closed if c["status"] == "right"), "wrong": sum(1 for c in closed if c["status"] == "wrong"),
                   "neutral": sum(1 for c in closed if c["status"] == "neutral"),
                   "buy": group([c for c in closed if c["tag"] in BUYISH]), "watch": group([c for c in closed if c["tag"] in WAITISH])},
        "early": {"right": sum(1 for c in early if c["status"] == "right"), "wrong": sum(1 for c in early if c["status"] == "wrong")},
        "pending": len(pending_calls), "next_close": next_close,
        "baseline": {"buy": rates(base["buy"]), "watch": rates(base["watch"])},
        **{k: v for k, v in (lambda b: {"odds_resolved": b["n"], "brier": b["brier"], "expected_yes": b["expected_yes"], "actual_yes": b["actual_yes"]})(brier(predictions)).items()},
        "odds_open": len(pred_open),
        "odds_early_yes": sum(1 for x in pred_open if x["status"] == "yes"),
        "model_odds": {
            "logged": len(mo30), "open": sum(1 for x in mo90 if not x["final"]),
            "h30": {**brier(mo30), "early_yes": sum(1 for x in mo30 if not x["final"] and x["status"] == "yes"), "open": sum(1 for x in mo30 if not x["final"])},
            "h90": {**brier(mo90), "early_yes": sum(1 for x in mo90 if not x["final"] and x["status"] == "yes"), "open": sum(1 for x in mo90 if not x["final"])},
        },
    }
    out = root / "data" / "calls.json"
    out.write_text(json.dumps({"as_of": as_of, "window_days": WINDOW_DAYS, "threshold": THRESHOLD, "confirm_readings": CONFIRM_READINGS,
                               "noise_threshold_pctl": NOISE_PCTL, "noise_threshold_cap": NOISE_CAP,
                               "summary": summary, "calls": calls, "predictions": predictions,
                               "model_odds": model_odds},
                              ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return out


if __name__ == "__main__":
    p = build()
    s = json.loads(p.read_text(encoding="utf-8"))["summary"]
    print(f"Rebuilt {p.relative_to(ROOT)}: calls {s['calls']} (closed windows {s['closed']['right']} right, {s['closed']['wrong']} wrong), "
          f"odds scored {s['odds_resolved']}, open {s['odds_open']}")

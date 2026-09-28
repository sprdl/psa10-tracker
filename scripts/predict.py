#!/usr/bin/env python3
"""
"You vs the model": five weekly questions about your own cards, scored against the limit-odds model.

    python3 scripts/predict.py              # generate this week's questions if missing, resolve, print
    python3 scripts/predict.py --dry-run    # same, without writing data/predict.json

build_history.py calls update() whenever a snapshot is published (price checks, email alerts,
evaluations), so questions appear with the first publish of a week and resolve as prices come in.

A week runs Monday 00:00 → Friday 23:59 JST. Questions are made from the latest snapshot, one per
card, at most one "climb" question:
  - "Will a listing drop to ¥X or less by Friday?" with X = your limit, the Definitely-buy or Buy line
    (when 2–15% below today's lowest ask), otherwise a round price about 5% below;
  - "Will the lowest ask climb to ¥X or more?" about 6% above, for the card that rose most this week.
Only questions the model gives between 15% and 85% are used, so neither side gets a free point.
The model's odds use the limit-odds model (data/odds_model.json) scaled to the days until Friday:
z = ln(target / ask) / (σ30 · √(days/30)), P = 1.29 × share of historical 30-day endpoints beyond z
(same maths as scripts/odds_model.py, shorter horizon). Frozen when the question is made.

Resolution: every snapshot (quick, full or email alert) between the question's creation and Friday
23:59 counts. A drop question is Yes when any snapshot's lowest PSA10 ask is at or below the target
(a climb question: at or above). Answers are saved by the site's form (scripts/set_predictions.py);
answers given after a question resolved or closed don't count.

data/predict.json: {"weeks": {"2026-09-28": {"created", "close", "questions": [
    {"id": "2026-09-28-1", "url", "name", "dir": "below"|"above", "target", "ask", "lo30", "hi30",
     "model": 0.41, "why": "your limit", "days"}],
  "answers": {qid: {"p": 0.35, "at": iso}}, "results": {qid: {"outcome": 1|0, "at": iso, "extreme": price}}}}}
"""
import json
import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JST = timezone(timedelta(hours=9))
N_QUESTIONS = 5
P_MIN, P_MAX = 0.15, 0.85

sys.path.insert(0, str(ROOT / "scripts"))
import odds_model  # noqa: E402


def ts(s):
    d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    return d if d.tzinfo else d.replace(tzinfo=JST)


def week_start(now):
    d = now.astimezone(JST).date()
    return d - timedelta(days=d.weekday())


def close_of(monday):
    friday = monday + timedelta(days=4)
    return datetime(friday.year, friday.month, friday.day, 23, 59, 59, tzinfo=JST)


def short_odds(model, name, ask, target, days):
    """Chance the lowest ask touches target within `days` (drop or climb), 30-day model scaled."""
    if not model or not ask or not target or days <= 0:
        return None
    code = odds_model.card_code(model, name)
    s30 = (model["cards"][code][0] if code else model["pool_sigma"][0]) * math.sqrt(days / 30)
    a = model["about"]
    z = math.log(target / ask) / s30
    qs = model["z_end30"]
    share = odds_model.z_share(qs, z) if target < ask else 1 - odds_model.z_share(qs, z)
    return round(min(a.get("cap", 0.99), a["touch_factor_30"] * share), 3)


def _round(v):
    step = 1000 if v >= 30000 else 500
    return int(round(v / step) * step)


def snapshots(root):
    m = json.loads((root / "data" / "manifest.json").read_text(encoding="utf-8"))
    snaps = sorted([s for s in m.get("snapshots", []) if s.get("collected_at_jst")], key=lambda s: s["collected_at_jst"])
    return snaps


def load_snap(root, s):
    return json.loads((root / "data" / "snapshots" / s["file"]).read_text(encoding="utf-8"))


def generate(root, now, monday):
    snaps = snapshots(root)
    if not snaps:
        return None
    cur = load_snap(root, snaps[-1])
    hist = json.loads((root / "data" / "history.json").read_text(encoding="utf-8")).get("snapshots", []) if (root / "data" / "history.json").exists() else []
    limits = (json.loads((root / "data" / "limits.json").read_text(encoding="utf-8")) if (root / "data" / "limits.json").exists() else {}).get("limits", {})
    model = odds_model.load_model(root)
    close = close_of(monday)
    days = max(0.5, (close - now).total_seconds() / 86400)
    t_now = ts(cur["collected_at_jst"])
    cands = []
    for c in cur.get("cards", []):
        g = (c.get("grades") or {}).get("psa10") or {}
        ask = g.get("lowest_price")
        if not ask:
            continue
        url, name = c["url"], c.get("card_name_ja", "")
        series = [e["p"][url][0] for e in hist if e.get("p", {}).get(url)
                  and (t_now - ts(e["d"])).days <= 30]
        lo30, hi30 = (min(series), max(series)) if series else (ask, ask)
        wk = [e["p"][url][0] for e in hist if e.get("p", {}).get(url) and (t_now - ts(e["d"])).days <= 7]
        move7 = (ask / wk[0] - 1) if wk else 0
        tiers = (c.get("analysis") or {}).get("tiers") or {}
        opts = []
        lim = (limits.get(url) or {}).get("price")
        for label, v, bonus in (("your limit", lim, 3), ("Definitely-buy line", tiers.get("definitely_buy"), 2), ("Buy line", tiers.get("buy_upper"), 2)):
            if v and 0.02 <= 1 - v / ask <= 0.15:
                opts.append(("below", int(v), label, bonus))
        opts.append(("below", _round(ask * 0.95), "about 5% below today", 0))
        opts.append(("above", _round(ask * 1.06), "about 6% above today", 0.5 if move7 > 0.02 else -1))
        for d, target, why, bonus in opts:
            p = short_odds(model, name, ask, target, days)
            if p is None or not (P_MIN <= p <= P_MAX):
                continue
            cands.append({"url": url, "name": name, "dir": d, "target": target, "ask": ask, "lo30": lo30, "hi30": hi30,
                          "model": p, "why": why, "days": round(days, 1), "_score": bonus - abs(p - 0.5)})
    cands.sort(key=lambda q: -q["_score"])
    picked, used, above = [], set(), 0
    for q in cands:
        if q["url"] in used or (q["dir"] == "above" and above >= 1):
            continue
        used.add(q["url"])
        above += q["dir"] == "above"
        picked.append(q)
        if len(picked) == N_QUESTIONS:
            break
    for i, q in enumerate(picked, 1):
        q.pop("_score")
        q["id"] = f"{monday.isoformat()}-{i}"
    return {"created": now.replace(microsecond=0).isoformat(), "close": close.isoformat(), "questions": picked,
            "answers": {}, "results": {}}


def resolve(root, week, now):
    """Mark questions Yes as soon as a snapshot touches the target; No once the week has closed."""
    snaps = snapshots(root)
    created, close = ts(week["created"]), ts(week["close"])
    todo = [q for q in week["questions"] if q["id"] not in week["results"]]
    if not todo:
        return 0
    rel = [s for s in snaps if created <= ts(s["collected_at_jst"]) <= close]
    extremes = {q["id"]: None for q in todo}
    n = 0
    for s in rel:
        d = load_snap(root, s)
        asks = {c["url"]: ((c.get("grades") or {}).get("psa10") or {}).get("lowest_price") for c in d.get("cards", [])}
        for q in todo:
            if q["id"] in week["results"]:
                continue
            a = asks.get(q["url"])
            if a is None:
                continue
            e = extremes[q["id"]]
            extremes[q["id"]] = a if e is None else (min(e, a) if q["dir"] == "below" else max(e, a))
            if (q["dir"] == "below" and a <= q["target"]) or (q["dir"] == "above" and a >= q["target"]):
                week["results"][q["id"]] = {"outcome": 1, "at": d.get("collected_at_jst"), "extreme": a}
                n += 1
    if now > close:
        for q in todo:
            if q["id"] not in week["results"]:
                week["results"][q["id"]] = {"outcome": 0, "at": close.isoformat(), "extreme": extremes[q["id"]]}
                n += 1
    return n


def update(root=ROOT, now=None, write=True):
    now = now or datetime.now(JST)
    path = root / "data" / "predict.json"
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    weeks = data.setdefault("weeks", {})
    monday = week_start(now)
    key = monday.isoformat()
    made = False
    # new questions from Monday until Thursday night, so there's always at least a day to answer
    if key not in weeks and now.astimezone(JST).weekday() <= 3:
        w = generate(root, now, monday)
        if w and w["questions"]:
            weeks[key] = w
            made = True
    resolved = sum(resolve(root, w, now) for w in weeks.values())
    if write and (made or resolved or not path.exists()):
        data["about"] = "You vs the model: weekly questions, answers and results. See scripts/predict.py."
        path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return made, resolved, data


if __name__ == "__main__":
    made, resolved, data = update(write="--dry-run" not in sys.argv)
    wk = data.get("weeks", {}).get(week_start(datetime.now(JST)).isoformat())
    print(f"predict: {'new questions' if made else 'no new questions'} · {resolved} resolved")
    for q in (wk or {}).get("questions", []):
        r = wk["results"].get(q["id"])
        print(f"  {q['id']} {q['name'][:22]} {q['dir']} ¥{q['target']:,} (ask ¥{q['ask']:,}, {q['why']}) model {q['model']:.0%}"
              + (f" → {'YES' if r['outcome'] else 'NO'}" if r else ""))

#!/usr/bin/env python3
"""
Which cards the price check must evaluate in the same run (FULL-CHECK step 8b, quick check Q5),
and the queue of cards that were just added or restored (data/eval_queue.json).

    python3 scripts/eval_queue.py                 # print the EVALUATE NOW block (same as the update scripts)
    python3 scripts/eval_queue.py add <id|url> "<why>"   # queue a card by hand (e.g. "re-evaluate after reprint news")
    python3 scripts/eval_queue.py drop <id|url>   # take a card off the queue without evaluating it

Why a queue (2026-10-10): a card added from an "Add card" request (or restored after Remove card)
used to depend on the run noticing it had no tiers. A restored card still carried its old tiers, and a
new card with no PSA10 listing yet was skipped, so neither was evaluated. Now:
  - scripts/card_requests.py add  queues every card it adds or restores;
  - scripts/apply_analysis.py     takes a card off the queue once a buy verdict (any tag, `defer`
                                  included) has been applied to it;
  - due()                         lists the queued cards first (whatever their PSA10 market), then the
                                  older rule: a PSA10 ask but no tiers and no verdict, or a `defer`
                                  verdict on a Monday (one fresh look a week).
A queued card that isn't in the latest snapshot yet waits until a check publishes it.
Both quick_update.py and full_update.py print the block; at most PER_RUN cards are evaluated per run.
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JST = timezone(timedelta(hours=9))
PER_RUN = 3
ABOUT = ("Cards added or restored by an Add card request, waiting for their first evaluation in the same price "
         "check (scripts/eval_queue.py). apply_analysis.py removes a card once a buy verdict is applied.")


def path(root=ROOT):
    return root / "data" / "eval_queue.json"


def load(root=ROOT):
    p = path(root)
    d = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    d.setdefault("about", ABOUT)
    d.setdefault("queue", {})
    return d


def save(d, root=ROOT):
    path(root).write_text(json.dumps(d, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def to_url(x):
    x = str(x).strip().rstrip("/")
    return x if x.startswith("http") else f"https://snkrdunk.com/apparels/{x}"


def add(url, name="", why="", root=ROOT):
    d = load(root)
    d["queue"][to_url(url)] = {"name": name, "why": why,
                               "since": datetime.now(JST).replace(microsecond=0).isoformat()}
    save(d, root)


def remove(urls, root=ROOT):
    """Drop these cards from the queue; True if the file changed."""
    d = load(root)
    hit = [u for u in (to_url(u) for u in urls) if u in d["queue"]]
    for u in hit:
        del d["queue"][u]
    if hit:
        save(d, root)
    return bool(hit)


def latest_snapshot(root=ROOT):
    m = json.loads((root / "data" / "manifest.json").read_text(encoding="utf-8"))
    snaps = sorted([s for s in m.get("snapshots", []) if s.get("collected_at_jst")], key=lambda s: s["collected_at_jst"])
    if not snaps:
        return {}
    return json.loads((root / "data" / "snapshots" / snaps[-1]["file"]).read_text(encoding="utf-8"))


def due(root=ROOT, now=None):
    """[{url, ask, name, why}] in order: queued cards (published ones), then cards with a PSA10 ask but
    no tiers and no verdict (or `defer` on a Monday). Also returns the queued cards not published yet."""
    snap = latest_snapshot(root)
    cards = {c.get("url", "").rstrip("/"): c for c in snap.get("cards", [])}
    rp = root / "data" / "removed_cards.json"
    gone = {to_url(k) for k in ((json.loads(rp.read_text(encoding="utf-8")).get("removed") or {}) if rp.exists() else {})}
    monday = (now or datetime.now(JST)).weekday() == 0
    out, waiting, seen = [], [], set()
    for url, q in load(root)["queue"].items():
        if url in gone:
            continue
        c = cards.get(url)
        if not c:
            waiting.append({"url": url, "name": q.get("name", ""), "why": q.get("why", "")})
            continue
        ask = ((c.get("grades") or {}).get("psa10") or {}).get("lowest_price")
        out.append({"url": url, "ask": ask, "name": c.get("card_name_ja", ""), "why": q.get("why") or "queued"})
        seen.add(url)
    for url, c in cards.items():
        if url in seen or url in gone:
            continue
        a = c.get("analysis") or {}
        ask = ((c.get("grades") or {}).get("psa10") or {}).get("lowest_price")
        tag = (a.get("verdict") or {}).get("tag")
        if ask and not a.get("tiers") and (not tag or (tag == "defer" and monday)):
            out.append({"url": url, "ask": ask, "name": c.get("card_name_ja", ""),
                        "why": "weekly look at a deferred card" if tag else "PSA10 market, no tiers yet"})
    return out, waiting


def print_due(root=ROOT, step="FULL-CHECK step 8b"):
    items, waiting = due(root)
    if not items:
        print("\nEVALUATE NOW: none (no new cards, every card with a PSA10 market has tiers).")
    else:
        print(f"\nEVALUATE NOW ({step}) — the run is not finished until each of these has an evaluation applied:")
        for i, it in enumerate(items):
            ask = f"PSA10 ask ¥{it['ask']:,}" if it["ask"] else "no PSA10 ask (evaluate anyway: `defer` with reasoning)"
            print(f"  {'' if i < PER_RUN else '(next run) '}{it['url']}  {ask}  {it['name']}  [{it['why']}]")
        print("  For each (at most 3 per run): `python3 scripts/eval_context.py <id>`, then the pokemon-tcg-card-evaluation")
        print("  skill end to end, including apply_analysis.py. A new card is exactly what this step is for.")
    for w in waiting:
        print(f"  waiting to be published by a check: {w['url']}  {w['name']}  [{w['why']}]")
    return items


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["add"] and len(a) >= 2:
        add(a[1], why=a[2] if len(a) > 2 else "queued by hand")
        print(f"Queued {to_url(a[1])}. Commit data/eval_queue.json (the next price check evaluates it).")
    elif a[:1] == ["drop"] and len(a) == 2:
        print("Dropped." if remove([a[1]]) else "Not in the queue.")
    else:
        print_due()

#!/usr/bin/env python3
"""
Today's full-check plan: which cards get which SNKRDUNK reads, which altema pages are due,
and the Monday / monthly extras. scripts/full_update.py calls build_plan() again when it
publishes, so the rules below live in one place.

    python3 pricecheck/plan.py

Prints a short summary plus two ready-made JS lines to paste into the in-page scripts:
    PLAN = [["455596","full",0], ...]            -> pricecheck/scripts/snkrdunk_full.js
    ALTEMA = [["224087","https://…","due"], ...] -> pricecheck/scripts/altema_batch.js

Rules (unchanged from the old step 2/3 of the full check):
  SNKRDUNK  "full" (product page + PSA10 and A listings) for cards with a PSA10 market in the
            latest snapshot, and for every card on Mondays; "tile" (product page only) otherwise.
            A "tile" card whose PSA10 tile shows a price gets its listings read too (in the page
            script), so a new market is captured from its first day. Third field 1 = fetch the
            photo URL (the card has none on file).
  altema    altema_mode "daily": every run while PSA10 population < 8,000 (or unknown), Mondays
            only once it's 8,000+.  "weekly_until_graded": Mondays, or when this run shows PSA10
            activity (listed as "ifpsa"; full_update.py keeps the result only if the SNKRDUNK line
            shows a PSA10 ask or a completed PSA10 sale).
"""
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

JST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parent.parent
MATURE_POP = 8000


def load_cards(root=ROOT):
    """pricecheck/references/cards.json + data/tracked_cards.json (repo list wins on nothing; ids unique)."""
    base = json.loads((root / "pricecheck" / "references" / "cards.json").read_text(encoding="utf-8"))["cards"]
    cards, seen = [], set()
    for c in base:
        cards.append(dict(c, _source="pricecheck")); seen.add(c["snkrdunk_id"])
    tp = root / "data" / "tracked_cards.json"
    if tp.exists():
        t = json.loads(tp.read_text(encoding="utf-8"))
        for c in (t.get("cards") if isinstance(t, dict) else t) or []:
            if c.get("snkrdunk_id") and c["snkrdunk_id"] not in seen:
                cards.append(dict(c, _source="tracked")); seen.add(c["snkrdunk_id"])
    rp = root / "data" / "removed_cards.json"   # removed with the site's Remove card button
    if rp.exists():
        gone = set((json.loads(rp.read_text(encoding="utf-8")).get("removed") or {}).keys())
        cards = [c for c in cards if c["snkrdunk_id"] not in gone]
    return cards


SCOUT_READS = 20  # scout card pages read per full check (about 2.5 s each)
SCOUT_EVERY_H = 40  # Scout runs when data/scout.json is older than this (about every other day)


def pokeca_slug(name):
    """pokeca-chart card page slug from the card name's [SET NNN/NNN] code: "[SV8a 217/187]" -> "sv8a-217-187".
    A card can override it with "pokeca_slug" in its card-list entry ("-" = not on pokeca-chart)."""
    m = re.search(r"\[\s*([A-Za-z0-9-]+)\s+(\d+)\s*/\s*(\d+)\s*\]", name or "")
    return f"{m[1].lower()}-{m[2]}-{m[3]}" if m else None


def latest_snapshot(root=ROOT):
    m = json.loads((root / "data" / "manifest.json").read_text(encoding="utf-8"))
    snaps = sorted([s for s in m.get("snapshots", []) if s.get("collected_at_jst")], key=lambda s: s["collected_at_jst"])
    if not snaps:
        return None, None
    p = root / "data" / "snapshots" / snaps[-1]["file"]
    return p, json.loads(p.read_text(encoding="utf-8"))


def build_plan(root=ROOT, now=None):
    now = now or datetime.now(JST)
    monday = now.weekday() == 0
    snap_path, snap = latest_snapshot(root)
    by_id = {}
    for c in (snap or {}).get("cards", []):
        by_id[c.get("url", "").rstrip("/").split("/")[-1]] = c
    plan, altema, skipped, prem, amiss = [], [], {}, [], []
    tracked_slugs = set()
    for c in load_cards(root):
        sid = c["snkrdunk_id"]
        prev = by_id.get(sid) or {}
        has_market = ((prev.get("grades") or {}).get("psa10") or {}).get("lowest_price") is not None
        mode = "full" if (has_market or monday) else "tile"
        plan.append([sid, mode, 0 if c.get("image_url") else 1])
        slug = c.get("pokeca_slug") or pokeca_slug(c.get("card_name_ja", ""))
        if slug and slug != "-":
            tracked_slugs.add(slug)
        if has_market and slug and slug != "-":
            prem.append([sid, slug])
        url = c.get("altema_url")
        pop = prev.get("psa10_population")
        amode = c.get("altema_mode", "daily")
        if not url:
            skipped[sid] = "no altema page on file yet"
            amiss.append([sid, c.get("card_name_ja", "")])
        elif amode == "weekly_until_graded":
            altema.append([sid, url, "due" if monday else "ifpsa"])
        elif isinstance(pop, int) and pop >= MATURE_POP and not monday:
            skipped[sid] = "weekly population check (mature card, 8,000+ graded)"
        else:
            altema.append([sid, url, "due"])
    odds_built = None
    op = root / "data" / "odds_model.json"
    if op.exists():
        try:
            odds_built = json.loads(op.read_text(encoding="utf-8")).get("built")
        except Exception:
            pass
    odds_age = None
    if odds_built:
        try:
            odds_age = (now.date() - datetime.fromisoformat(str(odds_built)[:10]).date()).days
        except Exception:
            pass
    rp = root / "data" / "removed_cards.json"   # removed cards aren't suggested again by Scout
    if rp.exists():
        for v in (json.loads(rp.read_text(encoding="utf-8")).get("removed") or {}).values():
            slug = pokeca_slug(v.get("name"))
            if slug:
                tracked_slugs.add(slug)
    scout = {"skip": sorted(tracked_slugs), "read": {}, "n": SCOUT_READS}
    sp = root / "data" / "scout.json"
    if sp.exists():
        try:
            sd = json.loads(sp.read_text(encoding="utf-8"))
            upd = sd.get("updated")
            # every other day is enough for discovery (2026-10-08); when it's not due the plan has no scout
            # step, full_update.py doesn't require SC lines, and the SCOUT line prints null
            if upd and (now - datetime.fromisoformat(upd)).total_seconds() < SCOUT_EVERY_H * 3600:
                scout = None
            if scout is not None:
                scout["skip"] = sorted(tracked_slugs | set(sd.get("dismissed") or []))
                scout["read"] = {k: v.get("read", "") for k, v in (sd.get("pool") or {}).items() if v.get("read")}
        except Exception:
            pass
    held = []
    try:   # bought cards and unopened sealed items that aren't tracked cards (scripts/holdings_prices.py)
        sys.path.insert(0, str(root / "scripts"))
        import holdings_prices
        held = [[k, v] for k, v in holdings_prices.needed(root, {c["snkrdunk_id"] for c in load_cards(root)}).items()]
    except Exception as e:  # never break a price check over this
        print(f"(holdings prices skipped: {e})")
    return {
        "held": held, "now": now, "monday": monday, "scout": scout, "latest": snap_path.name if snap_path else None,
        "plan": plan, "altema": altema, "altema_skipped": skipped, "altema_missing": amiss, "premium": prem,
        "odds_model_built": odds_built, "odds_rebuild_due": odds_age is None or odds_age > 30,
    }


def main():
    p = build_plan()
    full = sum(1 for x in p["plan"] if x[1] == "full")
    print(f"{p['now']:%Y-%m-%d %A %H:%M} JST · latest snapshot {p['latest']} · "
          f"{'MONDAY: PSA tier check + release calendar due · ' if p['monday'] else ''}"
          f"odds model built {p['odds_model_built']}{' → REBUILD DUE (step 5b)' if p['odds_rebuild_due'] else ''}")
    print(f"SNKRDUNK: {full} full, {len(p['plan']) - full} tile-only · altema: "
          f"{sum(1 for a in p['altema'] if a[2] == 'due')} due, {sum(1 for a in p['altema'] if a[2] == 'ifpsa')} if PSA10 activity, "
          f"{len(p['altema_skipped'])} skipped")
    print("PLAN = " + json.dumps(p["plan"]))
    print("ALTEMA = " + json.dumps(p["altema"]))
    print("PREM = " + json.dumps(p["premium"]))
    print("HELD = " + json.dumps(p["held"]))
    print("SCOUT = " + json.dumps(p["scout"], separators=(",", ":")))
    if p["altema_missing"]:
        print("ALTEMA MISSING (step 1c) = " + json.dumps(p["altema_missing"], ensure_ascii=False))


if __name__ == "__main__":
    main()

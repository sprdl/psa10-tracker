#!/usr/bin/env python3
"""
Mercari prices for cards near your limit, saved to data/mercari.json for the site.

    python3 scripts/mercari.py --due                # which cards to check now + the CARDS line for the page script
    python3 scripts/mercari.py --js                 # pricecheck/scripts/mercari_check.js with those CARDS filled in
    python3 scripts/mercari.py - [--no-push] <<'EOF' # save the lines pricecheck/scripts/mercari_check.js returned
    MC 455596 14 6 61000
    MI 455596 m123456789 61000 F - 1700 1 1 %E3%83%96...
    EOF
    python3 scripts/mercari.py --show               # print what data/mercari.json holds now

Why only some cards: Mercari is read in the user's own browser with the same precautions as SNKRDUNK
(only when the user asks for a price check, hidden same-origin iframes, one page at a time, pauses,
no fetch/XHR, no scheduled runs). To keep the pages few, a check reads Mercari only for cards whose
SNKRDUNK lowest PSA10 ask is within 5% of the user's limit (ask <= limit x 1.05): the cards where a
cheaper listing elsewhere could actually turn into a buy. Full and quick checks both do it.

Effective price = listing price + the あんしん鑑定 fee (¥1,700; free for items of ¥100,000 or more since
2026-09-04). あんしん鑑定 only exists when the seller enabled it; a listing without it is kept at its
bare price but flagged ("no あんしん鑑定: check the cert yourself"). For an auction the price is the
current bid, so the effective price is a lower bound.

The pilot (2026-10-03, project doc mercari-pilot) found Mercari not cheaper on average, with noisy
titles. So only listings whose title says PSA10 for this card number count (no other grades or
graders, no lots), and the item page itself is opened for the cheapest ones to confirm price,
auction end and the あんしん鑑定 option.

data/mercari.json: {"updated", "about", "cards": {snkrdunk url: {
    "checked": iso, "limit": 65000, "ask": 66000, "seen": 14, "matched": 6, "cheapest": 61000,
    "items": [{"id": "m123", "url": "https://jp.mercari.com/item/m123", "price": 61000, "auction": false,
               "ends": iso|null, "fee": 1700|0|null, "anshin": true|false|null,  "eff": 62700,
               "grade": true, "num": true|null, "title": "..."}],
    "error": "..."}}}
The site shows the cheapest effective price on each card page and raises an alert when a fixed-price
listing is at or under the limit, or an auction ending within 2 hours is still at or under it.
"""
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import unquote

JST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parent.parent
PATH = ROOT / "data" / "mercari.json"
NEAR = 1.05            # read Mercari when the SNKRDUNK ask is within 5% of the limit
FEE, FREE_FROM = 1700, 100000
KEEP_DAYS = 14         # drop card entries not refreshed for this long


def die(msg):
    print(f"\nERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def sid_of(url):
    return str(url or "").rstrip("/").split("/")[-1]


def anshin_fee(price):
    return 0 if price >= FREE_FROM else FEE


def latest_snapshot(root=ROOT):
    m = json.loads((root / "data" / "manifest.json").read_text(encoding="utf-8"))
    snaps = sorted([s for s in m.get("snapshots", []) if s.get("collected_at_jst")], key=lambda s: s["collected_at_jst"])
    if not snaps:
        return None
    return json.loads((root / "data" / "snapshots" / snaps[-1]["file"]).read_text(encoding="utf-8"))


def removed(root=ROOT):
    p = root / "data" / "removed_cards.json"
    if not p.exists():
        return set()
    d = json.loads(p.read_text(encoding="utf-8"))
    return {sid_of(u) for u in (d.get("removed") or d.get("cards") or {})}


def search_terms(name):
    """'ブラッキーex SAR [SV8a 217/187](拡張パック…)' -> ('ブラッキーex SAR PSA10', '217/187')."""
    short = re.split(r"\s*[\[［(（]", name or "", maxsplit=1)[0].strip()
    m = re.search(r"(\d{2,3}/\d{2,3})", name or "")
    return f"{short} PSA10".strip(), (m.group(1) if m else "")


def due(root=ROOT, near=NEAR):
    """Cards to read on Mercari: a limit is set and the SNKRDUNK PSA10 ask is at most limit x near."""
    snap = latest_snapshot(root) or {}
    lp = root / "data" / "limits.json"
    limits = json.loads(lp.read_text(encoding="utf-8")).get("limits", {}) if lp.exists() else {}
    lim_by = {sid_of(u): v.get("price") for u, v in limits.items() if isinstance(v, dict) and v.get("price")}
    gone = removed(root)
    out = []
    for c in snap.get("cards", []):
        sid = sid_of(c.get("url"))
        lim = lim_by.get(sid)
        ask = ((c.get("grades") or {}).get("psa10") or {}).get("lowest_price")
        if sid in gone or not lim or not ask or ask > lim * near:
            continue
        q, num = search_terms(c.get("card_name_ja", ""))
        out.append({"id": sid, "q": q, "num": num, "lim": int(lim), "ask": int(ask), "name": c.get("card_name_ja", "")})
    return sorted(out, key=lambda x: x["ask"] / x["lim"])


def print_due(root=ROOT, header=True):
    """The MERCARI block printed at the end of full_update.py / quick_update.py."""
    try:
        cards = due(root)
    except Exception as e:  # never break a price check over this
        print(f"\nMERCARI: could not work out the due cards ({e}).")
        return
    if not cards:
        print("\nMERCARI: none due (no card's SNKRDUNK ask is within 5% of your limit).")
        return
    if header:
        print("\nMERCARI NOW (pricecheck/MERCARI.md; required in full AND quick checks) — read Mercari for these cards (SNKRDUNK ask within 5% of the limit):")
    for c in cards:
        print(f"  {c['id']}  ask ¥{c['ask']:,} / limit ¥{c['lim']:,} ({c['ask'] / c['lim'] - 1:+.1%})  {c['name'][:40]}")
    js = json.dumps([{k: c[k] for k in ("id", "q", "num", "lim")} for c in cards], ensure_ascii=False, separators=(",", ":"))
    print("  CARDS = " + js)


def decode(lines, now=None):
    """MC/MI/ME lines from mercari_check.js -> {snkrdunk id: entry}."""
    now = now or datetime.now(JST).replace(microsecond=0)
    out = {}
    for ln in lines:
        p = ln.strip().split(" ")
        if len(p) < 3 or p[0] not in ("MC", "MI", "ME"):
            continue
        e = out.setdefault(p[1], {"checked": now.isoformat(), "items": []})
        if p[0] == "ME":
            e["error"] = unquote(p[2])
        elif p[0] == "MC":
            e["seen"], e["matched"] = int(p[2]), int(p[3])
            e["cheapest"] = None if p[4] == "-" else int(p[4])
        elif p[0] == "MI" and len(p) >= 10:
            price, auction = int(p[3]), p[4] == "A"
            ends = None if p[5] == "-" else datetime.fromtimestamp(int(p[5]) * 60, JST).isoformat()
            if p[6] == "n":
                fee, anshin = 0, False
            elif p[6] == "-":
                fee, anshin = anshin_fee(price), None     # offered, fee not readable: assume the standard one
            else:
                fee, anshin = int(p[6]), True
            e["items"].append({"id": p[2], "url": f"https://jp.mercari.com/item/{p[2]}", "price": price,
                               "auction": auction, "ends": ends, "fee": fee, "anshin": anshin,
                               "eff": price + fee, "grade": p[7] == "1",
                               "num": {"1": True, "0": False}.get(p[8]), "title": unquote(" ".join(p[9:]))})
    for e in out.values():   # a listing whose page names only other card numbers is another card: drop it
        e["items"] = [i for i in e["items"] if i["num"] is not False]
    for e in out.values():
        e["items"].sort(key=lambda x: x["eff"])
    return out


def save(entries, root=ROOT, push=True):
    if not entries:
        print("mercari: no lines to save.")
        return
    lims = {c["id"]: c for c in due(root, near=10)}  # limit + ask for every card with a limit
    data = json.loads(PATH.read_text(encoding="utf-8")) if PATH.exists() else {}
    data["about"] = ("Mercari PSA10 listings for cards whose SNKRDUNK ask is within 5% of the limit, read in the "
                     "user's browser during price checks (pricecheck/scripts/mercari_check.js → scripts/mercari.py). "
                     "eff = price + あんしん鑑定 fee (¥1,700, free from ¥100,000).")
    cards = data.setdefault("cards", {})
    now = datetime.now(JST)
    for url in list(cards):
        try:
            if now - datetime.fromisoformat(cards[url]["checked"]) > timedelta(days=KEEP_DAYS):
                del cards[url]
        except (KeyError, ValueError):
            del cards[url]
    lines = []
    for sid, e in entries.items():
        c = lims.get(sid) or {}
        e["limit"], e["ask"] = c.get("lim"), c.get("ask")
        cards[f"https://snkrdunk.com/apparels/{sid}"] = e
        if e.get("error"):
            lines.append(f"  {sid}: failed ({e['error']})")
            continue
        best = e["items"][0] if e["items"] else None
        alert = ""
        lim = e["limit"]
        if best and lim:
            fixed = [i for i in e["items"] if not i["auction"] and i["eff"] <= lim]
            soon = [i for i in e["items"] if i["auction"] and i["ends"] and i["eff"] <= lim
                    and datetime.fromisoformat(i["ends"]) - now <= timedelta(hours=2)]
            if fixed:
                alert = f"  ** AT/UNDER LIMIT: ¥{fixed[0]['eff']:,} incl. fee {fixed[0]['url']}"
            elif soon:
                alert = f"  ** AUCTION ending {soon[0]['ends'][11:16]} JST at ¥{soon[0]['eff']:,} incl. fee {soon[0]['url']}"
        lines.append(f"  {sid}: {e.get('matched', 0)} PSA10 match(es) of {e.get('seen', 0)}"
                     + (f", cheapest ¥{best['eff']:,} incl. fee ({'auction' if best['auction'] else 'fixed'}"
                        f"{'' if best['anshin'] is not False else ', no あんしん鑑定'})" if best else "")
                     + (f" vs SNKRDUNK ¥{e['ask']:,}, limit ¥{lim:,}" if e.get("ask") and lim else "") + alert)
    data["updated"] = now.replace(microsecond=0).isoformat()
    PATH.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print("mercari: saved " + str(len(entries)) + " card(s)")
    print("\n".join(lines))
    if not push:
        return
    for cmd in (["git", "add", str(PATH)], ["git", "commit", "-q", "-m", "mercari: listings near my limits"], ["git", "push", "-q"]):
        r = subprocess.run(cmd, cwd=root, text=True, capture_output=True)
        if r.returncode != 0 and "nothing to commit" not in (r.stdout + r.stderr):
            print(f"mercari: {' '.join(cmd)} failed: {(r.stderr or r.stdout).strip()}")
            return
    print("mercari: pushed.")


def main():
    args = sys.argv[1:]
    if "--js" in args:   # the page script with today's CARDS filled in, ready to paste into javascript_tool
        cards = due()
        if not cards:
            print("none due")
            return
        js = (ROOT / "pricecheck" / "scripts" / "mercari_check.js").read_text(encoding="utf-8")
        line = re.search(r"  const CARDS = \[.*?\];\n", js).group(0)
        cj = json.dumps([{k: c[k] for k in ("id", "q", "num", "lim")} for c in cards], ensure_ascii=False, separators=(",", ":"))
        print(js[js.index("(() => {"):].replace(line, f"  const CARDS = {cj};\n"))
        return
    if "--due" in args:
        print_due(header=False) if due() else print("none due")
        return
    if "--show" in args:
        print(PATH.read_text(encoding="utf-8") if PATH.exists() else "no data/mercari.json yet")
        return
    files = [a for a in args if not a.startswith("--")]
    text = sys.stdin.read() if not files or files[0] == "-" else Path(files[0]).read_text(encoding="utf-8")
    push = "--no-push" not in args
    if push:
        subprocess.run(["git", "pull", "--ff-only", "--quiet"], cwd=ROOT)
    save(decode(text.splitlines()), push=push)


if __name__ == "__main__":
    main()

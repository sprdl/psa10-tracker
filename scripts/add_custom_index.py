#!/usr/bin/env python3
"""
My-tier index: a daily, equal-weighted PSA10 index of the cards in the tier actually
being bought (modern Japanese Pokémon SAR / alt-art cards, ¥15k–150k at the base date).

Definition lives in data/custom_index.json -> "meta" (constituents + base prices).
Level = 100 × average over constituents of (today's price ÷ base price).
A constituent with no price today carries its last known price forward (flagged in
"carried"); one with no price ever is left out.

Daily use (the price-check skill does this once per JST day, with the full check):

    python3 scripts/add_custom_index.py --print-js
        prints the in-page extractor for https://pokeca-chart.com/gr/all-card/?sort=newest
        (it reads the rendered list only; no network requests). Run it there.

    python3 scripts/add_custom_index.py RESULT.json [--pokeca 105124] [--no-push]
        RESULT.json = the extractor's output ({"prices": {code: price}, "missing": [...]}).
        --pokeca = today's pokeca-chart PSA10 index value, stored alongside for comparison.
        Upserts today's JST entry, commits and pushes data/custom_index.json.

Changing constituents (quarterly review): edit meta.constituents and add the change to
meta.revisions. Keep the level continuous: set each new card's base to
price_on_change_date × 100 ÷ level_on_change_date, and rescale the others the same way.
"""
import argparse, json, os, subprocess, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILE = ROOT / "data" / "custom_index.json"
JST = timezone(timedelta(hours=9))

JS = r"""await (async () => {
  const CODES = %s;
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  for (let i = 0; i < 30 && !/PSA10価格/.test(document.querySelector('main')?.innerText || ''); i++) await sleep(300);
  const seen = {}, re = /\[([^\]]+)\][^\n]*\n\n[^\n]*\n\nPSA10価格\n\n([^\n]+)/g;
  const H = document.body.scrollHeight;
  for (let y = 0; y <= H + 1200; y += 600) {
    window.scrollTo(0, y); await sleep(120);
    const t = document.querySelector('main').innerText; let m;
    while ((m = re.exec(t))) seen[m[1].toLowerCase()] = m[2];
  }
  window.scrollTo(0, 0);
  const prices = {}, missing = [];
  for (const c of CODES) { const v = seen[c.toLowerCase()]; const p = v && /\d/.test(v) ? Number(v.replace(/[^\d]/g, '')) : null; if (p) prices[c] = p; else missing.push(c); }
  if (!Object.keys(seen).length) return { error: 'card list not found on page' };
  return { page_cards_seen: Object.keys(seen).length, prices, missing };
})()"""


def load():
    return json.loads(FILE.read_text(encoding="utf-8"))


def save(d):
    FILE.write_text(json.dumps(d, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def compute(meta, prices, prev_entry):
    rels, carried, left_out = [], [], []
    prev_prices = (prev_entry or {}).get("prices", {})
    used = {}
    for c in meta["constituents"]:
        code, base = c["code"], c["base"]
        p = prices.get(code)
        if p is None and code in prev_prices:
            p = prev_prices[code]; carried.append(code)
        if p is None:
            left_out.append(code); continue
        used[code] = p
        rels.append(p / base)
    if len(rels) < 0.8 * len(meta["constituents"]):
        sys.exit(f"ERROR: only {len(rels)}/{len(meta['constituents'])} constituents priced — not saving.")
    return round(100 * sum(rels) / len(rels), 2), used, carried, left_out


def git(*a, check=True):
    return subprocess.run(["git", *a], cwd=ROOT, text=True, capture_output=True, check=check,
                          env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("result", nargs="?")
    ap.add_argument("--pokeca", type=float, help="pokeca-chart PSA10 index value today")
    ap.add_argument("--no-push", action="store_true")
    ap.add_argument("--print-js", action="store_true")
    args = ap.parse_args()
    d = load()
    meta = d["meta"]
    if args.print_js:
        print(JS % json.dumps([c["code"] for c in meta["constituents"]], ensure_ascii=False))
        return
    if not args.result:
        ap.error("RESULT.json required")
    r = json.loads(Path(args.result).read_text(encoding="utf-8"))
    if r.get("error"):
        sys.exit(f"ERROR from extractor: {r['error']}")
    known = {c["code"] for c in meta["constituents"]}
    extra = set(r.get("prices", {})) - known
    if extra:
        print(f"warning: ignoring prices for non-constituents: {sorted(extra)}")
    today = datetime.now(JST).strftime("%Y-%m-%d")
    series = [e for e in d.get("series", []) if e["d"] != today]
    prev = series[-1] if series else None
    level, used, carried, left_out = compute(meta, r.get("prices", {}), prev)
    entry = {"d": today, "level": level, "n": len(used), "prices": used}
    if carried: entry["carried"] = carried
    if left_out: entry["left_out"] = left_out
    if args.pokeca: entry["pokeca_psa10"] = round(args.pokeca)
    series.append(entry)
    d["series"] = series
    save(d)
    chg = f" ({(level / prev['level'] - 1) * 100:+.1f}% vs {prev['d']})" if prev else ""
    print(f"My-tier index {today}: {level:.2f}{chg} · {len(used)}/{len(meta['constituents'])} priced"
          + (f" · carried: {', '.join(carried)}" if carried else "") + (f" · left out: {', '.join(left_out)}" if left_out else ""))
    movers = sorted(((c, used[c] / b["base"] - 1) for b in meta["constituents"] for c in [b["code"]] if c in used),
                    key=lambda x: x[1])
    if movers:
        print(f"  weakest vs base: {movers[0][0]} {movers[0][1]:+.1%} · strongest: {movers[-1][0]} {movers[-1][1]:+.1%}")
    if args.no_push:
        return
    git("add", "data/custom_index.json")
    if git("commit", "-m", f"my-tier index: {today} {level:.2f}", check=False).returncode != 0:
        print("Nothing to commit."); return
    p = git("push", check=False)
    if p.returncode != 0:
        sys.exit("git push failed:\n" + (p.stderr or p.stdout))
    print("Pushed.")


if __name__ == "__main__":
    main()

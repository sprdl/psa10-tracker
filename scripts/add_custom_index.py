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

History backfill (one-off, or after a constituent change):

    python3 scripts/add_custom_index.py --print-backfill-js
        prints an in-page script for https://pokeca-chart.com/gr/chart-index/ . It needs the
        per-card PSA10 histories that scripts/odds_model_builder.js ('grab') leaves in that
        site's localStorage (ci_h:<code>), reads the PSA10 index history from the page's own
        chart data, and returns a compact back series. Run it there.

    python3 scripts/add_custom_index.py --backfill RESULT.json [--no-push]
        replaces all "backfill": true entries with RESULT's series (real daily entries win on
        the same date), commits and pushes.

    Back values use the same formula as the daily level (100 × mean(price ÷ base)) on the days
    all constituents are eligible. Earlier, when fewer cards existed, levels are chain-linked
    backwards (ratio of the mean over the cards eligible on both days). A card becomes
    eligible JOIN_DAYS after its first price, so launch spikes don't drive the level. Card
    prices between chart points are log-interpolated; before Aug 2026 the source history is
    roughly monthly, so back values show the trend, not daily noise.

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
  // the list renders progressively: wait for the page to stop growing, and keep scrolling to the live height
  let prevH = 0;
  for (let i = 0; i < 20; i++) { const h = document.body.scrollHeight; if (h > 5000 && h === prevH) break; prevH = h; await sleep(300); }
  for (let y = 0; y <= document.body.scrollHeight + 1200; y += 600) {
    // dispatching scroll events keeps the virtualised list rendering even when the browser tab is hidden
    window.scrollTo(0, y); window.dispatchEvent(new Event('scroll')); document.dispatchEvent(new Event('scroll')); await sleep(200);
    const t = document.querySelector('main').innerText; let m;
    while ((m = re.exec(t))) seen[m[1].toLowerCase()] = m[2];
  }
  window.scrollTo(0, 0);
  const prices = {}, missing = [];
  for (const c of CODES) { const v = seen[c.toLowerCase()]; const p = v && /\d/.test(v) ? Number(v.replace(/[^\d]/g, '')) : null; if (p) prices[c] = p; else missing.push(c); }
  if (!Object.keys(seen).length) return { error: 'card list not found on page' };
  return { page_cards_seen: Object.keys(seen).length, prices, missing };
})()"""


BACKFILL_JS = r"""await (async () => {
  const META = %s, END = %s, JOIN_DAYS = 90, MIN_CARDS = 5;
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const DAY = 86400000, T = s => Date.parse(String(s).slice(0, 10).replace(/\//g, '-') + 'T00:00:00Z'), D = t => new Date(t).toISOString().slice(0, 10);
  const findIdx = () => {
    for (const c of document.querySelectorAll('canvas')) {
      let el = c;
      for (let d = 0; d < 12 && el; d++, el = el.parentElement) {
        const fk = Object.keys(el).find(k => k.startsWith('__reactFiber')); if (!fk) continue;
        let f = el[fk];
        for (let u = 0; u < 30 && f; u++, f = f.return) { const p = f.memoizedProps; if (p && Array.isArray(p.allData) && p.allData.length && 'value' in p.allData[0]) return p.allData; }
      }
    }
    return null;
  };
  let idxData = null;
  for (let i = 0; i < 25 && !(idxData = findIdx()); i++) await sleep(400);
  if (!idxData) return { error: 'PSA10 index chart data not found — run this on https://pokeca-chart.com/gr/chart-index/' };
  const idx = idxData.map(r => [T(r.date), r.value]).filter(r => r[1] > 0).sort((a, b) => a[0] - b[0]);
  const idxAt = t => { let v = null; for (const [d, x] of idx) { if (d <= t) v = x; else break; } return v; };
  const lsKeys = Object.keys(localStorage).filter(k => k.startsWith('ci_h:'));
  const H = {}, missing = [];
  for (const c of META) {
    const k = lsKeys.find(k => k.slice(5).toLowerCase() === c.code.toLowerCase());
    const rows = k ? JSON.parse(localStorage.getItem(k)).map(([d, p]) => [T(d), p]).filter(r => r[1] > 0).sort((a, b) => a[0] - b[0]) : [];
    if (rows.length < 2) missing.push(c.code); else H[c.code] = rows;
  }
  if (missing.length > META.length * 0.2) return { error: 'card histories missing in localStorage — run odds_model_builder.js list+grab first', missing };
  const price = (code, t) => {                    // log-linear between chart points; none before the first
    const h = H[code]; if (!h || t < h[0][0]) return null;
    for (let i = 1; i < h.length; i++) if (h[i][0] >= t) { const [t0, p0] = h[i - 1], [t1, p1] = h[i]; const w = (t - t0) / (t1 - t0 || 1); return Math.exp(Math.log(p0) + w * (Math.log(p1) - Math.log(p0))); }
    return h[h.length - 1][1];
  };
  const eligible = (code, t) => H[code] && t >= H[code][0][0] + JOIN_DAYS * DAY;
  // grid: month ends until July 2026 (the source is monthly there), then daily from August 2026
  // (August values between the weekly source points are interpolated, so 30-day lookbacks land on the right day)
  const end = T(END.d), grid = [];
  for (let y = 2022, m = 0; ; m++) { if (m === 12) { m = 0; y++; } const t = Date.UTC(y, m + 1, 0); if (t >= T('2026-08-01')) break; grid.push(t); }
  for (let t = T('2026-08-01'); t <= end; t += DAY) grid.push(t);
  if (grid[grid.length - 1] !== end) grid.push(end);
  const series = [];
  let level = END.level;
  for (let k = grid.length - 2; k >= 0; k--) {
    const t0 = grid[k], t1 = grid[k + 1];
    const common = META.filter(c => eligible(c.code, t0) && eligible(c.code, t1));
    if (common.length < MIN_CARDS) break;
    const m = t => common.reduce((s, c) => s + price(c.code, t) / c.base, 0) / common.length;
    level = level * m(t0) / m(t1);
    const e = { d: D(t0), level: Math.round(level * 100) / 100, n: common.length, backfill: true };
    const iv = idxAt(t0); if (iv) e.pokeca_psa10 = Math.round(iv);
    series.unshift(e);
  }
  return { built: D(Date.now()), join_days: JOIN_DAYS, cards_with_history: Object.keys(H).length, missing, index_points: idx.length, series };
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


def backfill(d, path, no_push):
    r = json.loads(path.read_text(encoding="utf-8"))
    if r.get("error"):
        sys.exit(f"ERROR from backfill script: {r['error']} {r.get('missing', '')}")
    back = r.get("series") or []
    if len(back) < 10:
        sys.exit(f"ERROR: only {len(back)} back values — not saving.")
    real = [e for e in d.get("series", []) if not e.get("backfill")]
    real_days = {e["d"] for e in real}
    merged = sorted([e for e in back if e["d"] not in real_days] + real, key=lambda e: e["d"])
    d["series"] = merged
    d["meta"]["backfill"] = {
        "built": r.get("built"), "from": back[0]["d"], "to": back[-1]["d"], "points": len(back),
        "join_days": r.get("join_days"), "missing": r.get("missing") or [],
        "note": "Back values from pokeca-chart per-card PSA10 histories (monthly before Aug 2026, weekly in Aug, daily in Sep; month-end points until Jul 2026, daily after), chain-linked to the first daily reading. See the script docstring.",
    }
    save(d)
    lv = {e["d"]: e["level"] for e in merged}
    print(f"Backfilled {len(back)} points {back[0]['d']} → {back[-1]['d']} (first n={back[0]['n']}, missing: {r.get('missing') or 'none'})")
    for day in ("2024-06-30", "2025-06-30", "2025-12-31", "2026-02-28", "2026-04-30", "2026-08-29", "2026-08-27"):
        if day in lv: print(f"  {day}: {lv[day]:.2f}")
    if no_push:
        return
    git("add", "data/custom_index.json")
    if git("commit", "-m", f"my-tier index: backfill {back[0]['d']} → {back[-1]['d']}", check=False).returncode != 0:
        print("Nothing to commit."); return
    p = git("push", check=False)
    if p.returncode != 0:
        sys.exit("git push failed:\n" + (p.stderr or p.stdout))
    print("Pushed.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("result", nargs="?")
    ap.add_argument("--pokeca", type=float, help="pokeca-chart PSA10 index value today")
    ap.add_argument("--no-push", action="store_true")
    ap.add_argument("--print-js", action="store_true")
    ap.add_argument("--print-backfill-js", action="store_true")
    ap.add_argument("--backfill", metavar="RESULT.json", help="merge a back series from the backfill script")
    args = ap.parse_args()
    d = load()
    meta = d["meta"]
    if args.print_js:
        print(JS % json.dumps([c["code"] for c in meta["constituents"]], ensure_ascii=False))
        return
    if args.print_backfill_js:
        real = [e for e in d.get("series", []) if e.get("prices")]
        if not real:
            sys.exit("ERROR: no daily entry yet to anchor the backfill to.")
        end = {"d": real[0]["d"], "level": real[0]["level"]}
        print(BACKFILL_JS % (json.dumps([{"code": c["code"], "base": c["base"]} for c in meta["constituents"]], ensure_ascii=False),
                             json.dumps(end)))
        return
    if args.backfill:
        return backfill(d, Path(args.backfill), args.no_push)
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
    real = [e for e in series if e.get("prices")]
    prev = real[-1] if real else None
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

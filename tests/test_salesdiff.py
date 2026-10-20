#!/usr/bin/env python3
"""
The SNKRDUNK lines' diff (pricecheck/runner.js POLL ↔ scripts/salesdiff.py), run in Node against real data:
lines rebuilt from the last snapshots (and the last real full/quick inputs) go through the page's POLL and back
through salesdiff.process(), run after run with both bases kept, and must come back byte for byte. Also: a base
that doesn't match (page or Python side), a retry run ('+'), and the full POLL fallback.

    python3 tests/test_salesdiff.py        (needs node)
"""
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pricecheck"))
sys.path.insert(0, str(ROOT / "scripts"))
import jsrun  # noqa: E402
import salesdiff  # noqa: E402

HARNESS = r"""
const vm = require('vm');
const inp = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const store = new Map(Object.entries(inp.store));
const page = { text: null };
const ctx = vm.createContext({
  localStorage: { getItem: k => store.has(k) ? store.get(k) : null, setItem: (k, v) => store.set(k, String(v)) },
  location: { host: 'test.example' }, crypto: globalThis.crypto, TextEncoder, setTimeout,
  document: { createElement: () => ({}), body: { replaceChildren: (el) => { page.text = el.textContent; } } }, __wsleep: () => Promise.resolve(),
});
(async () => {
  const runner = vm.runInContext(inp.runner, ctx);
  await runner('none', 'x', [], 'y', null, null, '');       // defines __pcpoll (and answers NEED_SCRIPT)
  vm.runInContext(`globalThis.__pcB = {__pq: ${JSON.stringify(inp.B)}}; globalThis.__pq = ${JSON.stringify({ done: true, i: inp.lines.length, n: inp.lines.length, lines: inp.lines })}`, ctx);
  // a long result becomes the page (PAGE …), read with get_page_text: take what the page holds
  const read = async (code) => { const r = await vm.runInContext(code, ctx); return r.startsWith('PAGE ') ? page.text : r; };
  const out = await read("globalThis.__pcpoll('__pq')");
  const full = await read("globalThis.__pcpoll('__pq', 1)");
  process.stdout.write(JSON.stringify({ out, full, store: Object.fromEntries(store) }));
})().catch(e => { console.error(e); process.exit(1); });
"""
U = {"秒": "s", "分": "m", "時間": "h", "日": "d", "週間": "w", "ヶ月": "M", "か月": "K"}


def enc(w):
    w = str(w or "").strip()
    if w == "たった今":
        return "n"
    m = re.match(r"^(\d+)(秒|分|時間|日|週間|ヶ月|か月)前$", w)
    if m:
        return m[1] + U[m[2]]
    m = re.match(r"^20(\d\d)/(\d\d)/(\d\d)$", w)
    return m[1] + m[2] + m[3] if m else "~x"


def lines_from(snap):
    out = []
    for c in snap["cards"]:
        sid = c["url"].rstrip("/").split("/")[-1]
        g = c.get("grades") or {}
        p, a = g.get("psa10") or {}, g.get("raw_a_grade") or {}
        t = [sid, f"f{c.get('favorite_count') or '?'}", f"p{p.get('lowest_price') or '-'}", f"a{a.get('lowest_price') or '-'}"]
        for k, gr in (("P", p), ("A", a)):
            s = gr.get("recent_completed_sales") or []
            t.append(f"{k}=" + ",".join(f"{r['price']}@{enc(r['when'])}" for r in s) if s else f"{k}0")
        if snap.get("check_mode", "full") == "full":
            for k, gr in (("L", p), ("R", a)):
                if gr.get("top20_cheapest_listings") and not gr.get("listings_as_of"):
                    t.append(f"{k}=" + ",".join(map(str, gr["top20_cheapest_listings"])))
        out.append(" ".join(t))
    return out


def page(store, lines, B):
    r = subprocess.run(["node", "-e", HARNESS], text=True, capture_output=True,
                       input=json.dumps({"store": store, "lines": lines, "B": B, "runner": jsrun.runner_text()}))
    if r.returncode:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


def roundtrip(root, store, lines, B=None, expect_mode=None):
    B = salesdiff.base_hash(root) if B is None else B
    res = page(store, lines, B)
    text, base, seen, notes = salesdiff.process(res["out"] + "\n", root)
    assert seen and not notes, notes
    assert text.rstrip("\n").split("\n") == lines, "rebuilt lines differ"
    assert base is not None, "base didn't add up"
    salesdiff.save(root, base, seen)
    mode = res["out"].rsplit("\n", 1)[1].split()[1]
    if expect_mode:
        assert mode == expect_mode or (expect_mode == "hash" and len(mode) == 16), (mode, expect_mode)
    return res, len(res["out"]), len("\n".join(lines))


def main():
    m = json.loads((ROOT / "data" / "manifest.json").read_text(encoding="utf-8"))["snapshots"][-14:]
    runs = [lines_from(json.loads((ROOT / "data" / "snapshots" / s["file"]).read_text(encoding="utf-8"))) for s in m]
    for f in ("full-raw.txt", "quick-raw.txt"):
        p = ROOT / "data" / "incoming" / f
        if p.exists():
            runs.append([ln for ln in p.read_text(encoding="utf-8").splitlines() if re.match(r"\d+ ", ln)])
    runs[3] = runs[3][:5] + [runs[3][5].split(" ")[0] + " E" + "page%20did%20not%20load"] + runs[3][6:]   # an E line
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        store, sent, whole = {}, 0, 0
        for i, lines in enumerate(runs):
            res, a, b = roundtrip(root, store, lines, expect_mode="hash")   # run 0: both bases empty, so they match
            store = res["store"]
            if i:
                sent, whole = sent + a, whole + b
        print(f"ok  {len(runs)} runs round-trip; diffed lines are {sent / whole:.0%} of the whole lines ({sent:,} vs {whole:,} characters)")

        # retry run: whole lines, base updated on both sides, next run still diffs
        res, *_ = roundtrip(root, store, runs[-1][:2], B="+", expect_mode="+")
        store = res["store"]
        res, *_ = roundtrip(root, store, runs[-1], expect_mode="hash")
        store = res["store"]
        print("ok  retry run (+)")

        # the Python base lost: the page doesn't match, sends whole lines and both start over
        (root / salesdiff.BASE_FILE).unlink()
        res, *_ = roundtrip(root, store, runs[-2], expect_mode="-")
        store = res["store"]
        res, *_ = roundtrip(root, store, runs[-1], expect_mode="hash")
        store = res["store"]
        print("ok  base mismatch → whole lines, then diffs again")

        # the page diffed against a base Python no longer has: refused; the full POLL publishes, base dropped
        good = salesdiff.base_hash(root)
        res = page(store, runs[-2], good)
        bp = root / salesdiff.BASE_FILE
        b = json.loads(bp.read_text(encoding="utf-8"))
        b[next(iter(b))] += " x"
        bp.write_text(json.dumps(b), encoding="utf-8")
        try:
            salesdiff.process(res["out"], root)
            raise AssertionError("a diff against another base was accepted")
        except salesdiff.DiffError:
            pass
        text, base, seen, _ = salesdiff.process(res["full"], root)
        assert text.split("\n") == runs[-2] and seen and base is None
        salesdiff.save(root, base, seen)
        assert not bp.exists()
        store = res["store"]
        res, *_ = roundtrip(root, store, runs[-1], expect_mode="-")
        print("ok  refused diff → full POLL publishes, base starts over")

        # a damaged diffed line is refused, never published
        res = page(res["store"], runs[-2], salesdiff.base_hash(root))
        bad = res["out"].replace("^", "^1", 1)
        try:
            salesdiff.process(bad, root)
            raise AssertionError("a damaged diff was accepted")
        except salesdiff.DiffError:
            pass
        print("ok  damaged diff refused")
    print("all salesdiff checks passed")


if __name__ == "__main__":
    main()

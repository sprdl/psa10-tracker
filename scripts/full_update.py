#!/usr/bin/env python3
"""
Publish a FULL price check from the compact lines the in-page scripts return.

    python3 scripts/full_update.py - <<'EOF'            # lines on stdin (what the skill does)
    <snkrdunk_full.js lines>
    <altema_batch.js lines>          (ALT …)
    <pokeca_both.js lines>           (IDX psa10 {…} / IDX raw {…})
    MYTIER {…}                       My-tier extractor result (optional)
    PREM …                           pokeca_premium.js lines (optional; saved to data/premium.json)
    SCP … / SC {…} / SC! …           pokeca_scout.js lines (optional; saved to data/scout.json)
    TIER {…}                         psa_tier_status (Mondays, optional)
    VOL psa10 {"volume_trend": …, "volume_note": …}   volume override (optional)
    NOTE free text                   run notes (optional)
    EOF
    python3 scripts/full_update.py FILE [--dry-run] [--no-push] [--skip scout,premium,...]

Completeness guard: the run is refused when a planned step left no lines (market index, My-tier
index, altema pages due today, slab premiums, Scout), because a skipped step otherwise goes
unnoticed for days (Scout was skipped on 10/1 and 10/2 without a trace). Run the missing step and
re-run with all lines. Only if a step genuinely failed (site down, page structure changed), pass
--skip with its name and say so in the chat message.

What it does:
  1. decodes the lines into exactly the raw JSON pricecheck/scripts/assemble.py has always taken
     (base + listings + altema per card, the two indices), applying the plan's rules
     (pricecheck/plan.py) for tile-only cards and skipped/conditional altema checks;
  2. runs assemble.py with --prev = the live snapshot, printing its WARNINGS / CHANGES;
  3. (not --dry-run) pulls, publishes with scripts/add_snapshot.py, saves the My-tier index with
     scripts/add_custom_index.py, the slab premium with scripts/premium.py, and stores any newly
     found card photo URL.
Everything it writes goes to data/incoming/ (gitignored) except what the publishing scripts commit.
"""
import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "pricecheck"))
import quick_update  # noqa: E402  (decode_compact: the product-page part of each line)
import premium  # noqa: E402
import scout  # noqa: E402
import plan as planmod  # noqa: E402

TILE_ERR = {"-": "no for-sale listings (出品待ち on the grade tile)", "?": "no price on the grade tile",
            "x": "grade tile not found", "!": "grade tiles not found"}


def die(msg):
    print(f"\nERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def js_round(x):
    return int(x + 0.5)  # JS Math.round for positive numbers (Python's round() is banker's rounding)


def decode_listing(tok):
    """L=… / Lsg2f=… / L!err  → the snkrdunk_listings.js result shape assemble.py reads."""
    body = tok[1:]
    if body.startswith("!"):
        return {"error": unquote(body[1:])}
    m = re.fullmatch(r"([sfg\d]*)=([\d,]*)", body)
    if not m:
        raise ValueError(f"bad listings token {tok!r}")
    flags, prices = m[1], [int(p) for p in m[2].split(",") if p]
    if not prices:
        return {"error": "no for-sale listings found for this grade"}
    low = prices[0]
    thr = js_round(low * 1.15)
    within = [p for p in prices if p <= thr]
    out = {"lowest_price": low, "threshold_115pct_of_lowest": thr, "top20_cheapest_listings": prices,
           "listings_within_15pct_of_lowest": within, "count_within_15pct": len(within),
           "count_excluded_over_15pct": len(prices) - len(within)}
    if "s" in flags:
        out["sort_note"] = "on-page order/sold filter not confirmed; sorted and filtered in script"
    warn = []
    g = re.search(r"g(\d+)", flags)
    if g:
        warn.append(f"{g[1]} tile(s) show a grade different from the filter label")
    if "f" in flags:
        warn.append("the listings page's filter label didn't match the grade")
    if warn:
        out["grade_warning"] = "; ".join(warn)
    return out


def tile_listing(tile_tok, grade):
    """Tile-only card (no listings read): PSA10 → error; A → lowest ask from the tile."""
    code = (tile_tok or "?x")[1:]
    if grade == "PSA10":
        return {"error": TILE_ERR.get(code, "no for-sale listings (出品待ち on the grade tile)")}
    if code.isdigit():
        v = int(code)
        return {"lowest_price": v, "threshold_115pct_of_lowest": js_round(v * 1.15)}
    return {"error": TILE_ERR.get(code, "grade tile not read")}


def psa_activity(toks):
    by = {t[0]: t for t in toks}
    return (by.get("p", "p?")[1:].isdigit()) or bool(re.match(r"P(~\d+)?=\d", by.get("P", "")))


def parse(text, cards_meta, plan):
    raw = {"cards": {}, "index": {}}
    mytier = None
    prem_lines = []
    scout_lines = []
    alt_lines = {}
    card_lines = {}
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        head, _, rest = s.partition(" ")
        if head.isdigit():
            card_lines[head] = s
        elif head == "ALT":
            sid, _, r = rest.partition(" ")
            alt_lines[sid] = r
        elif head == "IDX":
            k, _, js = rest.partition(" ")
            raw["index"]["psa10" if k == "psa10" else "raw"] = json.loads(js)
        elif head in ("SCP", "SC", "SC!"):
            scout_lines.append(s)
        elif head == "PREM":
            prem_lines.append(s)
        elif head == "MYTIER":
            mytier = json.loads(rest)
        elif head == "TIER":
            raw["psa_tier_status"] = json.loads(rest)
        elif head == "VOL":
            k, _, js = rest.partition(" ")
            raw.setdefault("volume_overrides", {})["psa10" if k == "psa10" else "raw"] = json.loads(js)
        elif head == "NOTE":
            raw["run_notes"] = (raw.get("run_notes", "") + " " + rest).strip()
        else:
            print(f"  (ignored line: {s[:60]})")
    decoded = quick_update.decode_compact("\n".join(card_lines.values()))["cards"]
    altema_plan = {a[0]: a[2] for a in plan["altema"]}
    notes = []
    for sid, line in card_lines.items():
        toks = line.split()[1:]
        by = {t[0]: t for t in toks}
        base = decoded[sid]["base"]
        tiles = decoded[sid]["tiles"]
        # the tile values stay inside base for the tile-only rule below; assemble.py doesn't read them
        rc = {"base": base}
        if "L" in by or "R" in by:
            rc["psa10"] = decode_listing(by["L"]) if "L" in by else {"error": "listings not collected this run"}
            rc["a"] = decode_listing(by["R"]) if "R" in by else {"error": "listings not collected this run"}
        elif not base.get("error"):
            rc["psa10"] = tile_listing(by.get("p"), "PSA10")
            rc["a"] = tile_listing(by.get("a"), "A")
        if "I" in by:
            rc["image_url"] = unquote(by["I"][1:])
        # altema
        st = altema_plan.get(sid)
        if st is None:
            rc["altema"] = {"skipped": plan["altema_skipped"].get(sid, "not planned")}
        elif st == "ifpsa" and not psa_activity(toks):
            rc["altema"] = {"skipped": "weekly check until graded"}
        elif sid not in alt_lines:
            rc["altema"] = {"error": "altema not read this run"}
        else:
            a = {}
            for t in alt_lines[sid].split():
                if t[0] == "n":
                    a["psa10_population"] = int(t[1:]) if t[1:].isdigit() else None
                elif t[0] == "r":
                    a["psa10_gem_rate_pct"] = float(t[1:]) if t[1:] not in ("-", "") else None
                elif t[0] == "c":
                    a["card_number"] = unquote(t[1:])
                elif t[0] == "!":
                    a["error"] = unquote(t[1:])
            name = (cards_meta.get(sid) or {}).get("card_name_ja", "")
            num = re.search(r"\d+/\d+", a.get("card_number") or "")
            if a.get("card_number") and num and num[0] not in name:
                notes.append(f"{sid}: altema 型番 {a['card_number']} doesn't match the card name — check its altema_url")
            if isinstance(a.get("psa10_gem_rate_pct"), float) and a["psa10_gem_rate_pct"].is_integer():
                a["psa10_gem_rate_pct"] = int(a["psa10_gem_rate_pct"])
            rc["altema"] = a
        raw["cards"][sid] = rc
    for sid in cards_meta:
        if sid not in raw["cards"]:
            notes.append(f"{sid}: no SNKRDUNK line in this run")
    raw["_premium"] = premium.decode(prem_lines)
    raw["_scout"] = scout.decode(scout_lines) if scout_lines else None
    return raw, mytier, notes


STEP_NAMES = {
    "index": "market indices (step 4.1, IDX lines)",
    "mytier": "My-tier index (step 4.2, MYTIER line)",
    "altema": "altema pages due today (step 3, ALT lines)",
    "premium": "slab premiums (step 4.3, PREM lines)",
    "scout": "Scout (step 4.4, SCP/SC lines)",
}


def missing_steps(text, plan):
    heads = {ln.strip().partition(" ")[0] for ln in text.splitlines() if ln.strip()}
    miss = []
    if "IDX" not in heads:
        miss.append("index")
    if "MYTIER" not in heads:
        miss.append("mytier")
    if any(a[2] == "due" for a in plan.get("altema", [])) and "ALT" not in heads:
        miss.append("altema")
    if plan.get("premium") and "PREM" not in heads:
        miss.append("premium")
    if plan.get("scout") and not ({"SCP", "SC", "SC!"} & heads):
        miss.append("scout")
    return miss


def run(cmd):
    r = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)
    print((r.stdout or "") + (r.stderr or ""), end="")
    return r.returncode


def persist_images(raw, cards_meta, dry):
    for sid, rc in raw["cards"].items():
        img = rc.get("image_url")
        meta = cards_meta.get(sid)
        if not img or not meta or meta.get("image_url"):
            continue
        print(f"photo found for {sid}: saving it to the card list")
        if dry:
            continue
        if meta["_source"] == "tracked":
            run([sys.executable, "scripts/card_requests.py", "set", sid, f"image_url={img}"])
        else:
            p = ROOT / "pricecheck" / "references" / "cards.json"
            d = json.loads(p.read_text(encoding="utf-8"))
            for c in d["cards"]:
                if c["snkrdunk_id"] == sid:
                    c["image_url"] = img
            p.write_text(json.dumps(d, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
            run(["git", "add", str(p)])
            run(["git", "commit", "-q", "-m", f"pricecheck: photo URL for {sid}"])
            run(["git", "push", "-q"])


def main():
    args = sys.argv[1:]
    files = [a for i, a in enumerate(args) if not a.startswith("--") and not (i and args[i - 1] == "--skip")]
    dry = "--dry-run" in args
    text = sys.stdin.read() if not files or files[0] == "-" else Path(files[0]).read_text(encoding="utf-8")
    incoming = ROOT / "data" / "incoming"
    incoming.mkdir(parents=True, exist_ok=True)
    (incoming / "full-raw.txt").write_text(text, encoding="utf-8")

    if not dry:
        pull = subprocess.run(["git", "pull", "--ff-only", "--quiet"], cwd=ROOT, text=True, capture_output=True)
        if pull.returncode != 0:
            die("`git pull --ff-only` failed — sort out the local repo first:\n" + (pull.stderr or pull.stdout))

    plan = planmod.build_plan(ROOT)
    skip = set()
    for i, a in enumerate(args):
        if a == "--skip" and i + 1 < len(args):
            skip |= {x.strip() for x in args[i + 1].split(",") if x.strip()}
        elif a.startswith("--skip="):
            skip |= {x.strip() for x in a[7:].split(",") if x.strip()}
    miss = [m for m in missing_steps(text, plan) if m not in skip]
    if miss:
        die("planned steps left no lines in this run:\n" + "\n".join(f"  - {STEP_NAMES[m]}" for m in miss)
            + "\nRun them and re-run full_update.py with all lines. If a step genuinely failed, re-run with "
            + f"--skip {','.join(miss)} and say why in the chat message.")
    skipped_note = [f"step skipped on purpose this run: {STEP_NAMES[m]}" for m in sorted(skip) if m in STEP_NAMES]
    cards_meta = {c["snkrdunk_id"]: c for c in planmod.load_cards(ROOT)}
    raw, mytier, notes = parse(text, cards_meta, plan)
    notes = skipped_note + notes
    for sid, name in plan.get("altema_missing", []):
        notes.append(f"{sid}: no altema page on file ({name[:24]}) — find it (FULL-CHECK step 1c)")
    prem = raw.pop("_premium", {})
    sc = raw.pop("_scout", None)
    if not raw["cards"]:
        die("no SNKRDUNK card lines in the input")
    raw_path = incoming / "full-raw.json"
    raw_path.write_text(json.dumps(raw, ensure_ascii=False, indent=1), encoding="utf-8")
    snap_path, _ = planmod.latest_snapshot(ROOT)
    out_path = incoming / "latest-run.json"
    cmd = [sys.executable, "pricecheck/scripts/assemble.py", str(raw_path), "--out", str(out_path)]
    if snap_path:
        cmd += ["--prev", str(snap_path)]
    if run(cmd) != 0:
        die("assemble.py failed")
    if notes:
        print("\nFULL_UPDATE NOTES:")
        for n in notes:
            print(" -", n)
    if dry:
        print(f"\nDry run: assembled {out_path.relative_to(ROOT)}, nothing published.")
        return

    print()
    passthrough = [a for a in args if a == "--no-push"]
    if run([sys.executable, "scripts/add_snapshot.py", str(out_path), *passthrough]) != 0:
        die("add_snapshot.py failed (see above)")
    if mytier:
        ci = incoming / "custom-index.json"
        ci.write_text(json.dumps(mytier, ensure_ascii=False), encoding="utf-8")
        pv = (raw["index"].get("psa10") or {}).get("latest_index_value_jpy")
        print()
        run([sys.executable, "scripts/add_custom_index.py", str(ci), *(["--pokeca", str(int(pv))] if pv else []), *passthrough])
    if prem:
        print()
        premium.save(prem, ROOT, push="--no-push" not in args)
    if sc:
        print()
        scout.update(*sc, root=ROOT, push="--no-push" not in args)
    persist_images(raw, cards_meta, dry)


if __name__ == "__main__":
    main()

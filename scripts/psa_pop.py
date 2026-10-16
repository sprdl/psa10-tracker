#!/usr/bin/env python3
"""
PSA's own population report (psacard.com/pop): the only PSA10 population and gem rate source (since 2026-10-12;
altema, the earlier source, was dropped the same day).

The full check reads it every run with pricecheck/scripts/psa_pop.js (step 3a) and full_update.py decodes the POP
lines. This script is for everything outside a full check:

    python3 scripts/psa_pop.py decode - <<'EOF'       # show what POP lines mean (no writes)
    POP 455596 n82856 t95372 c217%20Umbreon%20EX vSpecial%20Art%20Rare
    EOF
    python3 scripts/psa_pop.py apply - [--no-push] <<'EOF'   # write them into the LATEST snapshot now
    POP …
    EOF
    python3 scripts/psa_pop.py missing                  # cards with regular PSA10 sales but no psa_pop_url

Gem rate = PSA 10 count ÷ total graded on PSA's row for the card (the usual 取得率 definition).
Card config (data/tracked_cards.json or pricecheck/references/cards.json, set with `card_requests.py set`):
    psa_pop_url   the SET page, e.g. /pop/tcg-cards/2024/pokemon-japanese-sv8a-terastal-fest-ex/288603
    psa_pop_no    the card number as PSA writes it ("217", "090")
    psa_pop_name  optional English name fragment to pick the row when a number repeats ("Umbreon")
Finding a set page: psacard.com/pop/tcg-cards/156940 lists the years; a year page lists its sets (the "Show"
menu up to 250 a page, sets named "Pokemon Japanese <code>-<English set name>"). Signed-in browser only.
"""
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parent.parent
JST = timezone(timedelta(hours=9))


def decode(lines):
    """{sid: {psa10_population, psa_total_graded, psa10_gem_rate_pct, card_number, variety} | {error}}"""
    out = {}
    for ln in lines:
        p = ln.strip().split(" ")
        if len(p) < 3 or p[0] != "POP":
            continue
        sid, a = p[1], {}
        for t in p[2:]:
            if t[0] == "n" and t[1:].isdigit():
                a["psa10_population"] = int(t[1:])
            elif t[0] == "t" and t[1:].isdigit():
                a["psa_total_graded"] = int(t[1:])
            elif t[0] == "c":
                a["card_number"] = unquote(t[1:])
            elif t[0] == "v" and t[1:] != "-":
                a["variety"] = unquote(t[1:])
            elif t[0] == "!":
                a["error"] = unquote(t[1:])
        if a.get("psa10_population") is not None and a.get("psa_total_graded"):
            a["psa10_gem_rate_pct"] = round(a["psa10_population"] / a["psa_total_graded"] * 100, 1)
        out[sid] = a
    return out


def latest_snapshot(root=ROOT):
    m = json.loads((root / "data" / "manifest.json").read_text(encoding="utf-8"))
    f = sorted(m["snapshots"], key=lambda s: s["collected_at_jst"])[-1]["file"]
    return root / "data" / "snapshots" / f


def missing(root=ROOT):
    sys.path.insert(0, str(root / "pricecheck"))
    import plan
    return plan.build_plan(root)["psapop_missing"]


def apply(found, root=ROOT, push=True):
    run = lambda *a, check=False: subprocess.run(["git", *a], cwd=root, text=True, capture_output=True, check=check)
    if push:
        run("pull", "--ff-only", "-q")
    path = latest_snapshot(root)
    snap = json.loads(path.read_text(encoding="utf-8"))
    now = datetime.now(JST).replace(microsecond=0).isoformat()
    done = []
    for c in snap.get("cards", []):
        sid = c.get("url", "").rstrip("/").split("/")[-1]
        a = found.get(sid)
        if not a or a.get("psa10_population") is None:
            if a and a.get("error"):
                print(f"{sid}: not applied: {a['error']}")
            continue
        old = (c.get("psa10_population"), c.get("psa10_gem_rate_pct"))
        c.update(psa10_population=a["psa10_population"], psa10_gem_rate_pct=a.get("psa10_gem_rate_pct"),
                 psa_total_graded=a.get("psa_total_graded"), population_source="psa", population_as_of=now)
        c.pop("population_error", None); c.pop("population_note", None)
        done.append(f"{sid}: {old[0]} / {old[1]}% → {a['psa10_population']:,} / {a.get('psa10_gem_rate_pct')}% (PSA)")
    print("\n".join(done) or "nothing to apply")
    if not done:
        return
    path.write_text(json.dumps(snap, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")   # compact, like add_snapshot.py
    if not push:
        return
    run("add", str(path.relative_to(root)))
    if run("commit", "-m", f"population: PSA pop report for {len(done)} card(s)").returncode != 0:
        print("Nothing to commit."); return
    p = run("push", "-q")
    print("Pushed." if p.returncode == 0 else "git push failed:\n" + (p.stderr or p.stdout))


def main():
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    if not a:
        sys.exit(__doc__)
    if a[0] == "missing":
        for sid, name in missing():
            print(sid, name)
        return
    src = a[1] if len(a) > 1 else "-"
    text = sys.stdin.read() if src == "-" else Path(src).read_text(encoding="utf-8")
    found = decode(text.splitlines())
    if a[0] == "decode":
        print(json.dumps(found, ensure_ascii=False, indent=1))
    elif a[0] == "apply":
        apply(found, push="--no-push" not in sys.argv)
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()

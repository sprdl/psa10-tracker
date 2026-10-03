#!/usr/bin/env python3
"""
Save the slab premium (PSA10 ÷ raw) per card from pokeca-chart to data/premium.json.

    python3 scripts/premium.py - [--no-push] <<'EOF'      # PREM lines from pricecheck/scripts/pokeca_premium.js
    PREM 455596 d260926 r42606 p67157 m1.746 n41 s250404:1.54,...
    EOF

scripts/full_update.py calls save() with the PREM lines of a full check, so this is only needed on
its own to redo that step.

Why pokeca-chart and not SNKRDUNK: the test on 2026-09-28 (project doc raw-vs-psa10-leadlag) found that
a card's premium relative to its OWN 6-month norm predicts how its PSA10 does against the market over
the next 30 days (stretched → lags, compressed → leads; small effect). That needs months of history,
which only pokeca-chart has (美品 raw, a cross-market average, so its level differs from SNKRDUNK's
A-rank). The site shows SNKRDUNK's own ask/sales premium next to it from the snapshots.

data/premium.json: {"updated": ..., "about": ..., "cards": {url: {
    "asof": "2026-09-26", "raw": 42606, "psa": 67157, "prem": 1.576, "norm": 1.746, "dev": -9.7,
    "n": 41, "series": [["2025-04-04", 1.54], ...]} or {"error": "..."}}}
"dev" is the percent difference of the latest premium from the norm; the site flags |dev| >= 20.
"""
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import unquote

JST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parent.parent
PATH = ROOT / "data" / "premium.json"


def _date(y):
    return f"20{y[:2]}-{y[2:4]}-{y[4:6]}"


def decode(lines):
    """PREM lines -> {snkrdunk id: entry}."""
    out = {}
    for line in lines:
        parts = line.strip().split()
        if len(parts) < 3 or parts[0] != "PREM":
            continue
        sid = parts[1]
        if parts[2].startswith("!"):
            out[sid] = {"error": unquote(parts[2][1:])}
            continue
        tok = {p[0]: p[1:] for p in parts[2:]}
        raw, psa = int(tok["r"]), int(tok["p"])
        norm = None if tok.get("m", "-") == "-" else float(tok["m"])
        prem = psa / raw
        series = []
        for pair in (tok.get("s") or "").split(","):
            if ":" in pair:
                d, k = pair.split(":")
                series.append([_date(d), float(k)])
        out[sid] = {"asof": _date(tok["d"]), "raw": raw, "psa": psa, "prem": round(prem, 3),
                    "norm": norm, "dev": round((prem / norm - 1) * 100, 1) if norm else None,
                    "n": int(tok.get("n", "0")), "series": series, "_g": tok.get("g")}
    return out


def save(entries, root=ROOT, push=True):
    if not entries:
        return
    path = root / "data" / "premium.json"
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    data["about"] = ("Slab premium (PSA10 ÷ raw 美品) per card from pokeca-chart, written by full checks "
                     "(pricecheck/scripts/pokeca_premium.js → scripts/premium.py). norm = median of the points "
                     "30–210 days before the latest; dev = % from the norm.")
    cards = data.setdefault("cards", {})
    hype_g = {sid: e.pop("_g", None) for sid, e in entries.items()}
    for sid, e in entries.items():
        url = f"https://snkrdunk.com/apparels/{sid}"
        if "error" in e and "series" in cards.get(url, {}):
            cards[url]["error"] = e["error"]      # keep the last good reading, note the failure
        else:
            cards[url] = e
    data["updated"] = datetime.now(JST).replace(microsecond=0).isoformat()
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    flagged = [(sid, e["dev"]) for sid, e in entries.items() if e.get("dev") is not None and abs(e["dev"]) >= 20]
    print(f"premium: {sum(1 for e in entries.values() if 'error' not in e)} card(s) saved"
          + (f", {len(entries) - sum(1 for e in entries.values() if 'error' not in e)} not on pokeca-chart" if any('error' in e for e in entries.values()) else "")
          + (" · far from norm: " + ", ".join(f"{s} {d:+.0f}%" for s, d in flagged) if flagged else ""))
    try:  # hype exposure rides on the same card pages (g token); written before the commit below
        import hype
        hype.save({sid: hype.parse_g(g) for sid, g in hype_g.items() if g}, root, push=False)
    except Exception as ex:  # never break the premium step over this
        print(f"hype: skipped ({ex})")
    if not push:
        return
    for cmd in (["git", "add", str(path), str(root / "data" / "hype.json")], ["git", "commit", "-q", "-m", "premium: pokeca-chart slab premium + hype exposure"], ["git", "push", "-q"]):
        r = subprocess.run(cmd, cwd=root, text=True, capture_output=True)
        if r.returncode != 0 and "nothing to commit" not in (r.stdout + r.stderr):
            print(f"premium: {' '.join(cmd)} failed: {(r.stderr or r.stdout).strip()}")
            return
    print("premium: pushed.")


if __name__ == "__main__":
    args = sys.argv[1:]
    files = [a for a in args if not a.startswith("--")]
    text = sys.stdin.read() if not files or files[0] == "-" else Path(files[0]).read_text(encoding="utf-8")
    if "--no-push" not in args:
        subprocess.run(["git", "pull", "--ff-only", "--quiet"], cwd=ROOT)
    save(decode(text.splitlines()), push="--no-push" not in args)

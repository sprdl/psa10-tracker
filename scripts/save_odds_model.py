#!/usr/bin/env python3
"""
Save a freshly built odds model (the JSON returned by scripts/odds_model_builder.js 'build')
as data/odds_model.json, keeping the "about" block, then commit and push.

    python3 scripts/save_odds_model.py built.json [--no-push]
"""
import json, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
new = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
for k in ("pool_sigma", "z_end30", "z_touch90", "cards"):
    if k not in new:
        sys.exit(f"missing {k} — not a model build")
if len(new["cards"]) < 60 or min(new["n"]) < 1000:
    sys.exit(f"too little data ({len(new['cards'])} cards, n={new['n']}) — not saving")
path = ROOT / "data" / "odds_model.json"
old = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
out = {"about": old.get("about", {}), **new}
path.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
print(f"Saved odds model built {new['built']}: {len(new['cards'])} cards, pool sigma {new['pool_sigma']}")
if "--no-push" not in sys.argv:
    subprocess.run(["git", "add", "data/odds_model.json"], cwd=ROOT, check=True)
    if subprocess.run(["git", "commit", "-q", "-m", f"odds model: rebuild {new['built']}"], cwd=ROOT).returncode == 0:
        subprocess.run(["git", "push", "-q"], cwd=ROOT, check=True)
        print("Pushed.")

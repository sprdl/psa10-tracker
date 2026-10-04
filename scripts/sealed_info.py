#!/usr/bin/env python3
"""
Name and picture of sealed products (data/holdings.json "sealed") from their SNKRDUNK pages.

    python3 scripts/sealed_info.py --due            # products with a SNKRDUNK link but no name/picture yet
    python3 scripts/sealed_info.py --js             # pricecheck/scripts/snkrdunk_sealed.js with them filled in
    python3 scripts/sealed_info.py - [--no-push] <<'EOF'
    SP s51 %E3%83%9D%E3%82%B1... https%3A%2F%2Fcdn.snkrdunk.com%2Fupload_bg_removed%2F....webp%3Fsize%3Dl
    EOF

A sealed product is logged from the site with its SNKRDUNK link (like a single), but the GitHub Action
that records it never opens SNKRDUNK (no automated access). So the price check reads each new
product's page once, in the user's browser, and this script saves what it found: the product name
(`snkrdunk_name`, also used as the name when none was typed) and the picture URL on SNKRDUNK's CDN
(`image`), the same way singles carry their image_url. Full and quick checks both print a
SEALED INFO block when something is due (FULL-CHECK step 8h).
"""
import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parent.parent
PATH = ROOT / "data" / "holdings.json"


def load():
    return json.loads(PATH.read_text(encoding="utf-8")) if PATH.exists() else {"holdings": []}


def due(root=ROOT):
    data = json.loads((root / "data" / "holdings.json").read_text(encoding="utf-8")) if (root / "data" / "holdings.json").exists() else {}
    return [(s["id"], s["url"]) for s in data.get("sealed", []) if s.get("url") and not (s.get("image") and s.get("snkrdunk_name"))]


def print_due(root=ROOT):
    try:
        d = due(root)
    except Exception as e:  # never break a price check over this
        print(f"\nSEALED INFO: skipped ({e}).")
        return
    if not d:
        return
    print("\nSEALED INFO NOW (FULL-CHECK step 8h; full AND quick checks) — read these sealed products' SNKRDUNK pages once:")
    for sid, url in d:
        print(f"  {sid}  {url}")
    print("  `python3 scripts/sealed_info.py --js` → paste on a snkrdunk.com tab → poll → `python3 scripts/sealed_info.py -` with the SP lines.")


def decode(lines):
    out = {}
    for ln in lines:
        p = ln.strip().split(" ")
        if len(p) >= 4 and p[0] == "SP":
            out[p[1]] = {"snkrdunk_name": unquote(p[2])[:160], "image": None if p[3] == "-" else unquote(p[3])}
        elif len(p) >= 3 and p[0] == "SE":
            out[p[1]] = {"error": unquote(" ".join(p[2:]))}
    return out


def save(found, push=True):
    if push:
        subprocess.run(["git", "pull", "--ff-only", "--quiet"], cwd=ROOT)
    data = load()
    done = []
    for s in data.get("sealed", []):
        e = found.get(s.get("id"))
        if not e:
            continue
        if e.get("error"):
            print(f"  {s['id']}: {e['error']}")
            continue
        s["snkrdunk_name"] = e["snkrdunk_name"]
        if e.get("image") and re.match(r"https://cdn\.snkrdunk\.com/", e["image"]):
            s["image"] = e["image"]
        done.append(f"{s['id']} {e['snkrdunk_name']}" + ("" if s.get("image") else " (no picture found)"))
    if not done:
        print("sealed: nothing to save.")
        return
    PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("sealed: " + "; ".join(done))
    if not push:
        return
    for cmd in (["git", "add", str(PATH)], ["git", "commit", "-q", "-m", "holdings: SNKRDUNK name and picture for sealed products"], ["git", "push", "-q"]):
        r = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)
        if r.returncode != 0 and "nothing to commit" not in (r.stdout + r.stderr):
            print(f"sealed: {' '.join(cmd)} failed: {(r.stderr or r.stdout).strip()}")
            return
    print("sealed: pushed.")


def main():
    args = sys.argv[1:]
    if "--due" in args:
        d = due()
        print("\n".join(f"{sid}  {url}" for sid, url in d) if d else "none due")
        return
    if "--js" in args:
        d = due()
        if not d:
            print("none due")
            return
        js = (ROOT / "pricecheck" / "scripts" / "snkrdunk_sealed.js").read_text(encoding="utf-8")
        line = re.search(r"  const SEALED = \[.*?\];\n", js).group(0)
        print(js[js.index("(() => {"):].replace(line, "  const SEALED = " + json.dumps([list(x) for x in d]) + ";\n"))
        return
    files = [a for a in args if not a.startswith("--")]
    text = sys.stdin.read() if not files or files[0] == "-" else Path(files[0]).read_text(encoding="utf-8")
    save(decode(text.splitlines()), push="--no-push" not in args)


if __name__ == "__main__":
    main()

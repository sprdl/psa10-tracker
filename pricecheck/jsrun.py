#!/usr/bin/env python3
"""
Ready-to-paste browser calls for the price check's in-page scripts, with a hash-checked cache.

Why: pasting every script's full text into javascript_tool on every run cost ~10k tokens of
reading plus ~10k tokens of writing (the slowest part of a full check), and a hand-edited
`const PLAN = [...]` line was one more place to make a mistake. Now:

  * Each script's text is kept in the site's own localStorage (key "pc:js:<name>"), once per site
    and per script version. A RUN call is short: it reads the cached text, checks its SHA-256 against
    the repo version, swaps in today's argument lines (built here, by Python, from the same plan
    full_update.py checks against), checks the SHA-256 of the *filled-in* script against the one
    computed here, and only then runs it. So what runs is byte-for-byte the script this file would
    have printed for pasting, or nothing runs.
  * A RUN call that finds no cached copy (first use on a site, a new script version, cleared site
    data) returns `NEED_SCRIPT <name> (...)` and runs nothing. Then paste the STORE call
    (`jsrun.py store <name>`): it checks the pasted text's SHA-256 before saving, so a transcription
    slip is caught (`STORE REFUSED`) instead of running a damaged script. Then repeat the RUN call.
  * If a site blocks eval (`EVAL_BLOCKED`) or storage (`STORE FAILED`), fall back to
    `jsrun.py inline <name>`: today's filled-in script as plain text, pasted verbatim (the old way).

The scripts themselves are unchanged and still make no fetch/XHR requests; caching only changes how
their text reaches the page.

Since 2026-10-20 the runner itself (pricecheck/runner.js) is cached too ("pc:run", `jsrun.py store runner`,
once per site and runner version): a RUN call is a ~400-character prefix that checks the cached runner's
SHA-256 and calls it, hashes are passed as their first 16 hex digits, and the POLL call is
`await globalThis.__pcpoll(...)`, defined by the runner. A RUN call that finds no runner answers
`NEED_RUNNER (…)`: paste the `jsrun.py store runner` STORE call on that tab, then the RUN call again.
For snkrdunk_quick / snkrdunk_full the POLL sends the lines as a diff against the previous run
(scripts/salesdiff.py); `jsrun.py poll <name> --full` prints a POLL that returns them whole.

    python3 pricecheck/jsrun.py full                 # full-check setup: RUN + POLL calls for today's plan
    python3 pricecheck/jsrun.py quick [--ids a,b]    # quick check: RUN + POLL call for snkrdunk_quick (--ids: retry only those)
    python3 pricecheck/jsrun.py run <name>           # one RUN call (args filled from today's data)
    python3 pricecheck/jsrun.py store <name>         # STORE call, only after a RUN call said NEED_SCRIPT
    python3 pricecheck/jsrun.py store runner         # STORE call for the runner, after a RUN call said NEED_RUNNER
    python3 pricecheck/jsrun.py inline <name>        # the filled-in script as plain text (fallback)
    python3 pricecheck/jsrun.py poll <name> [--full] # the POLL call (--full: lines undiffed, after salesdiff refused a diff)
    python3 pricecheck/jsrun.py list                 # names, sites and hashes

Names: snkrdunk_full, snkrdunk_held, snkrdunk_quick, snkrdunk_sealed (snkrdunk.com) · psa_pop
(psacard.com) · pokeca_both, mytier, pokeca_premium, pokeca_scout (pokeca-chart.com).
Single-page scripts, run on the page they read (`jsrun.py run <name>`): snkrdunk_base, grade_tiles (a card's
product page), snkrdunk_listings (its /used?conditionIds=22 or 18 page), pokeca_index (a chart-index page).
"""
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "pricecheck" / "scripts"
sys.path.insert(0, str(ROOT / "pricecheck"))
sys.path.insert(0, str(ROOT / "scripts"))

# name: (site, source file or None, global the script reports into (None = returns its result directly),
#        argument constant names, line prefix for a direct result)
REGISTRY = {
    "snkrdunk_full":   ("snkrdunk.com",     "snkrdunk_full.js",   "__pj", ["PLAN"], None),
    "snkrdunk_held":   ("snkrdunk.com",     "snkrdunk_held.js",   "__hq", ["HELD"], None),
    "snkrdunk_quick":  ("snkrdunk.com",     "snkrdunk_quick.js",  "__pq", ["IDS"], None),
    "snkrdunk_sealed": ("snkrdunk.com",     "snkrdunk_sealed.js", "__sq", ["SEALED"], None),
    "psa_pop":         ("psacard.com",      "psa_pop.js",         "__pp", ["PSAPOP"], None),
    "pokeca_both":     ("pokeca-chart.com", "pokeca_both.js",     None,   [], None),
    "mytier":          ("pokeca-chart.com", None,                 None,   ["CODES"], "MYTIER "),
    "pokeca_premium":  ("pokeca-chart.com", "pokeca_premium.js",  "__pj", ["PREM"], None),
    "pokeca_scout":    ("pokeca-chart.com", "pokeca_scout.js",    "__pj", ["SCOUT"], None),
    # single-page scripts (adding a card, an evaluation's listing depth, the manual fallback): run on the page itself,
    # result as one prefixed JSON line, so a long one comes back through the runner's PAGE answer (2026-10-20)
    "snkrdunk_base":     ("snkrdunk.com",     "snkrdunk_base.js",     None, [], "BASE "),
    "grade_tiles":       ("snkrdunk.com",     "grade_tiles.js",       None, [], "TILES "),
    "snkrdunk_listings": ("snkrdunk.com",     "snkrdunk_listings.js", None, [], "LISTINGS "),
    "pokeca_index":      ("pokeca-chart.com", "pokeca_index.js",      None, [], "INDEX "),
}


ONLY_IDS = None   # `--ids a,b` on run/inline/quick: re-read only these cards (quick check retry of E lines)


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def arg_re(name):
    # JS mirror in RUNNER below: one whole line `<indent>const NAME = <anything>;`
    return re.compile(r"^[ \t]*const " + re.escape(name) + r" = .*;[ \t]*$", re.M)


def base_text(name):
    """The script as it is cached: the file without its top-of-file `//` comment lines (as setup always pasted it)."""
    _, fname, *_ = REGISTRY[name]
    if fname:
        raw = (SCRIPTS / fname).read_text(encoding="utf-8")
    else:  # the My-tier extractor lives in scripts/add_custom_index.py as a template
        import add_custom_index
        raw = add_custom_index.JS % "[]"
    text = "\n".join(ln for ln in raw.split("\n") if not ln.startswith("//")).strip("\n") + "\n"
    for a in REGISTRY[name][3]:
        n = len(arg_re(a).findall(text))
        if n != 1:
            sys.exit(f"ERROR: {name}: expected exactly one `const {a} = ...;` line, found {n}")
    return text


def args_for(name, plan=None):
    """Today's argument values, from the same sources the old instructions used."""
    if name in ("snkrdunk_full", "snkrdunk_held", "psa_pop", "pokeca_premium", "pokeca_scout"):
        import plan as planmod
        p = plan or planmod.build_plan(ROOT)
        key = {"snkrdunk_full": "plan", "snkrdunk_held": "held", "psa_pop": "psapop",
               "pokeca_premium": "premium", "pokeca_scout": "scout"}[name]
        return {REGISTRY[name][3][0]: p[key]}
    if name == "mytier":
        import add_custom_index
        return {"CODES": [c["code"] for c in add_custom_index.load()["meta"]["constituents"]]}
    if name == "snkrdunk_quick":
        return {"IDS": with_focus(ONLY_IDS if ONLY_IDS is not None else quick_ids())}
    if name == "snkrdunk_sealed":
        import sealed_info
        return {"SEALED": [list(x) for x in sealed_info.due(ROOT)]}
    return {}


NEAR_PCT = 5      # quick checks also read the listings of cards this close to a limit or a sell tier
NEAR_MAX = 3      # at most this many (closest first): about 10 s each on SNKRDUNK


def near_cards(root=ROOT):
    """Cards whose lowest PSA10 ask is within NEAR_PCT of your limit (watchlist) or of the Take-profit line (owned):
    where the order-book depth decides the next step, so a quick check reads their listings too (2026-10-23)."""
    try:
        m = json.loads((root / "data" / "manifest.json").read_text(encoding="utf-8"))
        snaps = sorted([s for s in m.get("snapshots", []) if s.get("collected_at_jst")], key=lambda s: s["collected_at_jst"])
        cards = json.loads((root / "data" / "snapshots" / snaps[-1]["file"]).read_text(encoding="utf-8")).get("cards", [])
        lim = (json.loads((root / "data" / "limits.json").read_text(encoding="utf-8")).get("limits") or {})
    except (OSError, ValueError, IndexError):
        return []
    near = []
    for c in cards:
        ask = ((c.get("grades") or {}).get("psa10") or {}).get("lowest_price")
        url = (c.get("url") or "").rstrip("/")
        if not ask or not url:
            continue
        l = (lim.get(url) or lim.get(url + "/") or {}).get("price")
        tp = (((c.get("analysis") or {}).get("sell_tiers") or {}).get("take_profit_from"))
        gaps = [abs(ask / l - 1) * 100 for l in [l] if l] + [abs(ask / tp - 1) * 100 for tp in [tp] if tp]
        if gaps and min(gaps) <= NEAR_PCT:
            near.append((min(gaps), url.split("/")[-1]))
    return [i for _, i in sorted(near)[:NEAR_MAX]]


def with_focus(ids):
    """Cards in Focus watch (data/focus.json), and cards near a limit or sell tier (near_cards), are written "<id>:L":
    the quick script also reads their PSA10 listings."""
    fp = ROOT / "data" / "focus.json"
    try:
        focus = {u.rstrip("/").split("/")[-1] for u in (json.loads(fp.read_text(encoding="utf-8")).get("cards") or {})}
    except (OSError, ValueError):
        focus = set()
    focus |= set(near_cards())
    return [f"{i}:L" if i in focus else i for i in ids]


def quick_ids():
    """The ids a quick check reads: every card in the latest snapshot plus tracked cards not published yet, minus removed cards."""
    m = json.loads((ROOT / "data" / "manifest.json").read_text(encoding="utf-8"))
    snaps = sorted([s for s in m.get("snapshots", []) if s.get("collected_at_jst")], key=lambda s: s["collected_at_jst"])
    if not snaps:
        return []
    latest = json.loads((ROOT / "data" / "snapshots" / snaps[-1]["file"]).read_text(encoding="utf-8"))
    rp = ROOT / "data" / "removed_cards.json"
    gone = set((json.loads(rp.read_text(encoding="utf-8")).get("removed") or {}).keys()) if rp.exists() else set()
    ids = [c.get("url", "").rstrip("/").split("/")[-1] for c in latest.get("cards", []) if c.get("url")]
    tp = ROOT / "data" / "tracked_cards.json"
    for t in (json.loads(tp.read_text(encoding="utf-8")).get("cards", []) if tp.exists() else []):
        if t.get("snkrdunk_id") and t["snkrdunk_id"] not in ids:
            ids.append(t["snkrdunk_id"])
    return [i for i in ids if i not in gone]


def arg_line(base, name, value):
    indent = re.match(r"[ \t]*", arg_re(name).search(base).group(0)).group(0)
    return f"{indent}const {name} = {json.dumps(value, ensure_ascii=False, separators=(',', ':'))};"


def filled(name, plan=None):
    """(base text, [(arg, line)], filled-in text) for today."""
    base = base_text(name)
    subs = [(a, arg_line(base, a, v)) for a, v in args_for(name, plan).items()]
    text = base
    for a, line in subs:
        text = arg_re(a).sub(lambda _m, line=line: line, text, count=1)
    return base, subs, text


RUNNER_FILE = ROOT / "pricecheck" / "runner.js"
SALES_DIFF = {"snkrdunk_quick", "snkrdunk_full"}   # their POLL sends the lines as a diff (scripts/salesdiff.py)


def runner_text():
    """The runner as cached in "pc:run": runner.js without its top-of-file `//` comment lines."""
    raw = RUNNER_FILE.read_text(encoding="utf-8")
    return "\n".join(ln for ln in raw.split("\n") if not ln.startswith("//")).strip("\n") + "\n"


# Part of every RUN call: checks the cached runner's SHA-256 (first 16 hex digits) and returns it as a function.
PREFIX = (
    "await (await (async H=>{let s;try{s=localStorage.getItem('pc:run')}catch(e){return()=>'NEED_RUNNER (site storage unavailable: '+e.message+'; use jsrun.py inline <name>)'}"
    "if(!s)return()=>'NEED_RUNNER (no runner cached on '+location.host+' yet)';"
    "const d=[...new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(s)))].map(b=>b.toString(16).padStart(2,'0')).join('');"
    "if(!d.startsWith(H))return()=>'NEED_RUNNER (the cached runner is another version)';"
    "try{return(0,eval)(s)}catch(e){return()=>'EVAL_BLOCKED runner: '+e.message}})(%s))"
)


STORE = (
    "await (async(n,h,s)=>{const key=n==='runner'?'pc:run':'pc:js:'+n;"
    "const d=[...new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(s)))].map(b=>b.toString(16).padStart(2,'0')).join('');"
    "if(d!==h)return 'STORE REFUSED '+n+': the pasted text differs from the repo version (hash mismatch); paste the STORE call again verbatim';"
    "try{localStorage.setItem(key,s)}catch(e){return 'STORE FAILED '+n+' ('+e.message+'); use jsrun.py inline '+n}"
    "return 'stored '+n+' '+h.slice(0,12)+' on '+location.host+': now repeat the RUN call'"
    "})"
)


def js_str(s):
    return json.dumps(s, ensure_ascii=False)


# Site check before a full check's reads start (FULL-CHECK batch 2): a thrown error stops the batch, so SNKRDUNK's
# 4-minute read never starts when PSA can't be read (Cloudflare with the VPN on, or signed out). 2026-10-23
PSA_CHECK = ("(() => { const t = document.title + ' ' + (document.body ? document.body.innerText.slice(0, 3000) : ''); "
             "if (!document.querySelector('table') && /Attention Required|Just a moment|verify you are human|Cloudflare/i.test(t)) throw new Error('PSA shows a Cloudflare check: turn the VPN off, then run again'); "
             "if (/signin|login/i.test(location.href)) throw new Error('PSA shows its sign-in page: sign in to psacard.com in this browser, then run again'); "
             "return 'PSA page ok'; })()")


def js_sq(s):
    """A single-quoted JS string literal: an argument's JSON text needs no escaping of its double quotes this way."""
    return "'" + s.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n").replace("\r", "\\r") + "'"


def sales_base(name):
    """The base hash for the POLL's diff ('' = no diff; '+' = a retry run: whole lines, base updated)."""
    if name not in SALES_DIFF:
        return ""
    if ONLY_IDS is not None:
        return "+"
    import salesdiff
    return salesdiff.base_hash(ROOT)


def run_call(name, plan=None):
    base, subs, text = filled(name, plan)
    pre = REGISTRY[name][4]
    vals = "[" + ",".join(f"[{js_str(a)},{js_sq(line.split(' = ', 1)[1][:-1])}]" for a, line in subs) + "]"
    g = REGISTRY[name][2]
    return (PREFIX % js_str(sha(runner_text())[:16])
            + f"({js_str(name)},{js_str(sha(base)[:16])},{vals},{js_str(sha(text)[:16])},"
              f"{js_str(pre) if pre else 'null'},{js_str(g) if g else 'null'},{js_str(sales_base(name))})")


def store_call(name):
    base = runner_text() if name == "runner" else base_text(name)
    return f"{STORE}({js_str(name)},{js_str(sha(base))},{js_str(base)})"


def poll_call(name, full=False):
    g = REGISTRY[name][2]
    if not g:
        return None
    return (f"await (globalThis.__pcpoll?globalThis.__pcpoll('{g}'{',1' if full else ''})"
            f":'NOT STARTED (no runner on this tab; RUN first)')")


def block(name, plan=None, note=""):
    site = REGISTRY[name][0]
    out = [f"--- {name}  [{site}]{('  ' + note) if note else ''}", "RUN:", run_call(name, plan)]
    p = poll_call(name)
    if p:
        out += ["POLL (repeat until it returns lines instead of `running i/N`):", p]
    return "\n".join(out)


def cmd_full():
    import plan as planmod
    p = planmod.build_plan(ROOT)
    print("JS CALLS (pricecheck/jsrun.py). Paste each RUN line verbatim into javascript_tool on a tab of the named site.")
    print("RUN returns `started …` (then POLL) or the result lines. NEED_RUNNER → `python3 pricecheck/jsrun.py store runner`,")
    print("paste that STORE call, then the same RUN call again. NEED_SCRIPT → `python3 pricecheck/jsrun.py store <name>`,")
    print("paste that STORE call, then the same RUN call again. EVAL_BLOCKED / STORE FAILED → `jsrun.py inline <name>`.")
    print("A long result answers `PAGE …`: its lines are now that tab's page; read them with get_page_text on that tab.")
    print()
    print(block("snkrdunk_full", p, "tab S"))
    if p.get("held"):
        print(block("snkrdunk_held", p, "tab S, after snkrdunk_full is done"))
    else:
        print("--- snkrdunk_held: HELD = [] → skip step 2b")
    if p.get("psapop"):
        print(f"--- psa_check  [psacard.com]  tab P, right after navigating it (FULL-CHECK batch 2): throws on a Cloudflare or sign-in page\nCHECK:\n{PSA_CHECK}")
        print(block("psa_pop", p, "tab P (www.psacard.com/pop/tcg-cards/156940)"))
    else:
        print("--- psa_pop: PSAPOP = [] → skip step 3")
    print(block("pokeca_both", p, "tab K on https://pokeca-chart.com/gr/chart-index/ (returns the two IDX lines)"))
    print(block("mytier", p, "tab K on https://pokeca-chart.com/gr/all-card/?sort=newest (returns the MYTIER line)"))
    if p.get("scout"):   # before the premiums: it reads the all-card list on the tab, and a long result replaces the page
        print(block("pokeca_scout", p, "tab K, right after mytier (still on the all-card page)"))
    else:
        print("--- pokeca_scout: SCOUT = null → skip step 4.4")
    if p.get("premium"):
        print(block("pokeca_premium", p, "tab K, after pokeca_scout is done (or right after mytier when Scout isn't due)"))


def main():
    a = sys.argv[1:]
    if not a or a[0] in ("-h", "--help"):
        print(__doc__)
        return
    global ONLY_IDS
    for i, x in enumerate(a):
        if x == "--ids" and i + 1 < len(a):
            ONLY_IDS = [s.strip() for s in a[i + 1].split(",") if s.strip()]
            unknown = [s for s in ONLY_IDS if s not in quick_ids()]
            if unknown:
                sys.exit(f"ERROR: --ids not on the tracker: {', '.join(unknown)}")
            a = a[:i] + a[i + 2:]
            break
    cmd, name = a[0], (a[1] if len(a) > 1 else None)
    if cmd == "full":
        return cmd_full()
    if cmd == "quick":
        return print(block("snkrdunk_quick", note="tab on https://snkrdunk.com/apparels/<first id>"))
    if cmd == "list":
        for n, (site, *_r) in REGISTRY.items():
            print(f"{n:16} {site:17} {sha(base_text(n))[:12]}")
        print(f"{'runner':16} {'(every site)':17} {sha(runner_text())[:12]}")
        return
    if cmd == "store" and name == "runner":
        return print(store_call("runner"))
    if name not in REGISTRY:
        sys.exit(f"ERROR: unknown script {name!r}; one of: {', '.join(REGISTRY)}")
    if cmd == "run":
        print(run_call(name))
    elif cmd == "store":
        print(store_call(name))
    elif cmd == "inline":
        print(filled(name)[2])
    elif cmd == "poll":
        print(poll_call(name, "--full" in a) or f"{name} returns its result directly; no POLL needed")
    else:
        sys.exit(f"ERROR: unknown command {cmd!r}")


if __name__ == "__main__":
    main()

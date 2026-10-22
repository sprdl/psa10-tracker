#!/usr/bin/env python3
"""
Checks pricecheck/jsrun.py's browser calls in Node (a VM context standing in for the page):
- a RUN call with nothing cached runs nothing and asks for the STORE call;
- a STORE call with a damaged text is refused; the real one is stored;
- a RUN call then evaluates exactly the filled-in script `jsrun.py inline <name>` prints (byte for byte);
- a cached copy of another version is not run; a corrupted argument line is not run;
- (since 2026-10-20) the runner itself is cached: a RUN call with no runner, or another runner version, asks
  for `jsrun.py store runner`, and the POLL call answers like the old inline one.

    python3 tests/test_jsrun.py        (needs node)
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pricecheck"))
import jsrun  # noqa: E402

HARNESS = r"""
const vm = require('vm');
const calls = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const store = new Map();
const evaluated = [];
const page = { text: null };
const ctx = vm.createContext({
  localStorage: { getItem: k => store.has(k) ? store.get(k) : null, setItem: (k, v) => store.set(k, String(v)) },
  location: { host: 'test.example' }, crypto: globalThis.crypto, TextEncoder, setTimeout,
  document: { createElement: () => ({}), body: { replaceChildren: (el) => { page.text = el.textContent; } } },
  __wsleep: () => Promise.resolve(),   // the POLL's wait, instant here
  // the cached runner is really evaluated; a script is only recorded (what would have run)
  eval: src => src.startsWith('/*pc-runner*/') ? vm.runInContext(src, ctx) : (evaluated.push(src), 'ran'),
});
const run = (code) => vm.runInContext('(async()=>{ return ' + code + ' })()', ctx);
(async () => {
  const out = [];
  for (const c of calls) {
    if (c.op === 'tamper') { const k = c.name === 'runner' ? 'pc:run' : 'pc:js:' + c.name; store.set(k, store.get(k) + ' '); out.push('tampered'); continue; }
    if (c.op === 'fake') { vm.runInContext(`globalThis.${c.g} = ${JSON.stringify(c.q)}`, ctx); out.push('faked'); continue; }
    if (c.op === 'page') { out.push(String(page.text)); continue; }
    if (c.op === 'evaluated') { out.push(evaluated.length ? evaluated[evaluated.length - 1] : null); continue; }
    out.push(String(await run(c.code)));
  }
  process.stdout.write(JSON.stringify(out));
})().catch(e => { console.error(e); process.exit(1); });
"""


def node(calls):
    r = subprocess.run(["node", "-e", HARNESS], input=json.dumps(calls), text=True, capture_output=True)
    if r.returncode:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


def corrupt_arg(run, name):
    args = jsrun.REGISTRY[name][3]
    if not args:
        return run
    a = args[0]
    assert run.count(f'["{a}",\'') == 1, "argument value should appear once in a RUN call"
    return run.replace(f'["{a}",\'', f'["{a}",\'1||', 1)


def check(name):
    run, store, inline = jsrun.run_call(name), jsrun.store_call(name), jsrun.filled(name)[2]
    base = jsrun.base_text(name)   # a paste with one character changed in the script text
    bad_store = f"{jsrun.STORE}({jsrun.js_str(name)},{jsrun.js_str(jsrun.sha(base))},{jsrun.js_str(base.replace('const ', 'const  ', 1))})"
    g = jsrun.REGISTRY[name][2]
    out = node([
        {"code": run},                       # 0 nothing cached: the runner first
        {"code": jsrun.store_call("runner")},
        {"code": run},                       # 0 now the script
        {"code": bad_store},                 # 1 damaged paste
        {"code": run},                       # 2 still nothing cached
        {"code": store},                     # 3 real store
        {"code": run},                       # 4 runs
        {"op": "evaluated"},                 # 5 what ran
        {"op": "tamper", "name": name},      # 6
        {"code": run},                       # 7 other version
        {"code": store},                     # 8 re-store
        {"code": corrupt_arg(run, name)},    # 9 corrupted arg line
        {"op": "tamper", "name": "runner"},  # 10
        {"code": run},                       # 11 other runner version
        {"code": jsrun.store_call("runner")},
        {"op": "fake", "g": g or "__none", "q": {"done": False, "i": 2, "n": 5, "lines": []}},
        {"code": jsrun.poll_call(name) or "'no poll'"},  # 14 running
        {"op": "fake", "g": g or "__none", "q": {"done": True, "i": 5, "n": 5, "lines": ["H 1", "H 2"]}},
        {"code": jsrun.poll_call(name) or "'no poll'"},  # 16 lines (non-card lines are never diffed)
        {"op": "fake", "g": g or "__none", "q": {"done": True, "i": 5, "n": 5, "lines": ["H %03d %s" % (i, "y" * 40) for i in range(40)]}},
        {"code": jsrun.poll_call(name) or "'no poll'"},  # 18 too long: becomes the page
        {"op": "page"},                                  # 19 what the page holds
    ])
    assert out[0].startswith("NEED_RUNNER"), out[0]
    assert out[1].startswith("stored runner"), out[1]
    out = out[2:]
    assert out[0].startswith(f"NEED_SCRIPT {name}"), out[0]
    assert out[1].startswith(f"STORE REFUSED {name}"), out[1]
    assert out[2].startswith(f"NEED_SCRIPT {name}"), out[2]
    assert out[3].startswith(f"stored {name}"), out[3]
    pre = jsrun.REGISTRY[name][4]
    assert out[4] == ((pre or "") + "ran"), out[4]
    expected = inline[len("await "):] if inline.startswith("await ") else inline
    assert out[5] == expected, f"{name}: evaluated text differs from `jsrun.py inline`"
    assert out[7].startswith(f"NEED_SCRIPT {name}") and "another version" in out[7], out[7]
    assert out[8].startswith(f"stored {name}"), out[8]
    if jsrun.REGISTRY[name][3]:
        assert out[9].startswith(f"RUNNER ERROR {name}"), out[9]
    for a, line in jsrun.filled(name)[1]:
        assert line in out[5], f"{name}: argument line for {a} missing"
    assert out[11].startswith("NEED_RUNNER") and "another version" in out[11], out[11]
    if g:
        assert out[14] == "running 2/5", out[14]
        assert out[16].split("\n")[:2] == ["H 1", "H 2"], out[16]
        tail = out[16].split("\n")[2:]
        assert tail[-1].startswith(f"#T {name} "), out[16]                       # the run's timing (run-clock laps)
        assert (name in jsrun.SALES_DIFF) == (len(tail) == 2 and tail[0].startswith("#B ")), out[16]   # + the #B line
        long = ["H %03d %s" % (i, "y" * 40) for i in range(40)]
        assert out[18].startswith("PAGE ") and len(out[18]) < 300, out[18]
        assert out[19].split("\n")[:40] == long, out[19][:200]
    n_prefix = len(jsrun.PREFIX % '"0123456789abcdef"')
    assert len(run) < n_prefix + 300 + sum(len(l) for _, l in jsrun.filled(name)[1]), f"{name}: RUN call longer than expected"
    print(f"ok  {name}")


if __name__ == "__main__":
    for n in jsrun.REGISTRY:
        check(n)
    print("all jsrun checks passed")

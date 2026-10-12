#!/usr/bin/env python3
"""
Checks pricecheck/jsrun.py's browser calls in Node (a VM context standing in for the page):
- a RUN call with nothing cached runs nothing and asks for the STORE call;
- a STORE call with a damaged text is refused; the real one is stored;
- a RUN call then evaluates exactly the filled-in script `jsrun.py inline <name>` prints (byte for byte);
- a cached copy of another version is not run; a corrupted argument line is not run.

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
const ctx = vm.createContext({
  localStorage: { getItem: k => store.has(k) ? store.get(k) : null, setItem: (k, v) => store.set(k, String(v)) },
  location: { host: 'test.example' }, crypto: globalThis.crypto, TextEncoder,
  eval: src => { evaluated.push(src); return 'ran'; },
});
const run = (code) => vm.runInContext('(async()=>{ return ' + code + ' })()', ctx);
(async () => {
  const out = [];
  for (const c of calls) {
    if (c.op === 'tamper') { store.set('pc:js:' + c.name, store.get('pc:js:' + c.name) + ' '); out.push('tampered'); continue; }
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
    assert run.count(f"const {a} = ") == 1, "argument line should appear once in a RUN call"
    return run.replace(f"const {a} = ", f"const {a} = 1||", 1)


def check(name):
    run, store, inline = jsrun.run_call(name), jsrun.store_call(name), jsrun.filled(name)[2]
    base = jsrun.base_text(name)   # a paste with one character changed in the script text
    bad_store = f"{jsrun.STORE}({jsrun.js_str(name)},{jsrun.js_str(jsrun.sha(base))},{jsrun.js_str(base.replace('const ', 'const  ', 1))})"
    out = node([
        {"code": run},                       # 0 nothing cached
        {"code": bad_store},                 # 1 damaged paste
        {"code": run},                       # 2 still nothing cached
        {"code": store},                     # 3 real store
        {"code": run},                       # 4 runs
        {"op": "evaluated"},                 # 5 what ran
        {"op": "tamper", "name": name},      # 6
        {"code": run},                       # 7 other version
        {"code": store},                     # 8 re-store
        {"code": corrupt_arg(run, name)},    # 9 corrupted arg line
    ])
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
    print(f"ok  {name}")


if __name__ == "__main__":
    for n in jsrun.REGISTRY:
        check(n)
    print("all jsrun checks passed")

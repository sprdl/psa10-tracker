// The in-page runner of pricecheck/jsrun.py (2026-10-20). Kept in each site's localStorage as "pc:run" (STORE call
// `jsrun.py store runner`, once per site and runner version), so a RUN call is a short prefix that checks this text's
// SHA-256 and calls it with the script name, the script's hash, today's argument values, the filled-in script's hash,
// the result prefix, the global the script reports into and the sales base hash. Same rules as before it moved here:
// the cached script runs only if its SHA-256 matches the repo version and the filled-in script matches jsrun.py's build.
// It also defines globalThis.__pcpoll(<global>, full): the POLL call. For snkrdunk_quick / snkrdunk_full (B given) the
// POLL sends each card's sales and listing lists as a diff against the previous run's lines (kept in localStorage
// "pc:base", mirrored in data/incoming/snk-base.json by scripts/salesdiff.py) and ends with a `#B <mode> <new base>
// <lines>` line; scripts/salesdiff.py rebuilds the exact lines and checks them against that hash.
/*pc-runner*/(async (n, h, subs, hf, pre, g, B) => {
  const G = globalThis;
  const sha = async (t) => [...new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(t)))].map((b) => b.toString(16).padStart(2, '0')).join('');
  const LIST = /^[PALR][^=^\s]*=/;
  const canon = (o) => Object.keys(o).sort().map((k) => k + '\t' + o[k] + '\n').join('');
  // one line against its base line: in a list token (P/A sales, L/R listings), each run of entries that also stands in
  // the base line's list of the same letter becomes <start>.<count>; the token becomes <letter><flags>^<items>
  // (only when that is shorter). Literal entries never look like <digits>.<digits>.
  const cmp = (line, base) => {
    const t = line.split(' ');
    if (!/^\d+$/.test(t[0]) || !base) return line;
    const b = base.split(' ');
    return t.map((x, i) => {
      const m = i && x.match(/^([PALR])([^=^\s]*)=(.+)$/);
      if (!m) return x;
      const bt = b.find((y) => y[0] === m[1] && LIST.test(y));
      if (!bt) return x;
      const o = bt.slice(bt.indexOf('=') + 1).split(','), nw = m[3].split(','), items = [];
      let p = 0, used = false;
      while (p < nw.length) {
        let J = 0, K = 0;
        for (let j = 0; j < o.length; j++) { let k = 0; while (p + k < nw.length && j + k < o.length && o[j + k] === nw[p + k]) k++; if (k > K) { K = k; J = j; } }
        const ref = J + '.' + K;
        if (K && ref.length < nw.slice(p, p + K).join(',').length) { items.push(ref); p += K; used = true; } else { items.push(nw[p]); p++; }
      }
      if (!used) return x;
      const y = m[1] + m[2] + '^' + items.join(',');
      return y.length < x.length ? y : x;
    }).join(' ');
  };
  // the base keeps each card's last good line, plus its last L/R list when the new line has none (a quick check, Rc)
  const update = (base, lines) => {
    for (const l of lines) {
      const t = l.split(' ');
      if (!/^\d+$/.test(t[0]) || (t[1] || '').startsWith('E')) continue;
      const keep = (base[t[0]] || '').split(' ').filter((y) => /^[LR]/.test(y) && LIST.test(y) && !t.some((z) => z[0] === y[0] && LIST.test(z)));
      base[t[0]] = t.concat(keep).join(' ');
    }
  };
  const pack = async (lines, bm) => {
    let base = {};
    try { base = JSON.parse(localStorage.getItem('pc:base') || '{}') || {}; } catch (e) { base = {}; }
    const cur = (await sha(canon(base))).slice(0, 16);
    let mode = '+', out = lines;
    if (bm !== '+') {
      if (bm === cur) { mode = cur; out = lines.map((l) => cmp(l, base[l.split(' ')[0]])); } else { mode = '-'; base = {}; }
    }
    update(base, lines);
    let nb = '-';
    try { localStorage.setItem('pc:base', JSON.stringify(base)); nb = (await sha(canon(base))).slice(0, 16); } catch (e) { nb = '-'; }
    return { out: out.join('\n'), tr: '#B ' + mode + ' ' + nb + ' ' + (await sha(lines.join('\n'))).slice(0, 16) };
  };
  G.__pcpoll = async (gg, full) => {
    for (let i = 0; i < 75 && !G[gg]?.done; i++) await (G.__wsleep || ((m) => new Promise((r) => setTimeout(r, m))))(500);
    const q = G[gg];
    if (!q) return 'NOT STARTED (no window.' + gg + ' on this tab)';
    if (!q.done) return `running ${q.i}/${q.n}${G.document?.hidden ? ' (tab hidden)' : ''}`;
    const bm = (G.__pcB || {})[gg];
    if (!bm) return q.lines.join('\n');
    if (!q.__pc) q.__pc = await pack(q.lines, bm);   // once per run: it also stores the new base
    return (full ? q.lines.join('\n') : q.__pc.out) + '\n' + q.__pc.tr;
  };
  let s;
  try { s = localStorage.getItem('pc:js:' + n); } catch (e) { return 'NEED_SCRIPT ' + n + ' (site storage unavailable: ' + e.message + '; use jsrun.py inline ' + n + ')'; }
  if (!s) return 'NEED_SCRIPT ' + n + ' (not cached on ' + location.host + ' yet)';
  if (!(await sha(s)).startsWith(h)) return 'NEED_SCRIPT ' + n + ' (cached copy is another version)';
  for (const [k, v] of subs) {
    const re = new RegExp('^[ \\t]*const ' + k + ' = .*;[ \\t]*$', 'gm');
    const m = s.match(re);
    if (!m || m.length !== 1) return 'RUNNER ERROR ' + n + ': ' + (m ? m.length : 0) + ' lines for ' + k;
    s = s.replace(re, (x) => x.match(/^[ \t]*/)[0] + 'const ' + k + ' = ' + v + ';');
  }
  if (!(await sha(s)).startsWith(hf)) return 'RUNNER ERROR ' + n + ': filled-in script differs from the repo build; nothing ran';
  if (g) (G.__pcB = G.__pcB || {})[g] = B || '';
  let r;
  try { r = (0, eval)(s.replace(/^\s*await\s+/, '')); } catch (e) { return (e instanceof EvalError ? 'EVAL_BLOCKED ' : 'SCRIPT ERROR ') + n + ': ' + e.message; }
  r = await r;
  if (!pre) return r;
  if (r && typeof r === 'object' && r.error) return pre.trim() + '! ' + r.error;
  return pre + (typeof r === 'string' ? r : JSON.stringify(r));
})

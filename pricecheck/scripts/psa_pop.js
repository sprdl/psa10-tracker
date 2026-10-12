// PSA's own population report for the tracked cards (FULL check, step 3), in ONE javascript call. Run it on any
// https://www.psacard.com page (signed in: the pop report needs a PSA account) with PSAPOP filled in from
// `python3 pricecheck/plan.py` ("PSAPOP = [...]" line). Opens each SET page once in a hidden same-origin iframe
// (several cards of one set share a page), lets the page's own "Show" menu list the whole set, and reads the
// rows of the tracked card numbers. One page load per set, a pause between sets; no fetch/XHR of its own.
// Returns at once; poll window.__pp like the other batch scripts:
//   await (async()=>{for(let i=0;i<75&&!window.__pp.done;i++)await (window.__wsleep||(m=>new Promise(r=>setTimeout(r,m))))(500);const q=window.__pp;return q.done?q.lines.join('\n'):`running ${q.i}/${q.n}${document.hidden?' (tab hidden)':''}`})()
// Lines (decoded by scripts/full_update.py):
//   POP <snkrdunk id> n<PSA 10 count> t<total graded> c<uri card no.> v<uri variety, or ->
//   POP <snkrdunk id> !<uri error>      (sign-in page, Cloudflare check, row not found, …)
// A card number can have several rows (variants such as errors or stamps): the row whose name has no extra
// variety text wins, else the biggest total; `name` (English, from psa_pop_name) narrows the match when given.
(() => {
  const PSAPOP = [/* ["164250","/pop/tcg-cards/2023/pokemon-japanese-sv4a-shiny-treasure-ex/255404","347","Mew EX"], … */];
  if (window.__pp && !window.__pp.done) return `already running ${window.__pp.i}/${window.__pp.n}`;
  const q = window.__pp = { n: PSAPOP.length, i: 0, lines: [], done: false };
  const sleep = window.__wsleep || (window.__wsleep = (() => {
    const P = {}; let n = 0, w = null;
    try { w = new Worker(URL.createObjectURL(new Blob(['onmessage=e=>setTimeout(()=>postMessage(e.data[0]),e.data[1])'], { type: 'text/javascript' }))); w.onmessage = (e) => { const r = P[e.data]; delete P[e.data]; if (r) r(); }; } catch (e) { w = null; }
    return (ms) => new Promise((r) => { if (w) { P[++n] = r; w.postMessage([n, ms]); } setTimeout(r, ms); });
  })());
  const enc = encodeURIComponent;
  const num = (s) => { const t = String(s || '').replace(/[,\s]/g, ''); return /^\d+$/.test(t) ? Number(t) : null; };
  const bySet = {};
  for (const [sid, url, no, name] of PSAPOP) (bySet[new URL(url, location.origin).pathname] = bySet[new URL(url, location.origin).pathname] || []).push({ sid, no: String(no), name: name || '' });
  (async () => {
    for (const [path, want] of Object.entries(bySet)) {
      const fail = (msg) => { for (const w of want) { q.lines.push(`POP ${w.sid} !${enc(msg)}`); q.i++; } };
      const f = document.createElement('iframe');
      f.style.cssText = 'position:fixed;left:-3000px;top:0;width:1400px;height:2400px;border:0';
      f.src = path;
      document.body.appendChild(f);
      try {
        let d = null;
        for (let i = 0; i < 60; i++) {
          await sleep(400);
          const x = f.contentDocument;
          if (!x || !x.body) continue;
          if (/signin|errors\/notfound/.test(x.location.href)) break;
          if (x.querySelector('#tablePSA tbody tr td:nth-child(2)') && x.querySelector('.dataTables_info')) { d = x; break; }
        }
        if (!d) {
          const x = f.contentDocument, href = x ? x.location.href : '';
          fail(/signin/.test(href) ? 'PSA sign-in page: sign in to psacard.com in this browser' : /notfound/.test(href) ? 'set page not found (check psa_pop_url)'
            : /Just a moment|verify you are human|Cloudflare/i.test(x && x.body ? x.body.innerText : '') ? 'Cloudflare check (VPN on?)' : 'pop table did not load');
          continue;
        }
        // the page's own "Show" menu: largest page size, then page through if the set is still bigger
        const sel = d.querySelector('.dataTables_length select');
        if (sel) {
          const before = d.querySelector('.dataTables_info').innerText;
          sel.value = [...sel.options].map((o) => o.value).pop();
          sel.dispatchEvent(new Event('change', { bubbles: true }));
          for (let i = 0; i < 30 && d.querySelector('.dataTables_info').innerText === before; i++) await sleep(400);
          await sleep(600);
        }
        const rows = [];
        for (let page = 0; page < 6; page++) {
          for (const r of d.querySelectorAll('#tablePSA tbody tr')) {
            const td = r.children; if (td.length < 17) continue;
            const no = td[1].innerText.trim(); if (!no) continue;
            const strong = td[2].querySelector('strong');
            const full = td[2].innerText.replace(/Shop with Affiliates/g, '').replace(/\s+/g, ' ').trim();
            const nm = strong ? strong.innerText.trim() : full;
            const first = (c) => { const dv = c.querySelector('div'); return num(dv ? dv.innerText : c.innerText); };
            rows.push({ no, name: nm, variety: full.slice(nm.length).trim(), ten: first(td[15]), total: first(td[16]) });
          }
          const next = d.querySelector('.dataTables_paginate .next:not(.disabled) a, .dataTables_paginate a.next:not(.disabled)');
          const m = d.querySelector('.dataTables_info').innerText.replace(/,/g, '').match(/to (\d+) of (\d+)/);
          if (!next || !m || Number(m[1]) >= Number(m[2])) break;
          const before = d.querySelector('.dataTables_info').innerText;
          next.click();
          for (let i = 0; i < 30 && d.querySelector('.dataTables_info').innerText === before; i++) await sleep(400);
          await sleep(600);
        }
        for (const w of want) {
          let c = rows.filter((r) => r.no === w.no || r.no.replace(/^0+/, '') === w.no.replace(/^0+/, ''));
          if (w.name) { const nn = c.filter((r) => r.name.toLowerCase().includes(w.name.toLowerCase())); if (nn.length) c = nn; }
          if (!c.length) { q.lines.push(`POP ${w.sid} !${enc(`card no. ${w.no} not found on the set page (${rows.length} rows read)`)}`); q.i++; continue; }
          const plain = c.filter((r) => !r.variety);
          const r = (plain.length ? plain : c).sort((a, b) => (b.total || 0) - (a.total || 0))[0];
          q.lines.push(r.ten == null || r.total == null ? `POP ${w.sid} !${enc('grade cells not readable')}`
            : `POP ${w.sid} n${r.ten} t${r.total} c${enc(r.no + ' ' + r.name)} v${r.variety ? enc(r.variety) : '-'}`);
          q.i++;
        }
      } catch (e) {
        fail(String((e && e.message) || e));
      } finally { f.remove(); }
      await sleep(1500);
    }
    q.done = true;
  })();
  return `started ${PSAPOP.length} cards in ${Object.keys(bySet).length} set pages`;
})();

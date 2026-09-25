(function () {
  'use strict';

  const state = {
    manifest: null,
    currentIndex: -1, // index into manifest.snapshots (chronological ascending)
    currentData: null,
    previousData: null,
    calls: null, // data/calls.json — track record of past calls (scripts/build_calls.py)
    holdings: [], // data/holdings.json — purchases you've actually made (see docs/schema.md)
    selectedUrl: null, // card shown in the overview's detail drawer (desktop)
    cardTab: 'overview', // last-used tab of the card detail
    cardFrom: 'overview', // view a card page was opened from (for the back link)
  };

  const els = {
    snapshotSelects: [document.getElementById('snapshot-select'), document.getElementById('snapshot-select-m')],
    collectedAt: document.getElementById('collected-at'),
    marketStrip: document.getElementById('market-strip'),
    banners: document.getElementById('banners'),
    notesBody: document.getElementById('notes-body'),
    cards: document.getElementById('watchlist'),
    watchPanel: document.getElementById('watch-panel'),
    portfolioSummary: document.getElementById('portfolio-summary'),
    portfolioList: document.getElementById('portfolio-list'),
  };

  // Deterministic abstract art-band variant per card (by url), so a given card
  // always gets the same purely-decorative color band across snapshots. These
  // are plain gradients — never a character likeness (see project copyright note).
  const ART_CLASSES = ['art-1', 'art-2', 'art-3', 'art-4', 'art-5', 'art-6', 'art-7', 'art-8'];
  function artClassFor(card) {
    const key = card.url || card.card_name_ja || '';
    let hash = 0;
    for (let i = 0; i < key.length; i++) hash = (hash * 31 + key.charCodeAt(i)) >>> 0;
    return ART_CLASSES[hash % ART_CLASSES.length];
  }

  // card_name_ja embeds the set code/number and pack name as trailing
  // "[code] (pack name)" — split it so the lot shows a clean serif name plus a
  // small meta line, without inventing any field the JSON doesn't have.
  const VERDICT_TAG_LABELS = {
    definitely_buy: 'Definitely buy', buy: 'Buy', watch: 'Watch', dont_buy: "Don't buy", defer: 'Defer',
  };

  function capitalize(s) { return s ? s.charAt(0).toUpperCase() + s.slice(1) : s; }

  // verdict.label is a full descriptive headline ("Buy — still grinding toward
  // definitely-buy"), not a short tag — too long for a pill. Pull the short tag
  // word from verdict.tag for the pill, and use the label's own remainder
  // (after the dash) as a bold lead-in sentence above the reasoning paragraph.
  function verdictHeadline(label) {
    if (!label) return '';
    const m = label.match(/—\s*(.+)$/);
    return capitalize((m ? m[1] : label).trim());
  }

  function parseCardName(name) {
    const m = (name || '').match(/^(.*?)\s*\[([^\]]+)\]\s*\(([^)]+)\)\s*$/);
    if (m) return { short: m[1].trim(), code: m[2].trim(), pack: m[3].trim() };
    return { short: name || '', code: '', pack: '' };
  }

  // ---------- formatting helpers ----------

  function fmtYen(n) {
    if (n === null || n === undefined || isNaN(n)) return '—';
    return '¥' + Math.round(n).toLocaleString('en-US');
  }

  function fmtYenShort(n) {
    if (n === null || n === undefined || isNaN(n)) return '—';
    if (Math.abs(n) >= 10000) return '¥' + (n / 1000).toFixed(1) + 'k';
    return fmtYen(n);
  }

  function fmtPct(n, digits) {
    if (n === null || n === undefined || isNaN(n)) return '—';
    const d = digits === undefined ? 1 : digits;
    const sign = n > 0 ? '+' : '';
    return sign + n.toFixed(d) + '%';
  }

  function fmtDateJST(iso) {
    const m = iso.match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/);
    if (!m) return iso;
    const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
    const [, y, mo, d, h, mi] = m;
    return `${months[parseInt(mo, 10) - 1]} ${parseInt(d, 10)}, ${y} ${h}:${mi} JST`;
  }

  // Values carried from an earlier full check (quick runs) carry the time they were
  // really measured; show it so old numbers never pass for new ones.
  function asOfHtml(iso) {
    return iso ? `<span class="asof">as of ${escapeHtml(fmtDateShort(iso).slice(5))}</span>` : '';
  }

  function fmtDateShort(iso) {
    const m = iso.match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/);
    if (!m) return iso;
    const [, y, mo, d, h, mi] = m;
    return `${y}/${mo}/${d} ${h}:${mi}`;
  }

  function roundToThousand(n) {
    return Math.round(n / 1000) * 1000;
  }

  function escapeHtml(str) {
    if (str === null || str === undefined) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  // For values placed inside an HTML attribute (e.g. src="...") — also escapes quotes.
  function escapeAttr(str) {
    return escapeHtml(str).replace(/"/g, '&quot;');
  }

  function dirClass(pct) {
    if (pct === null || pct === undefined || isNaN(pct) || pct === 0) return '';
    return pct > 0 ? 'pos' : 'neg';
  }

  // ---------- data loading ----------

  async function fetchJSON(path) {
    const res = await fetch(path, { cache: 'no-store' });
    if (!res.ok) throw new Error(`Failed to fetch ${path}: ${res.status}`);
    return res.json();
  }

  async function init() {
    try {
      state.manifest = await fetchJSON('data/manifest.json');
    } catch (e) {
      els.cards.innerHTML = `<div class="empty-state">Couldn't load data/manifest.json. Has a snapshot been added yet?</div>`;
      document.querySelectorAll('.view').forEach((v) => { v.hidden = v.dataset.view !== 'overview'; });
      return;
    }

    const snaps = state.manifest.snapshots || [];
    if (!snaps.length) {
      els.cards.innerHTML = `<div class="empty-state">No snapshots yet — run add_snapshot to publish the first one.</div>`;
      return;
    }

    els.snapshotSelects.forEach((sel) => {
      sel.innerHTML = '';
      for (let i = snaps.length - 1; i >= 0; i--) {
        const opt = document.createElement('option');
        opt.value = String(i);
        opt.textContent = fmtDateShort(snaps[i].collected_at_jst) + (snaps[i].check_mode === 'quick' ? ' · quick' : '');
        sel.appendChild(opt);
      }
      sel.value = String(snaps.length - 1);
      sel.addEventListener('change', () => {
        els.snapshotSelects.forEach((o) => { o.value = sel.value; });
        loadIndex(parseInt(sel.value, 10));
      });
    });
    window.addEventListener('hashchange', () => { applyRoute(); window.scrollTo(0, 0); });

    // Holdings are optional and rare to change — a missing file just means
    // nothing's been bought yet, not an error.
    try {
      const h = await fetchJSON('data/holdings.json');
      state.holdings = h.holdings || [];
    } catch (e) {
      state.holdings = [];
    }

    try { state.calls = await fetchJSON('data/calls.json'); } catch (e) { state.calls = null; }

    await loadIndex(snaps.length - 1);
  }

  async function loadIndex(idx) {
    const snaps = state.manifest.snapshots;
    state.currentIndex = idx;
    state.currentData = await fetchJSON('data/snapshots/' + snaps[idx].file);
    state.previousData = idx > 0 ? await fetchJSON('data/snapshots/' + snaps[idx - 1].file) : null;
    render();
  }

  // ---------- derived-value helpers ----------
  // Everything here is computed fresh from raw inputs each render — never store a derived
  // number in the snapshot JSON itself (see docs/schema.md).

  function getRep(card) {
    const psa10 = card.grades && card.grades.psa10;
    const a = card.analysis;
    if (a && a.representative_price != null) return a.representative_price;
    return psa10 ? psa10.lowest_price : null;
  }

  function depthInfo(grade) {
    const within = grade.count_within_15pct || 0;
    const total = (grade.top20_cheapest_listings || []).length || 20;
    const ratio = total ? Math.min(1, within / total) : 0;
    return { within, total, ratio, cls: ratio >= 0.4 ? 'depth-tight' : 'depth-thin' };
  }

  function salesRangeText(sales) {
    if (!sales || !sales.length) return '—';
    const prices = sales.map((s) => s.price);
    return `${fmtYen(Math.min(...prices))}–${fmtYen(Math.max(...prices))}`;
  }

  function computeOffPeakPct(peakPrice, repPrice) {
    if (!peakPrice) return null;
    return ((peakPrice - repPrice) / peakPrice) * 100;
  }

  function computeDiyEconomics(card, repPrice) {
    const a = card.analysis;
    const raw = card.grades && card.grades.raw_a_grade;
    if (!a || a.grading_fee_jpy == null || !raw || card.psa10_gem_rate_pct == null) return null;
    const gradingFee = a.grading_fee_jpy;
    const shipping = a.shipping_insurance_jpy != null ? a.shipping_insurance_jpy : 2000;
    const gemRate = card.psa10_gem_rate_pct / 100;
    if (!gemRate) return null;
    const rawPrice = raw.lowest_price;
    const diyExpected = (rawPrice + gradingFee + shipping) / gemRate;
    const delta = diyExpected - repPrice;
    return { gradingFee, shipping, rawPrice, diyExpected, delta };
  }

  function computeGauge(tiers, peakPrice, currentPrice) {
    if (!tiers || !peakPrice) return null;
    const scaleMax = roundToThousand(peakPrice * 1.08) || peakPrice;
    const db = tiers.definitely_buy, bu = tiers.buy_upper, ceil = tiers.ceiling;
    const watchMid = (bu + ceil) / 2;
    const pct = (v) => Math.min(100, Math.max(0, (v / scaleMax) * 100));
    return {
      scaleMax,
      dbPct: pct(db), buPct: pct(bu), watchMidPct: pct(watchMid), ceilPct: pct(ceil),
      curPct: pct(currentPrice), peakPct: pct(peakPrice),
    };
  }

  function zoneOf(tiers, price) {
    if (price <= tiers.definitely_buy) return 'definitely-buy';
    if (price <= tiers.buy_upper) return 'buy';
    if (price <= tiers.ceiling) return 'watch';
    return "don't-buy";
  }

  // Same four zones as zoneOf, but keyed like verdict.tag (definitely_buy /
  // buy / watch / dont_buy) so the verdict pill can be computed live from the
  // current price vs. the card's tiers on every refresh — no Claude review
  // needed for the pill itself, only for the written reasoning.
  function liveTagOf(tiers, price) {
    if (!tiers || price == null) return null;
    if (price <= tiers.definitely_buy) return 'definitely_buy';
    if (price <= tiers.buy_upper) return 'buy';
    if (price <= tiers.ceiling) return 'watch';
    return 'dont_buy';
  }

  // A written "defer" is a deliberate human call ("don't act regardless of
  // price"), so it wins over the computed zone; otherwise the live zone wins.
  function displayTagFor(card) {
    const a = card.analysis;
    if (!a) return null;
    const written = a.verdict && a.verdict.tag;
    if (written === 'defer') return 'defer';
    return liveTagOf(a.tiers, getRep(card)) || written || null;
  }

  function tagLabel(tag) {
    return VERDICT_TAG_LABELS[tag] || (tag || '').replace(/_/g, ' ');
  }

  // ---------- my limit prices + buy signals (saved in this browser only) ----------
  // Storage can be unavailable (private mode, blocked site data): every read falls
  // back to a default and every write is best-effort, so the site still works.
  const store = {
    get(key, dflt) { try { const v = localStorage.getItem(key); return v ? JSON.parse(v) : dflt; } catch (e) { return dflt; } },
    set(key, val) { try { localStorage.setItem(key, JSON.stringify(val)); } catch (e) { /* not persisted */ } },
  };
  let limits = store.get('psa10.limits', {});
  const LIMIT_STEP = 500;

  function getLimit(card) { const v = limits[card.url]; return typeof v === 'number' ? v : null; }
  function setLimit(card, v) {
    if (v == null) delete limits[card.url];
    else limits[card.url] = Math.max(LIMIT_STEP, Math.round(v / LIMIT_STEP) * LIMIT_STEP);
    store.set('psa10.limits', limits);
  }
  // A limit is "hit" when a PSA10 listing you could buy right now is at or below it —
  // so this compares the lowest ask, not the representative (sales) price.
  function lowestAsk(card) { const p = card.grades && card.grades.psa10; return p ? p.lowest_price : null; }
  function limitHit(card) { const l = getLimit(card), a = lowestAsk(card); return l != null && a != null && a <= l; }

  // ---------- purchases (data/holdings.json, written by GitHub Actions) ----------
  // "Bought it" / "Remove" open a pre-filled GitHub issue form; .github/workflows/purchases.yml
  // turns it into a holdings.json change and redeploys the site. Nothing is stored here.
  const REPO_URL = 'https://github.com/sprdl/psa10-tracker';
  function todayJST() { return new Date(Date.now() + 9 * 3600e3).toISOString().slice(0, 10); }
  function holdingCost(h) {
    const grading = h.condition === 'raw_to_grade'
      ? (h.grading_fee_jpy || 0) + (h.shipping_insurance_jpy != null ? h.shipping_insurance_jpy : 2000)
      : 0;
    return (h.purchase_price_jpy || 0) + grading;
  }
  function holdingsFor(card) { return state.holdings.filter((h) => h.card_url === card.url); }
  function boughtFormUrl(card) {
    const q = new URLSearchParams({ template: 'bought.yml', title: 'Bought: ' + parseCardName(card.card_name_ja).short,
      url: card.url, price: String(lowestAsk(card) || ''), date: todayJST() });
    return `${REPO_URL}/issues/new?${q}`;
  }
  function removeFormUrl(h) {
    const q = new URLSearchParams({ template: 'remove-purchase.yml',
      title: 'Remove purchase: ' + parseCardName(h.card_name_ja || '').short, id: h.id });
    return `${REPO_URL}/issues/new?${q}`;
  }

  function computeSignals(cards) {
    const out = [];
    cards.forEach((card, i) => {
      if (lowestAsk(card) == null) return;
      const name = parseCardName(card.card_name_ja).short;
      if (limitHit(card)) {
        out.push({ key: card.url + '|limit', i, card, name, kind: 'limit', rank: 0,
          text: `Lowest ask ${fmtYen(lowestAsk(card))} is at or below your limit ${fmtYen(getLimit(card))}` });
      }
      const tag = displayTagFor(card);
      if (tag === 'definitely_buy' || tag === 'buy') {
        const t = card.analysis.tiers;
        out.push({ key: card.url + '|' + tag, i, card, name, kind: tag, rank: tag === 'definitely_buy' ? 1 : 2,
          text: `${fmtYen(getRep(card))} is in the ${tagLabel(tag)} zone (≤${fmtYen(tag === 'buy' ? t.buy_upper : t.definitely_buy)})` });
      }
    });
    return out.sort((a, b) => a.rank - b.rank);
  }

  function renderSignals(cards) {
    const el = document.getElementById('signals');
    const snaps = state.manifest.snapshots || [];
    const isLatest = state.currentIndex === snaps.length - 1;
    const signals = computeSignals(cards);
    // "NEW" = not shown on this browser's previous visit to the latest snapshot.
    const seen = new Set(store.get('psa10.seenSignals', []));
    const tracked = cards.filter((c) => lowestAsk(c) != null).length;

    if (!signals.length) {
      el.innerHTML = `<div class="signals-head">Buy signals</div><div class="signals-empty">None right now. No card is in a Buy zone or at your limit (${tracked} tracked).</div>`;
    } else {
      el.innerHTML = `<div class="signals-head">Buy signals</div>` + signals.map((s) => {
        const isNew = isLatest && !seen.has(s.key);
        const pill = s.kind === 'limit' ? '<span class="sig-pill limit">My limit</span>' : `<span class="vtag ${s.kind}">${escapeHtml(tagLabel(s.kind))}</span>`;
        return `<button type="button" class="signal" data-idx="${s.i}">${pill}<span class="sig-name">${escapeHtml(s.name)}</span><span class="sig-text">${escapeHtml(s.text)}</span>${isNew ? '<span class="sig-new">NEW</span>' : ''}</button>`;
      }).join('');
      el.querySelectorAll('.signal').forEach((b) => b.addEventListener('click', () => {
        const card = cards[Number(b.dataset.idx)];
        if (card) openCard(card);
      }));
    }
    if (isLatest) store.set('psa10.seenSignals', signals.map((s) => s.key));
  }

  // ---------- render: market strip ----------

  function renderMarketStrip(data) {
    const idx = data.pokeca_chart_index;
    if (!idx) { els.marketStrip.innerHTML = ''; return; }
    const psa10 = idx.psa10 || {};
    const raw = idx.raw_bihin || {};
    const mc = data.market_context || {};

    let fourthCell;
    if (mc.catalyst) {
      fourthCell = `<div class="cell"><div class="k">Catalyst</div><div class="v" style="font-size:1rem;">${escapeHtml(mc.catalyst)}</div></div>`;
    } else if (mc.psa_tier_status && (mc.psa_tier_status.note || mc.psa_tier_status.paused != null)) {
      const pts = mc.psa_tier_status;
      fourthCell = `<div class="cell"><div class="k">PSA value tier</div><div class="v" style="font-size:1rem;">${pts.paused ? 'Paused' : 'Active'}</div><div class="d">${escapeHtml(pts.note || '')}</div></div>`;
    } else {
      fourthCell = `<div class="cell"><div class="k">PSA10 momentum</div><div class="v">${fmtPct(psa10.month_change_pct)}</div><div class="d">month · ${fmtPct(psa10.year_change_pct)} year</div></div>`;
    }

    els.marketStrip.innerHTML = `
      <div class="cell">
        <div class="k">PSA10 index</div>
        <div class="v">${fmtYen(psa10.latest_index_value_jpy)}</div>
        <div class="d ${dirClass(psa10.day_change_pct)}">${fmtPct(psa10.day_change_pct)} day${asOfHtml(psa10.as_of)}</div>
      </div>
      <div class="cell">
        <div class="k">Raw A-rank index</div>
        <div class="v">${fmtYen(raw.latest_index_value_jpy)}</div>
        <div class="d ${dirClass(raw.day_change_pct)}">${fmtPct(raw.day_change_pct)} day${asOfHtml(raw.as_of)}</div>
      </div>
      <div class="cell">
        <div class="k">Both indices' volume</div>
        <div class="v" style="font-size:1rem; text-transform:capitalize;">${psa10.volume_trend || '—'}</div>
        <div class="d">vs raw: ${raw.volume_trend || '—'}</div>
      </div>
      ${fourthCell}
    `;
    const notes = [['PSA10 index volume', psa10.volume_note], ['Raw A-rank index volume', raw.volume_note]].filter((n) => n[1]);
    let mn = document.getElementById('market-notes');
    if (!mn) { mn = document.createElement('div'); mn.id = 'market-notes'; mn.className = 'market-notes'; els.marketStrip.after(mn); }
    mn.innerHTML = notes.map(([k, v]) => `<div class="panel"><div class="lbl">${escapeHtml(k)}</div><p>${escapeHtml(v)}</p></div>`).join('');
  }

  // ---------- render: banners (human-authored + auto-detected) ----------

  function computeAutoFlags(cards, prevData) {
    if (!prevData) return [];
    const prevCards = prevData.cards || [];
    const flags = [];
    cards.forEach((card) => {
      const prev = prevCards.find((c) => c.url === card.url);
      if (!prev) return;
      const psa10 = card.grades && card.grades.psa10;
      const prevPsa10 = prev.grades && prev.grades.psa10;
      if (psa10 && prevPsa10) {
        const prevD = depthInfo(prevPsa10);
        const curD = depthInfo(psa10);
        if (prevD.ratio > 0 && (curD.ratio - prevD.ratio) / prevD.ratio <= -0.3) {
          flags.push(`${card.card_name_ja}: listing depth dropped from ${prevD.within}/${prevD.total} to ${curD.within}/${curD.total}`);
        }
        const tiers = card.analysis && card.analysis.tiers;
        if (tiers) {
          const repPrev = getRep(prev);
          const repCur = getRep(card);
          if (repPrev != null && repCur != null) {
            const zPrev = zoneOf(tiers, repPrev);
            const zCur = zoneOf(tiers, repCur);
            if (zPrev !== zCur) {
              flags.push(`${card.card_name_ja}: price moved from ${zPrev} into ${zCur} territory (${fmtYen(repPrev)} → ${fmtYen(repCur)})`);
            }
          }
        }
      }
      if (card.favorite_count != null && prev.favorite_count) {
        const chg = ((card.favorite_count - prev.favorite_count) / prev.favorite_count) * 100;
        if (Math.abs(chg) >= 5) {
          flags.push(`${card.card_name_ja}: favorites ${chg > 0 ? 'up' : 'down'} ${Math.abs(chg).toFixed(1)}% (${prev.favorite_count.toLocaleString()} → ${card.favorite_count.toLocaleString()})`);
        }
      }
    });
    return flags;
  }

  function renderBanners(data, prevData) {
    let html = '';
    (data.banners || []).forEach((b) => {
      const cls = b.type === 'warning' ? 'warning' : b.type === 'correction' ? 'correction' : '';
      html += `<div class="banner ${cls}"><strong>${escapeHtml(b.title || '')}</strong>${escapeHtml(b.body || '')}</div>`;
    });
    const autoFlags = computeAutoFlags(data.cards || [], prevData);
    if (autoFlags.length) {
      html += `<div class="banner auto"><strong>Automatically detected since last snapshot</strong><ul>${autoFlags.map((f) => `<li>${escapeHtml(f)}</li>`).join('')}</ul></div>`;
    }
    els.banners.innerHTML = html;
  }

  // ---------- app shell: views + routing ----------
  // Hash routes: #/overview, #/collection, #/watching, #/holdings, #/planner,
  // #/record, #/market, #/tables, #/more (phone) and #/card/<snkrdunk id>.
  const VIEWS = {
    overview: 'Overview', collection: 'The collection', watching: 'Watching', holdings: 'Holdings',
    planner: 'Budget planner', record: 'Track record', market: 'Market & notes', tables: 'Tables', more: 'More', card: '',
  };
  const DESKTOP = window.matchMedia('(min-width: 1200px)');

  function cardId(card) { return (card.url || '').replace(/\/+$/, '').split('/').pop(); }
  function findCardById(id) { return ((state.currentData && state.currentData.cards) || []).find((c) => cardId(c) === id) || null; }
  function prevCardOf(card) { return ((state.previousData && state.previousData.cards) || []).find((c) => c.url === card.url) || null; }
  function hasMarket(card) { const p = card.grades && card.grades.psa10; return !!(p && p.lowest_price != null); }

  function parseRoute() {
    const [v, arg] = location.hash.replace(/^#\/?/, '').split('/');
    return { view: Object.prototype.hasOwnProperty.call(VIEWS, v) ? v : 'overview', arg: arg ? decodeURIComponent(arg) : null };
  }

  function applyRoute() {
    if (!state.currentData) return;
    const { view, arg } = parseRoute();
    document.querySelectorAll('.view').forEach((s) => { s.hidden = s.dataset.view !== view; });
    const navView = view === 'card' ? (state.cardFrom || 'overview') : view;
    document.querySelectorAll('#nav a, .tabbar a').forEach((a) => a.classList.toggle('on', a.dataset.view === navView));
    const tab = document.querySelector('.tabbar a[data-view="more"]');
    if (tab && ['watching', 'record', 'market', 'tables'].includes(view)) tab.classList.add('on');

    const back = document.getElementById('back-link');
    back.hidden = view !== 'card';
    let title = VIEWS[view];
    let sub = viewSubtitle(view);
    if (view === 'card') {
      const card = findCardById(arg);
      back.href = '#/' + (state.cardFrom || 'overview');
      back.querySelector('span').textContent = VIEWS[state.cardFrom || 'overview'];
      if (card) {
        const { short, code, pack } = parseCardName(card.card_name_ja);
        title = short; sub = [code, pack].filter(Boolean).join(' · ');
        renderCardPage(card);
      } else {
        title = 'Card not found'; sub = "This card isn't in the selected snapshot.";
        document.getElementById('card-page').innerHTML = '';
      }
    } else {
      state.cardFrom = view === 'more' ? 'overview' : view;
    }
    document.getElementById('page-title').textContent = title;
    document.getElementById('page-sub').textContent = sub;
    document.title = view === 'overview' ? 'PSA10 Tracker' : `${title} · PSA10 Tracker`;
  }

  function viewSubtitle(view) {
    const cards = (state.currentData && state.currentData.cards) || [];
    const market = cards.filter(hasMarket).length;
    const snap = state.manifest.snapshots[state.currentIndex] || {};
    const when = state.currentData ? fmtDateJST(state.currentData.collected_at_jst) : '';
    switch (view) {
      case 'overview': return `${market} cards with a PSA10 market · ${cards.length - market} watching · checked ${when}${snap.check_mode === 'quick' ? ' (quick)' : ''}`;
      case 'collection': return `${market} cards with a PSA10 market. Limit hits and Buy zones come first.`;
      case 'watching': return `${cards.length - market} cards without a PSA10 market yet. They move to the overview once PSA10 listings appear.`;
      case 'holdings': return 'Cards you bought, valued at today\'s price';
      case 'planner': return 'Tick cards to see what a shortlist costs against your budget';
      case 'record': return 'How past calls and stated odds turned out';
      case 'market': return `pokeca-chart indices · checked ${when}`;
      case 'tables': return 'Every tracked card side by side';
      default: return '';
    }
  }

  function openCard(card) {
    if (DESKTOP.matches && parseRoute().view === 'overview') {
      state.selectedUrl = card.url;
      renderOverviewList(state.currentData.cards || []);
      renderDrawer();
      return;
    }
    location.hash = '#/card/' + cardId(card);
  }

  function updateCounts() {
    const cards = (state.currentData && state.currentData.cards) || [];
    const market = cards.filter(hasMarket).length;
    const tr = state.calls && state.calls.summary;
    const counts = {
      collection: market || '', watching: (cards.length - market) || '', holdings: state.holdings.length || '',
      record: tr && tr.calls_scored ? `${(tr.calls || {}).right || 0}–${(tr.calls || {}).wrong || 0}` : '',
    };
    document.querySelectorAll('em[data-count]').forEach((em) => { em.textContent = counts[em.dataset.count] || ''; });
  }

  // ---------- render ----------

  function render() {
    const data = state.currentData;
    const cards = data.cards || [];
    const prevCards = (state.previousData && state.previousData.cards) || [];
    els.collectedAt.textContent = fmtDateJST(data.collected_at_jst);
    renderMarketStrip(data);
    renderKpis(data);
    renderSignals(cards);
    renderBanners(data, state.previousData);
    els.notesBody.textContent = data.notes || '';
    renderPortfolio(state.holdings, cards);
    renderOverviewList(cards);
    renderDrawer();
    renderCollection(cards);
    renderWatchPanel(cards.filter((c) => !hasMarket(c)), prevCards);
    renderPlanner(cards);
    renderTrackRecord();
    renderTables(cards, prevCards);
    updateCounts();
    applyRoute();
  }

  // Order used by the list and the display case: cards with a listing at or below
  // your limit first, then Definitely-buy / Buy zones, otherwise the snapshot's order.
  function sortedMarketCards(cards) {
    const rank = (c) => (limitHit(c) ? 0 : 3) + ({ definitely_buy: 0, buy: 1 }[displayTagFor(c)] ?? 2);
    return cards.filter(hasMarket).map((card, i) => ({ card, i })).sort((a, b) => rank(a.card) - rank(b.card) || a.i - b.i).map((x) => x.card);
  }

  // ---------- render: key numbers ----------

  function renderKpis(data) {
    const idx = data.pokeca_chart_index || {};
    const p = idx.psa10 || {}, r = idx.raw_bihin || {};
    const st = plannerState();
    const spent = state.holdings.reduce((a, h) => a + holdingCost(h), 0);
    const sm = state.calls && state.calls.summary;
    const c = (sm && sm.calls) || {};
    const chg = (x) => `<span class="${dirClass(x.day_change_pct)}">${fmtPct(x.day_change_pct)} day</span> · <span class="${dirClass(x.month_change_pct)}">${fmtPct(x.month_change_pct)} month</span>`;
    const tiles = [
      { href: '#/market', k: 'PSA10 index', v: fmtYen(p.latest_index_value_jpy), d: chg(p) },
      { href: '#/market', k: 'Raw A-rank index', v: fmtYen(r.latest_index_value_jpy), d: chg(r) },
      { href: '#/planner', k: 'Budget left', v: fmtYen(st.budget - spent), d: `of ${fmtYen(st.budget)} · ${fmtYen(spent)} spent` },
      { href: '#/record', k: 'Track record', v: sm && sm.calls_scored ? `${c.right || 0} right · ${c.wrong || 0} wrong` : '—',
        d: sm ? `${c.pending || 0} calls pending · ${sm.odds_open || 0} odds open` : 'no calls yet' },
    ];
    document.getElementById('kpis').innerHTML = tiles.map((t) =>
      `<a class="kpi" href="${t.href}"><span class="lbl">${escapeHtml(t.k)}</span><span class="kpi-v display">${escapeHtml(t.v)}</span><span class="kpi-d">${t.d}</span></a>`).join('');
  }

  // ---------- render: portfolio (cards you've actually bought) ----------

  function renderPortfolio(holdings, currentCards) {
    if (!holdings.length) {
      els.portfolioSummary.innerHTML = '';
      els.portfolioList.innerHTML = `<div class="empty-state">No purchases yet. Use <b>✓ Bought it</b> on a card to log one; it shows up here with its profit and loss.</div>`;
      return;
    }
    let totalCost = 0;
    let totalValue = 0;
    let matchedCount = 0;

    const rows = holdings.map((h) => {
      const match = currentCards.find((c) => c.url === h.card_url);
      const currentPrice = match ? getRep(match) : null;
      const cost = holdingCost(h);
      const pnl = currentPrice != null ? currentPrice - cost : null;
      const pnlPct = currentPrice != null && cost ? (pnl / cost) * 100 : null;
      if (currentPrice != null) {
        totalCost += cost;
        totalValue += currentPrice;
        matchedCount++;
      }
      return { h, match, currentPrice, cost, pnl, pnlPct };
    });

    if (matchedCount) {
      const totalPnl = totalValue - totalCost;
      const totalPnlPct = totalCost ? (totalPnl / totalCost) * 100 : null;
      els.portfolioSummary.innerHTML = `
        <div class="pf-stat"><div class="lbl">Total cost</div><div class="val">${fmtYen(totalCost)}</div></div>
        <div class="pf-stat"><div class="lbl">Current value</div><div class="val">${fmtYen(totalValue)}</div></div>
        <div class="pf-stat"><div class="lbl">Unrealized P&amp;L</div><div class="val ${totalPnl >= 0 ? 'pos' : 'neg'}">${totalPnl >= 0 ? '+' : '−'}${fmtYen(Math.abs(totalPnl))}${totalPnlPct != null ? ' (' + fmtPct(totalPnlPct) + ')' : ''}</div></div>
        ${matchedCount < holdings.length ? `<div class="pf-stat"><div class="lbl">Untracked</div><div class="val muted">${holdings.length - matchedCount} card${holdings.length - matchedCount === 1 ? '' : 's'}</div></div>` : ''}
      `;
    } else {
      els.portfolioSummary.innerHTML = `<div class="pf-stat"><div class="lbl">Status</div><div class="val muted">No current price data for any held card yet</div></div>`;
    }

    els.portfolioList.innerHTML = rows.map(({ h, match, currentPrice, pnl, pnlPct }) => {
      const displayName = match ? parseCardName(match.card_name_ja).short : parseCardName(h.card_name_ja || '').short;
      const imgSrc = (match && match.image_url) || h.image_url;
      const thumbHtml = imgSrc ? `<img src="${escapeAttr(imgSrc)}" alt="" loading="lazy" onerror="this.remove();">` : '';
      const costNote = h.condition === 'raw_to_grade' ? ' + grading' : '';
      const pnlHtml = pnl != null
        ? `<span class="${pnl >= 0 ? 'pos' : 'neg'}">${pnl >= 0 ? '+' : '−'}${fmtYen(Math.abs(pnl))}${pnlPct != null ? ' (' + fmtPct(pnlPct) + ')' : ''}</span>`
        : `<span class="muted">no current price</span>`;
      const nameHtml = match ? `<a href="#/card/${escapeAttr(cardId(match))}">${escapeHtml(displayName)}</a>` : escapeHtml(displayName);
      return `
        <div class="pf-row">
          <span class="pf-thumb">${thumbHtml}</span>
          <div class="pf-info">
            <div class="pf-name">${nameHtml}</div>
            <div class="pf-meta">Bought ${escapeHtml(h.purchase_date || '—')} for ${fmtYen(h.purchase_price_jpy)}${costNote}${h.notes ? ' · ' + escapeHtml(h.notes) : ''}${h.id ? ` · <a class="pf-remove" href="${escapeAttr(removeFormUrl(h))}" target="_blank" rel="noopener">Remove</a>` : ''}</div>
          </div>
          <div class="pf-current">
            <div class="val">${currentPrice != null ? fmtYen(currentPrice) : '—'}</div>
            <div class="pf-pnl">${pnlHtml}</div>
          </div>
        </div>`;
    }).join('');
  }

  // ---------- render: overview list + detail drawer ----------

  function zoneBarHtml(card, cls) {
    const a = card.analysis || {};
    const t = a.tiers, peak = a.peak && a.peak.price;
    if (!t) return `<span class="zb-none">no tiers yet</span>`;
    const scale = roundToThousand(Math.max(peak || 0, t.ceiling) * 1.08) || t.ceiling;
    const pct = (v) => Math.min(100, Math.max(0, (v / scale) * 100)).toFixed(1) + '%';
    const lim = getLimit(card);
    return `<span class="zb ${cls || ''}"><span class="zb-track"><i class="z-db" style="width:${pct(t.definitely_buy)}"></i><i class="z-bu" style="width:${pct(t.buy_upper - t.definitely_buy)}"></i><i class="z-w" style="width:${pct(t.ceiling - t.buy_upper)}"></i><i class="z-x"></i></span><span class="zb-now" style="left:${pct(getRep(card))}"></span>${lim != null ? `<span class="zb-lim" style="left:${pct(lim)}"></span>` : ''}</span>`;
  }

  function tagChip(card) {
    const tag = displayTagFor(card);
    return tag ? `<span class="vtag ${tag}">${escapeHtml(tagLabel(tag))}</span>` : `<span class="vtag none">No tiers</span>`;
  }

  function slabHtml(card, size) {
    const code = parseCardName(card.card_name_ja).code;
    const img = card.image_url ? `<img src="${escapeAttr(card.image_url)}" alt="" loading="lazy" onerror="this.remove()">` : '';
    return `<span class="slab ${size || ''}"><span class="slab-label"><b>${escapeHtml(code)}</b><b>GEM MT 10</b></span><span class="slab-art ${artClassFor(card)}">${img}</span></span>`;
  }

  function offPeakText(card) {
    const peak = card.analysis && card.analysis.peak;
    if (!peak || !peak.price) return '—';
    const pct = computeOffPeakPct(peak.price, getRep(card));
    return `${pct >= 0 ? '−' : '+'}${Math.abs(pct).toFixed(0)}%`;
  }

  function renderOverviewList(cards) {
    const el = document.getElementById('watchlist');
    const list = sortedMarketCards(cards);
    if (!list.length) { el.innerHTML = `<div class="empty-state">No cards with live market data in this snapshot yet.</div>`; return; }
    if (!state.selectedUrl || !list.some((c) => c.url === state.selectedUrl)) state.selectedUrl = list[0].url;
    el.innerHTML = list.map((card) => {
      const { short, code, pack } = parseCardName(card.card_name_ja);
      const owned = holdingsFor(card).length;
      return `<a class="wl-row${card.url === state.selectedUrl ? ' sel' : ''}${limitHit(card) ? ' hit' : ''}" href="#/card/${escapeAttr(cardId(card))}" data-url="${escapeAttr(card.url)}">
        ${slabHtml(card, 'xs')}
        <span class="wl-name"><b class="jp">${escapeHtml(short)}</b><small>${escapeHtml([code, pack].filter(Boolean).join(' · '))}</small></span>
        <span class="wl-price display">${fmtYen(getRep(card))}</span>
        ${zoneBarHtml(card)}
        <span class="wl-off">${offPeakText(card)}</span>
        <span class="wl-tag">${tagChip(card)}${owned ? '<span class="owned-chip">Owned</span>' : ''}${limitHit(card) ? '<span class="limit-chip">Limit</span>' : ''}</span>
      </a>`;
    }).join('');
    el.querySelectorAll('.wl-row').forEach((a) => a.addEventListener('click', (e) => {
      if (!DESKTOP.matches) return; // phones follow the link to the card page
      e.preventDefault();
      const card = cards.find((c) => c.url === a.dataset.url);
      if (card) openCard(card);
    }));
  }

  function renderDrawer() {
    const el = document.getElementById('drawer');
    const card = ((state.currentData && state.currentData.cards) || []).find((c) => c.url === state.selectedUrl);
    if (!card) { el.innerHTML = ''; return; }
    el.innerHTML = buildCardDetail(card, prevCardOf(card), 'drawer');
    wireCardDetail(el, card);
  }

  function renderCardPage(card) {
    const el = document.getElementById('card-page');
    el.innerHTML = buildCardDetail(card, prevCardOf(card), 'page');
    wireCardDetail(el, card);
  }

  // ---------- render: display case ----------

  function renderCollection(cards) {
    const el = document.getElementById('collection');
    const list = sortedMarketCards(cards);
    const reqEl = document.getElementById('card-requests');
    el.innerHTML = list.map((card) => {
      const { short, code } = parseCardName(card.card_name_ja);
      const lim = getLimit(card);
      const owned = holdingsFor(card).length;
      const pop = card.psa10_population != null ? card.psa10_population.toLocaleString() : '—';
      return `<a class="tile${limitHit(card) ? ' hit' : ''}" href="#/card/${escapeAttr(cardId(card))}">
        <span class="tile-slab">${slabHtml(card, 'lg')}
          <span class="tile-chips">${tagChip(card)}</span>
          ${lim != null ? `<span class="tile-limit">Limit ${fmtYen(lim)}</span>` : ''}
          ${owned ? '<span class="tile-owned">Owned</span>' : ''}
        </span>
        <span class="tile-name jp">${escapeHtml(short)}</span>
        <span class="tile-price"><b class="display">${fmtYen(getRep(card))}</b><span>${offPeakText(card)} off peak</span></span>
        ${zoneBarHtml(card, 'thin')}
        <span class="tile-meta">${escapeHtml(code)} · Pop ${pop}</span>
      </a>`;
    }).join('') + `<a class="tile tile-add" href="https://github.com/sprdl/psa10-tracker/issues/new?template=add-card.yml" target="_blank" rel="noopener"><span class="display">+</span>Add a card to track${reqEl && !reqEl.hidden ? `<small>${escapeHtml(reqEl.textContent)}</small>` : ''}</a>`;
  }

  function renderWatchPanel(pending, prevCards) {
    if (!pending.length) {
      els.watchPanel.innerHTML = `<div class="empty-state">Every tracked card has a PSA10 market.</div>`;
      return;
    }
    els.watchPanel.innerHTML = pending.map((card) => {
      const prev = prevCards.find((c) => c.url === card.url) || null;
      let status = 'first snapshot on file';
      if (prev) {
        if (prev.favorite_count != null && card.favorite_count != null && prev.favorite_count !== card.favorite_count) {
          status = card.favorite_count > prev.favorite_count ? 'favorites rising' : 'favorites falling';
        } else {
          status = 'still no market';
        }
      }
      const fav = card.favorite_count != null ? card.favorite_count.toLocaleString() : '—';
      const { short, code } = parseCardName(card.card_name_ja);
      const raw = card.grades && card.grades.raw_a_grade;
      const thumbHtml = card.image_url ? `<img src="${escapeAttr(card.image_url)}" alt="" loading="lazy" onerror="this.remove();">` : '';
      return `<a class="watch-row" href="${escapeAttr(card.url)}" target="_blank" rel="noopener">
        <span class="wthumb">${thumbHtml}</span>
        <span class="wname"><b class="jp">${escapeHtml(short || card.card_name_ja)}</b><small>${escapeHtml(code)}</small></span>
        <span class="wraw"><small>Raw A</small><b class="display">${raw && raw.lowest_price != null ? fmtYen(raw.lowest_price) : '—'}</b></span>
        <span class="wmeta">♥ ${fav}</span>
        <span class="wstate">${escapeHtml(status)}</span>
      </a>`;
    }).join('');
  }

  // ---------- card detail (drawer on desktop, full page on phones) ----------

  function buildCardDetail(card, prevCard, mode) {
    const psa10 = card.grades.psa10;
    const analysis = card.analysis || null;
    const repPrice = getRep(card);
    const depth = depthInfo(psa10);
    const { short: shortName, code, pack } = parseCardName(card.card_name_ja);

    let flagHtml = '';
    if (analysis && analysis.price_source) {
      const src = analysis.price_source;
      const cls = src === 'sales_confirmed' ? 'confirmed' : src === 'ask_depth' ? 'depth' : 'unconfirmed';
      const label = src === 'sales_confirmed' ? 'sales-confirmed' : src === 'ask_depth' ? 'ask depth' : src.replace(/_/g, ' ');
      flagHtml = `<span class="flag ${cls}">${label}</span>`;
    }

    const peak = analysis && analysis.peak;
    let offPeakHtml;
    if (peak && peak.price) {
      const pct = computeOffPeakPct(peak.price, repPrice);
      offPeakHtml = `<span class="pct">${pct >= 0 ? '−' : '+'}${Math.abs(pct).toFixed(0)}%</span> off the ${fmtYen(peak.price)} peak${peak.when ? ' (' + escapeHtml(peak.when) + ')' : ''}`;
    } else {
      offPeakHtml = 'No price history pulled yet, peak unknown';
    }

    let deltaHtml = '<span class="flat">first snapshot on file</span>';
    if (prevCard) {
      const prevRep = getRep(prevCard);
      if (prevRep != null && repPrice != null) {
        const diff = repPrice - prevRep;
        const pct = prevRep ? (diff / prevRep) * 100 : 0;
        if (diff === 0) deltaHtml = '<span class="flat">unchanged</span> since last check';
        else deltaHtml = `<span class="${diff > 0 ? 'up' : 'down'}">${diff > 0 ? '▲' : '▼'} ${fmtPct(pct)}</span> since last check (${fmtYen(prevRep)})`;
      }
    }

    const limit = getLimit(card);
    const ask = lowestAsk(card);
    const owned = holdingsFor(card);
    const ownedHtml = owned.length
      ? `<span class="owned-note">✓ Owned${owned.length > 1 ? ' ×' + owned.length : ''} · bought ${fmtYen(owned[owned.length - 1].purchase_price_jpy)}</span>`
      : '';
    const limitRowHtml = `<div class="limit-row">${limit != null
      ? `<span class="limit-lbl">My limit</span> <strong>${fmtYen(limit)}</strong>${limitHit(card)
          ? ` <span class="limit-hit-note">a listing is at or below it (${fmtYen(ask)})</span>`
          : (ask != null ? ` <span class="limit-gap">lowest ask is ${fmtYen(ask - limit)} above</span>` : '')}
         <span class="limit-actions"><button type="button" class="limit-btn" data-act="edit">Edit</button><button type="button" class="limit-btn" data-act="clear">Clear</button></span>`
      : `<button type="button" class="limit-btn" data-act="edit">+ Set my limit</button><span class="limit-gap">get a Buy signal when a listing drops to it</span>`}</div>`;

    let gaugeHtml = '';
    const edge = (pct) => (pct > 86 ? ' edge-r' : pct < 10 ? ' edge-l' : '');
    if (analysis && analysis.tiers && peak && peak.price) {
      const g = computeGauge(analysis.tiers, peak.price, repPrice);
      const t = analysis.tiers;
      if (g) {
        gaugeHtml = `
          <div class="gauge-wrap">
            <div class="gauge-track" data-scale="${g.scaleMax}" style="background: linear-gradient(to right,
                var(--green-strong) 0%, var(--green-strong) ${g.dbPct.toFixed(1)}%,
                var(--green) ${g.dbPct.toFixed(1)}%, var(--green) ${g.buPct.toFixed(1)}%,
                var(--amber) ${g.buPct.toFixed(1)}%, var(--amber) ${g.watchMidPct.toFixed(1)}%,
                var(--amber-strong) ${g.watchMidPct.toFixed(1)}%, var(--amber-strong) ${g.ceilPct.toFixed(1)}%,
                var(--red) ${g.ceilPct.toFixed(1)}%, var(--red) 100%);">
              <div class="marker${edge(g.curPct)}" style="left:${g.curPct.toFixed(1)}%"><div class="tag">${fmtYenShort(repPrice)}</div><div class="stem"></div></div>
              <div class="marker peak${edge(g.peakPct)}" style="left:${g.peakPct.toFixed(1)}%"><div class="tag">Peak ${fmtYenShort(peak.price)}</div><div class="stem"></div></div>
              ${limit != null ? `<div class="marker limit${edge((limit / g.scaleMax) * 100)}" style="left:${Math.min(100, Math.max(0, (limit / g.scaleMax) * 100)).toFixed(1)}%" title="Drag to adjust your limit"><div class="knob"></div><div class="tag">Limit ${fmtYenShort(limit)}</div></div>` : ''}
            </div>
            <div class="gauge-legend"><span><i class="z-db"></i>Def-buy ≤${fmtYenShort(t.definitely_buy)}</span><span><i class="z-bu"></i>Buy ≤${fmtYenShort(t.buy_upper)}</span><span><i class="z-w"></i>Watch ≤${fmtYenShort(t.ceiling)}</span><span><i class="z-x"></i>Don't buy</span></div>
          </div>`;
      }
    }

    let favHtml = card.favorite_count != null ? card.favorite_count.toLocaleString() : '—';
    if (prevCard && prevCard.favorite_count != null && card.favorite_count != null) {
      const fdiff = card.favorite_count - prevCard.favorite_count;
      if (fdiff !== 0) favHtml += ` <span class="${fdiff > 0 ? 'up' : 'down'}">${fdiff > 0 ? '▲' : '▼'}</span>`;
    }
    const raw = card.grades.raw_a_grade;
    const popText = `${card.psa10_population != null ? card.psa10_population.toLocaleString() : '—'}${card.psa10_gem_rate_pct != null ? ' · ' + card.psa10_gem_rate_pct + '%' : ''}`;
    const statsHtml = `
      <div class="cd-stats">
        <div class="cd-stat"><div class="lbl">Order-book depth</div><div class="val">${depth.within} / ${depth.total}${asOfHtml(psa10.listings_as_of)}</div><div class="depth-bar-track"><div class="depth-bar-fill" style="width:${Math.round(depth.ratio * 100)}%"></div></div></div>
        <div class="cd-stat"><div class="lbl">Recent sales</div><div class="val">${salesRangeText(psa10.recent_completed_sales)}</div></div>
        <div class="cd-stat"><div class="lbl">Favorites</div><div class="val">${favHtml}</div></div>
        <div class="cd-stat"><div class="lbl">Population · gem rate</div><div class="val">${popText}${card.population_as_of ? asOfHtml(card.population_as_of) : ''}</div></div>
        <div class="cd-stat"><div class="lbl">Raw A lowest</div><div class="val">${raw ? fmtYen(raw.lowest_price) : '—'}</div></div>
      </div>`;

    const displayTag = displayTagFor(card);
    let verdictHtml;
    if (analysis && analysis.verdict) {
      const v = analysis.verdict;
      const headline = verdictHeadline(v.label);
      const refP = analysis.representative_price != null ? analysis.representative_price : analysis.verdict_price_ref;
      // The pill shows the LIVE zone (price vs. tiers), which can differ from what the
      // written reasoning concluded; a zone mismatch is flagged first, then plain drift
      // from the price the verdict was written against (verdict_price_ref).
      let staleHtml = '';
      if (v.tag && v.tag !== 'defer' && displayTag && v.tag !== displayTag) {
        staleHtml = `<div class="verdict-stale">Price is now in the ${tagLabel(displayTag)} zone. The written analysis called it ${tagLabel(v.tag)}${refP != null ? ' at ' + fmtYen(refP) : ''}, worth a fresh look.</div>`;
      } else if (!analysis.price_source && analysis.verdict_price_ref != null && repPrice != null) {
        const ref = analysis.verdict_price_ref;
        const diffPct = ref ? ((repPrice - ref) / ref) * 100 : 0;
        if (Math.abs(diffPct) >= 5) {
          staleHtml = `<div class="verdict-stale">Last fully reviewed at ${fmtYen(ref)}. The price has since ${diffPct < 0 ? 'fallen' : 'risen'} to ${fmtYen(repPrice)} (${diffPct >= 0 ? '+' : '−'}${Math.abs(diffPct).toFixed(0)}%), worth a fresh look before trusting the call below.</div>`;
        }
      }
      verdictHtml = `<div class="verdict">${headline ? `<h3 class="verdict-head">${escapeHtml(headline)}</h3>` : ''}<p>${escapeHtml(v.reasoning || '')}</p>${staleHtml}</div>`;
    } else if (gaugeHtml) {
      verdictHtml = displayTag
        ? `<div class="verdict"><p>Zone computed from the live price vs. this card's tiers. No written analysis yet.</p></div>`
        : `<div class="tier-pending needs-review">Tiers carried forward from a previous check. This card hasn't had a verdict written for it yet.</div>`;
    } else {
      verdictHtml = `<div class="tier-pending">Tiers not yet established for this card, showing raw stats only.</div>`;
    }

    const rep = getRep(card);
    const diy = computeDiyEconomics(card, rep);
    const rt = analysis && analysis.raw_tiers;
    const diyHtml = diy ? `
      <div class="cd-stats">
        <div class="cd-stat"><div class="lbl">Buy the slab</div><div class="val">${fmtYen(rep)}</div></div>
        <div class="cd-stat"><div class="lbl">Raw A-rank</div><div class="val">${fmtYen(diy.rawPrice)}</div></div>
        <div class="cd-stat"><div class="lbl">Grade it yourself (expected)</div><div class="val">${fmtYen(diy.diyExpected)}</div></div>
        <div class="cd-stat"><div class="lbl">vs. buying the slab</div><div class="val ${diy.delta >= 0 ? 'neg' : 'pos'}">${diy.delta >= 0 ? '+' : '−'}${fmtYen(Math.abs(diy.delta))}</div></div>
      </div>
      <p class="cd-note">Expected DIY cost = (raw ¥${Math.round(diy.rawPrice).toLocaleString()} + grading ¥${diy.gradingFee.toLocaleString()} + shipping ¥${diy.shipping.toLocaleString()}) ÷ ${card.psa10_gem_rate_pct}% gem rate.</p>
      ${rt ? `<p class="cd-note">If buying raw anyway (as a PSA hedge, not a saving): definitely buy ≤${fmtYen(rt.definitely_buy)}, buy ≤${fmtYen(rt.buy_upper)}, don't pay over ${fmtYen(rt.ceiling)}.</p>` : ''}`
      : `<div class="tier-pending">No DIY grading analysis for this card yet.</div>`;

    const tabs = [['overview', 'Overview'], ['history', 'History'], ['listings', 'Listings'], ['diy', 'DIY']];
    const actionsHtml = `<div class="cd-actions">
          <a class="btn btn-primary" href="${escapeAttr(boughtFormUrl(card))}" target="_blank" rel="noopener" title="Log a purchase of this card">✓ Bought it</a>
          <a class="btn" href="${escapeAttr(card.url)}" target="_blank" rel="noopener">SNKRDUNK ↗</a>
        </div>`;
    const cur = state.cardTab || 'overview';
    const imgSize = mode === 'page' ? 'xl' : 'md';

    return `
      <div class="cd cd-${mode}" data-url="${escapeAttr(card.url)}">
        <div class="cd-hero">
          ${slabHtml(card, imgSize)}
          <div class="cd-info">
            ${mode === 'drawer' ? `<a class="cd-name jp" href="#/card/${escapeAttr(cardId(card))}">${escapeHtml(shortName)}</a><span class="cd-meta">${escapeHtml([code, pack].filter(Boolean).join(' · '))}</span>` : ''}
            <span class="cd-price display">${fmtYen(repPrice)}</span>
            <span class="cd-plabel">${analysis && analysis.representative_price != null ? 'representative PSA10' : 'lowest PSA10 ask'}${flagHtml}</span>
            <span class="cd-off">${offPeakHtml}</span>
            <span class="cd-delta">${deltaHtml}</span>
            <span class="cd-tags">${tagChip(card)}${ownedHtml}</span>
            ${mode === 'page' ? actionsHtml : ''}
          </div>
        </div>
        <div class="cd-tabs" role="tablist" aria-label="Card sections">
          ${tabs.map(([k, l]) => `<button type="button" role="tab" data-tab="${k}" aria-selected="${k === cur}">${l}</button>`).join('')}
        </div>
        <div class="cd-panel" data-panel="overview"${cur === 'overview' ? '' : ' hidden'}>
          ${gaugeHtml}
          ${limitRowHtml}
          ${verdictHtml}
          ${card.quick_note ? `<p class="cd-note">${escapeHtml(card.quick_note)}</p>` : ''}
          ${statsHtml}
        </div>
        <div class="cd-panel" data-panel="history"${cur === 'history' ? '' : ' hidden'}><div class="history-block"><div class="loading-inline">Loading full history…</div></div></div>
        <div class="cd-panel" data-panel="listings"${cur === 'listings' ? '' : ' hidden'}>${buildGradeDetail('PSA10', psa10)}${raw ? buildGradeDetail('Raw A-rank', raw) : ''}</div>
        <div class="cd-panel" data-panel="diy"${cur === 'diy' ? '' : ' hidden'}>${diyHtml}</div>
        ${mode === 'page' ? '' : actionsHtml}
      </div>`;
  }

  function wireCardDetail(el, card) {
    wireLimitControls(el, card);
    let historyLoaded = false;
    const showTab = (k) => {
      state.cardTab = k;
      el.querySelectorAll('.cd-tabs button').forEach((b) => b.setAttribute('aria-selected', String(b.dataset.tab === k)));
      el.querySelectorAll('.cd-panel').forEach((p) => { p.hidden = p.dataset.panel !== k; });
      if (k === 'history' && !historyLoaded) {
        historyLoaded = true;
        renderPriceHistoryInto(card, el.querySelector('.history-block'));
      }
    };
    el.querySelectorAll('.cd-tabs button').forEach((b) => b.addEventListener('click', () => showTab(b.dataset.tab)));
    if ((state.cardTab || 'overview') === 'history') showTab('history');
  }

  // ---------- budget planner (saved in this browser only) ----------
  // Tick cards to see what the shortlist costs against the budget, priced either at
  // today's lowest PSA10 ask (what a listing costs right now) or at your own limits.
  // Only cards with a live PSA10 market are listed — no-market cards can't be bought
  // graded yet.
  const PLANNER_KEY = 'psa10.planner';
  function plannerState() {
    const st = store.get(PLANNER_KEY, {});
    return { budget: typeof st.budget === 'number' ? st.budget : 200000,
             mode: st.mode === 'limits' ? 'limits' : 'today',
             selected: Array.isArray(st.selected) ? st.selected : [] };
  }

  function renderPlanner(cards) {
    const box = document.getElementById('planner');
    const st = plannerState();
    const rows = cards.filter((c) => lowestAsk(c) != null).map((card) => {
      const today = lowestAsk(card);
      const lim = getLimit(card);
      const useLimit = st.mode === 'limits' && lim != null;
      return { card, name: parseCardName(card.card_name_ja).short, today, lim,
               price: useLimit ? lim : today, fromLimit: useLimit,
               buyLine: card.analysis && card.analysis.tiers ? card.analysis.tiers.buy_upper : null,
               tag: displayTagFor(card), on: st.selected.includes(card.url) };
    });
    const picked = rows.filter((r) => r.on);
    const total = picked.reduce((a, r) => a + r.price, 0);
    const totalToday = picked.reduce((a, r) => a + r.today, 0);
    const spent = state.holdings.reduce((a, h) => a + holdingCost(h), 0);
    const ownedUrls = new Set(state.holdings.map((h) => h.card_url));
    const left = st.budget - spent - total;
    const missingLimit = st.mode === 'limits' ? picked.filter((r) => !r.fromLimit).length : 0;

    const summary = `
      <div class="pl-summary">
        <div class="pl-stat"><div class="lbl">Selected (${picked.length})</div><div class="val">${fmtYen(total)}</div></div>
        ${spent ? `<div class="pl-stat"><div class="lbl">Spent so far</div><div class="val">${fmtYen(spent)}</div></div>` : ''}
        <div class="pl-stat"><div class="lbl">Budget</div><div class="val"><span class="pl-yen">¥</span><input type="number" class="pl-budget" inputmode="numeric" step="10000" min="0" value="${st.budget}"></div></div>
        <div class="pl-stat"><div class="lbl">${left >= 0 ? 'Left' : 'Over budget'}</div><div class="val ${left >= 0 ? 'pos' : 'neg'}">${fmtYen(Math.abs(left))}</div></div>
        ${st.mode === 'limits' && picked.length ? `<div class="pl-stat"><div class="lbl">vs. buying today</div><div class="val ${totalToday - total >= 0 ? 'pos' : 'neg'}">${totalToday - total >= 0 ? 'saves ' : 'costs '}${fmtYen(Math.abs(totalToday - total))}</div></div>` : ''}
      </div>
      <div class="pl-bar">${spent ? `<div class="pl-bar-spent" style="width:${Math.min(100, st.budget ? (spent / st.budget) * 100 : 0).toFixed(1)}%" title="Spent so far"></div>` : ''}<div class="pl-bar-fill ${left < 0 ? 'over' : ''}" style="width:${Math.min(100, st.budget ? (total / st.budget) * 100 : 0).toFixed(1)}%"></div></div>`;

    const toggle = `
      <div class="pl-mode" role="group" aria-label="Price basis">
        <button type="button" data-mode="today" class="${st.mode === 'today' ? 'on' : ''}">Today's prices</button>
        <button type="button" data-mode="limits" class="${st.mode === 'limits' ? 'on' : ''}">My limits</button>
      </div>
      ${missingLimit ? `<div class="pl-note">${missingLimit} selected card${missingLimit === 1 ? ' has' : 's have'} no limit set, so ${missingLimit === 1 ? 'it uses' : 'they use'} today's price.</div>` : ''}`;

    const list = rows.map((r) => {
      const fits = !r.on && !ownedUrls.has(r.card.url) && r.price <= left;
      const sub = [`today ${fmtYen(r.today)}`, r.lim != null ? `limit ${fmtYen(r.lim)}` : 'no limit', r.buyLine != null ? `Buy ≤${fmtYen(r.buyLine)}` : null].filter(Boolean).join(' · ');
      return `<label class="pl-row ${r.on ? 'on' : ''}">
        <input type="checkbox" data-url="${escapeAttr(r.card.url)}" ${r.on ? 'checked' : ''}>
        <span class="pl-name">${escapeHtml(r.name)}${r.tag ? ` <span class="vtag ${r.tag}">${escapeHtml(tagLabel(r.tag))}</span>` : ''}${ownedUrls.has(r.card.url) ? ' <span class="pl-owned">owned</span>' : ''}</span>
        <span class="pl-price">${fmtYen(r.price)}${st.mode === 'limits' ? `<span class="pl-src">${r.fromLimit ? 'my limit' : 'today'}</span>` : ''}</span>
        <span class="pl-sub">${escapeHtml(sub)}${fits ? ' <span class="pl-fits">fits</span>' : ''}</span>
      </label>`;
    }).join('');

    box.innerHTML = rows.length
      ? toggle + summary + `<div class="pl-list">${list}</div>`
      : '<div class="empty-state">No cards with a PSA10 market in this snapshot.</div>';

    const save = (patch) => { store.set(PLANNER_KEY, Object.assign(plannerState(), patch)); renderPlanner(cards); renderKpis(state.currentData); };
    box.querySelectorAll('.pl-mode button').forEach((b) => b.addEventListener('click', () => save({ mode: b.dataset.mode })));
    box.querySelectorAll('.pl-row input[type=checkbox]').forEach((cb) => cb.addEventListener('change', () => {
      const sel = new Set(plannerState().selected);
      if (cb.checked) sel.add(cb.dataset.url); else sel.delete(cb.dataset.url);
      save({ selected: [...sel] });
    }));
    const bud = box.querySelector('.pl-budget');
    if (bud) bud.addEventListener('change', () => { const v = Number(bud.value); save({ budget: v >= 0 ? v : 0 }); });
  }

  // ---------- track record: how past calls and stated odds turned out ----------
  // Everything is computed by scripts/build_calls.py when a check is published;
  // this only displays data/calls.json.
  const TR_STATUS = {
    right: ['Right', 'pos'], wrong: ['Wrong', 'neg'], neutral: ['Neutral', 'muted'], pending: ['Pending', 'pend'],
    unscored: ['Not scored', 'muted'], yes: ['Happened', 'pos'], no: ["Didn't happen", 'neg'],
    open: ['Open', 'pend'], void: ['Void', 'muted'],
  };
  function trPill(status) {
    const [label, cls] = TR_STATUS[status] || [status, 'muted'];
    return `<span class="tr-pill ${cls}">${escapeHtml(label)}</span>`;
  }
  function trPct(n) { return n == null ? '—' : (Math.abs(n) < 0.05 ? '±0%' : fmtPct(n)); }
  function trDate(iso) { const d = (iso || '').slice(5, 10).split('-'); return d.length === 2 ? `${+d[0]}/${+d[1]}` : '—'; }

  function renderTrackRecord() {
    const sec = document.getElementById('track');
    const tr = state.calls;
    if (!tr || !(tr.calls || []).length) { sec.innerHTML = '<div class="empty-state">No calls recorded yet. The track record fills in as evaluations are published.</div>'; return; }
    const sm = tr.summary || {};
    const c = sm.calls || {};
    const win = tr.window_days || 30, th = Math.round((tr.threshold || 0.05) * 100);
    const brier = sm.brier != null
      ? `<div class="pl-stat"><div class="lbl">Odds accuracy (Brier)</div><div class="val ${sm.brier <= 0.2 ? 'pos' : sm.brier > 0.25 ? 'neg' : ''}">${sm.brier.toFixed(2)}</div><div class="tr-hint">0 = perfect · 0.25 = always saying 50%</div></div>
         <div class="pl-stat"><div class="lbl">Expected vs happened</div><div class="val">${sm.expected_yes} vs ${sm.actual_yes}</div><div class="tr-hint">of ${sm.odds_resolved} resolved</div></div>`
      : `<div class="pl-stat"><div class="lbl">Stated odds</div><div class="val muted">${sm.odds_open || 0} open</div><div class="tr-hint">none resolved yet</div></div>`;
    const headline = sm.calls_scored
      ? `${c.right || 0} right · ${c.wrong || 0} wrong${c.neutral ? ` · ${c.neutral} neutral` : ''}`
      : 'no calls scored yet';

    const callRows = tr.calls.map((k) => {
      const name = parseCardName(k.name).short;
      const so = k.status === 'pending'
        ? `day ${k.days_in}/${win} · low so far ${k.low != null ? fmtYen(k.low) + ' (' + trPct(k.low_pct) + ')' : '—'} · now ${k.now != null ? fmtYen(k.now) + ' (' + trPct(k.now_pct) + ')' : '—'}`
        : escapeHtml(k.why);
      return `<div class="tr-row">
        <div class="tr-main"><span class="tr-name">${escapeHtml(name)}</span> <span class="vtag ${k.tag}">${escapeHtml(tagLabel(k.tag))}</span>
          <span class="tr-meta">${trDate(k.made)} at ${fmtYen(k.price)}${k.reaffirmed ? ` · reaffirmed ${k.reaffirmed}×` : ''}</span></div>
        <div class="tr-res">${trPill(k.status)}</div>
        <div class="tr-sub">${escapeHtml(k.label || '')}<br>${so}</div>
      </div>`;
    }).join('');

    const predRows = (tr.predictions || []).map((p) => {
      const name = parseCardName(p.name).short;
      const detail = p.status === 'open'
        ? `now ${p.now != null ? fmtYen(p.now) : '—'}${p.gap_pct != null ? ` · needs ${trPct(p.gap_pct)}` : ''} · ${escapeHtml(p.why)}`
        : escapeHtml(p.why);
      return `<div class="tr-row">
        <div class="tr-main"><span class="tr-odds">${Math.round(p.p * 100)}%</span> <span class="tr-name">${escapeHtml(name)}</span>
          <span class="tr-meta">${p.type === 'touch_below' ? '≤' : '≥'}${fmtYen(p.price)} by ${trDate(p.by)}</span></div>
        <div class="tr-res">${trPill(p.status)}</div>
        <div class="tr-sub">${escapeHtml(p.text)} (said ${trDate(p.made)})<br>${detail}</div>
      </div>`;
    }).join('');

    sec.innerHTML = `
        <div class="pl-summary">
          <div class="pl-stat"><div class="lbl">Buy / Watch calls</div><div class="val">${escapeHtml(headline)}</div><div class="tr-hint">${c.pending || 0} still inside their ${win}-day window</div></div>
          ${brier}
        </div>
        <h3 class="tr-h">Calls</h3>
        <div class="tr-list">${callRows}</div>
        ${predRows ? `<h3 class="tr-h">Stated odds</h3><div class="tr-list">${predRows}</div>` : ''}
        <p class="tr-note">How it's scored: each change of verdict is one call, measured on the lowest PSA10 ask over the next ${win} days.
          A <b>Buy</b> is wrong if the price drops more than ${th}% below the call price (you could have bought cheaper), otherwise right.
          A <b>Watch</b> is right if it drops more than ${th}% (waiting paid off), wrong if it ends more than ${th}% higher without a dip, otherwise neutral.
          Stated odds are checked against their deadline; the Brier score rewards odds that match how often things actually happen.
          Updated with every price check (as of ${escapeHtml(fmtDateShort(tr.as_of))}).</p>`;
  }

  // Limit controls in a card detail (drawer or card page). Clicks stop propagating
  // so nothing around them reacts; every change re-renders the whole app.
  function wireLimitControls(article, card) {
    const row = article.querySelector('.limit-row');
    const stop = (e) => e.stopPropagation();
    row.addEventListener('click', stop);

    row.addEventListener('click', (e) => {
      const btn = e.target.closest('.limit-btn');
      if (!btn) return;
      if (btn.dataset.act === 'clear') { setLimit(card, null); render(); return; }
      if (btn.dataset.act === 'edit') openLimitEditor(row, card);
    });

    const marker = article.querySelector('.marker.limit');
    const track = article.querySelector('.gauge-track');
    if (!marker || !track) return;
    const wrap = article.querySelector('.gauge-wrap');
    wrap.addEventListener('click', stop);
    const scale = Number(track.dataset.scale);
    const priceAt = (clientX) => {
      const r = track.getBoundingClientRect();
      const pct = Math.min(1, Math.max(0, (clientX - r.left) / r.width));
      return Math.max(LIMIT_STEP, Math.round((pct * scale) / LIMIT_STEP) * LIMIT_STEP);
    };
    let dragging = false, value = getLimit(card);
    marker.addEventListener('pointerdown', (e) => {
      e.preventDefault(); e.stopPropagation();
      dragging = true; marker.setPointerCapture(e.pointerId); marker.classList.add('dragging');
    });
    marker.addEventListener('pointermove', (e) => {
      if (!dragging) return;
      value = priceAt(e.clientX);
      marker.style.left = ((value / scale) * 100).toFixed(1) + '%';
      marker.querySelector('.tag').textContent = 'Limit ' + fmtYenShort(value);
    });
    const end = (e) => {
      if (!dragging) return;
      dragging = false; marker.classList.remove('dragging');
      setLimit(card, value); render();
    };
    marker.addEventListener('pointerup', end);
    marker.addEventListener('pointercancel', end);
  }

  function openLimitEditor(row, card) {
    const t = card.analysis && card.analysis.tiers;
    const start = getLimit(card) || (t && t.buy_upper) || lowestAsk(card) || '';
    row.innerHTML = `<span class="limit-lbl">My limit</span> ¥<input type="number" class="limit-input" inputmode="numeric" min="${LIMIT_STEP}" step="${LIMIT_STEP}" value="${start}">
      <button type="button" class="limit-btn primary" data-act="save">Save</button><button type="button" class="limit-btn" data-act="cancel">Cancel</button>
      <span class="limit-hint">${t ? `Buy line is ${fmtYen(t.buy_upper)}. ` : ''}Rounded to ¥${LIMIT_STEP}; drag the gold handle on the bar to fine-tune.</span>`;
    const input = row.querySelector('.limit-input');
    input.focus(); input.select();
    const save = () => { const v = Number(input.value); if (v > 0) setLimit(card, v); render(); };
    row.querySelector('[data-act="save"]').addEventListener('click', (e) => { e.stopPropagation(); save(); });
    row.querySelector('[data-act="cancel"]').addEventListener('click', (e) => { e.stopPropagation(); render(); });
    input.addEventListener('keydown', (e) => { if (e.key === 'Enter') save(); if (e.key === 'Escape') render(); });
  }

  // ---------- price history (across every snapshot on file, not just this one) ----------

  // Bounds the worst-case fetch volume as the archive grows over months/years of
  // 2x/day checks — plenty of runway for a multi-month trend without ever
  // downloading the entire history on every card expand.
  const HISTORY_MAX_SNAPSHOTS = 200;
  let historySnapshotsPromise = null;

  function loadAllSnapshotsForHistory() {
    if (historySnapshotsPromise) return historySnapshotsPromise;
    const snaps = state.manifest.snapshots || [];
    const capped = snaps.length > HISTORY_MAX_SNAPSHOTS ? snaps.slice(snaps.length - HISTORY_MAX_SNAPSHOTS) : snaps;
    historySnapshotsPromise = Promise.all(
      capped.map((s) => fetchJSON('data/snapshots/' + s.file).catch(() => null))
    ).then((results) => results.filter(Boolean));
    return historySnapshotsPromise;
  }

  // Preferred source: data/history.json, a compact per-card series rebuilt by
  // scripts/build_history.py on every publish, so expanding a card downloads one
  // small file instead of every snapshot. Falls back to the per-snapshot method
  // below if the index is missing.
  let historyIndexPromise = null;
  function loadHistoryIndex() {
    if (!historyIndexPromise) historyIndexPromise = fetchJSON('data/history.json').catch(() => null);
    return historyIndexPromise;
  }

  async function getCardPriceHistory(card) {
    const idx = await loadHistoryIndex();
    if (idx && Array.isArray(idx.snapshots)) {
      const pts = [];
      idx.snapshots.forEach((s) => {
        const v = s.p && s.p[card.url];
        if (v) pts.push({ date: s.d, price: v[0], confirmed: !!v[1] });
      });
      pts.sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0));
      return pts;
    }
    const allSnaps = await loadAllSnapshotsForHistory();
    const points = [];
    allSnaps.forEach((snap) => {
      const c = (snap.cards || []).find((x) => x.url === card.url);
      if (!c) return;
      const psa10 = c.grades && c.grades.psa10;
      if (!psa10 || psa10.lowest_price == null) return;
      const price = getRep(c);
      if (price == null) return;
      points.push({
        date: snap.collected_at_jst,
        price,
        confirmed: !!(c.analysis && c.analysis.price_source === 'sales_confirmed'),
      });
    });
    points.sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0));
    return points;
  }

  async function renderPriceHistoryInto(card, container) {
    if (!container) return;
    const points = await getCardPriceHistory(card);
    container.innerHTML = buildPriceHistoryHtml(card, points);
  }

  // A long-run line chart of representative_price across every snapshot the
  // card appears in, distinct from the short-window "recent sales" sparkline
  // above (which only covers one snapshot's own recent_completed_sales). This
  // is the view for judging progress against a months-long thesis, not a
  // single check.
  function buildPriceHistoryHtml(card, points) {
    if (points.length < 2) {
      return `<div class="lbl">Price history</div><div class="hist-empty">Not enough history yet — this builds up as you run more price checks.</div>`;
    }

    const prices = points.map((p) => p.price);
    let lo = Math.min(...prices);
    let hi = Math.max(...prices);
    const tiers = card.analysis && card.analysis.tiers;
    if (tiers) {
      lo = Math.min(lo, tiers.definitely_buy);
      hi = Math.max(hi, tiers.ceiling);
    }
    const pad = (hi - lo) * 0.1 || hi * 0.1 || 1000;
    lo = Math.max(0, lo - pad);
    hi = hi + pad;
    const range = hi - lo || 1;

    const w = 700, h = 160, padX = 4, padTop = 10, padBottom = 10;
    const plotH = h - padTop - padBottom;
    const step = (w - padX * 2) / (points.length - 1);
    const y = (price) => padTop + plotH - ((price - lo) / range) * plotH;
    const pts = points.map((p, i) => [padX + i * step, y(p.price)]);

    const trendUp = prices[prices.length - 1] > prices[0];
    const color = trendUp ? 'var(--red)' : 'var(--green-strong)';
    const gradId = 'hist-grad-' + (sparkGradCounter++);
    const linePath = smoothPath(pts);
    const baseline = h - padBottom;
    const last = pts[pts.length - 1];
    const areaPath = `${linePath} L${last[0].toFixed(1)},${baseline} L${pts[0][0].toFixed(1)},${baseline} Z`;

    const dots = points.map((p, i) => {
      const [px, py] = pts[i];
      return `<circle cx="${px.toFixed(1)}" cy="${py.toFixed(1)}" r="${p.confirmed ? 2.6 : 2}" fill="${p.confirmed ? color : 'var(--muted-2)'}" />`;
    }).join('');

    let refLines = '';
    if (tiers) {
      const refLine = (price, cls, label) => `
        <line x1="${padX}" y1="${y(price).toFixed(1)}" x2="${w - padX}" y2="${y(price).toFixed(1)}" class="hist-ref-line ${cls}" />
        <text x="${w - padX}" y="${(y(price) - 4).toFixed(1)}" class="hist-ref-label ${cls}" text-anchor="end">${label}</text>`;
      refLines = refLine(tiers.definitely_buy, 'db', 'Definitely-buy')
        + refLine(tiers.buy_upper, 'bu', 'Buy')
        + refLine(tiers.ceiling, 'ceil', "Don't-buy");
    }

    const svg = `<svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none">
      <defs>
        <linearGradient id="${gradId}" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="${color}" stop-opacity="0.3"/>
          <stop offset="100%" stop-color="${color}" stop-opacity="0"/>
        </linearGradient>
      </defs>
      ${refLines}
      <path d="${areaPath}" fill="url(#${gradId})" />
      <path d="${linePath}" fill="none" stroke="${color}" stroke-width="2" />
      ${dots}
    </svg>`;

    const dateLabels = `<div class="spark-dates"><span>${escapeHtml(fmtDateShort(points[0].date))}</span><span>${escapeHtml(fmtDateShort(points[points.length - 1].date))}</span></div>`;
    const note = tiers
      ? `<div class="hist-note">Dashed lines are today's tiers, shown for reference — they may not have applied at every point in the past.</div>`
      : '';

    return `<div class="lbl">Price history — ${points.length} checks, ${escapeHtml(fmtDateShort(points[0].date))} → ${escapeHtml(fmtDateShort(points[points.length - 1].date))}</div>${svg}${dateLabels}${note}`;
  }

  function buildGradeDetail(label, grade) {
    const listings = grade.top20_cheapest_listings || [];
    const sales = grade.recent_completed_sales || [];
    const distribution = buildDistribution(grade, listings);
    const sparkline = buildSparkline(sales);
    const salesList = sales.slice().reverse().map((s) => `<li><span>${fmtYen(s.price)}</span><span class="when">${escapeHtml(s.when)}</span></li>`).join('');

    const note = grade.note ? `<div class="raw-note">${escapeHtml(grade.note)}</div>` : '';

    return `
      <div class="detail-grade">
        <h3>${label} <span class="grade-pill">${listings.length} live listings sampled</span></h3>
        ${note}
        <div class="detail-row">
          <div><div class="stat-label">Lowest ask</div><div class="stat-value">${fmtYen(grade.lowest_price)}</div></div>
          <div><div class="stat-label">+15% threshold</div><div class="stat-value">${fmtYen(grade.threshold_115pct_of_lowest)}</div></div>
          <div><div class="stat-label">Within 15%</div><div class="stat-value">${grade.count_within_15pct}</div></div>
          <div><div class="stat-label">Excluded (over 15%)</div><div class="stat-value">${grade.count_excluded_over_15pct}</div></div>
        </div>
        ${distribution}
        ${sales.length ? sparkline : ''}
        ${sales.length ? `<ul class="sales-list">${salesList}</ul>` : ''}
      </div>
    `;
  }

  // Distribution strip: a real histogram of the sampled listing prices, bucketed
  // across their own min–max range, replacing the old 20-chip grid. Computed
  // entirely client-side from top20_cheapest_listings / threshold_115pct_of_lowest
  // — no new fields required in the JSON.
  function buildDistribution(grade, listings) {
    if (!listings.length) return '';
    const sorted = listings.slice().sort((a, b) => a - b);
    const min = sorted[0], max = sorted[sorted.length - 1];
    const threshold = grade.threshold_115pct_of_lowest;
    const range = max - min || 1;
    const bins = Math.min(14, sorted.length);
    const binWidth = range / bins || 1;
    const counts = new Array(bins).fill(0);
    sorted.forEach((p) => {
      let idx = Math.floor((p - min) / binWidth);
      if (idx >= bins) idx = bins - 1;
      if (idx < 0) idx = 0;
      counts[idx]++;
    });
    const maxCount = Math.max(...counts, 1);
    const bars = counts.map((c, idx) => {
      if (!c) return '';
      const leftPct = ((idx + 0.5) / bins) * 100;
      const heightPct = Math.max(16, (c / maxCount) * 100);
      const binPrice = min + (idx + 0.5) * binWidth;
      const within = threshold != null ? binPrice <= threshold : true;
      return `<div class="dist-bar ${within ? 'in' : ''}" style="left:${leftPct.toFixed(1)}%; height:${heightPct.toFixed(0)}%;"></div>`;
    }).join('');

    return `
      <div class="distribution">
        <div class="lbl">Listing distribution (${listings.length} sampled${threshold != null ? `, lowest → +15% cutoff at ${fmtYen(threshold)}` : ''})</div>
        <div class="dist-track">${bars}</div>
        <div class="dist-range"><span>${fmtYen(min)} lowest</span><span>${fmtYen(max)}</span></div>
      </div>`;
  }

  let sparkGradCounter = 0;

  // Smoothed (Catmull-Rom → cubic Bezier) sales sparkline with a gradient area
  // fill, generalized for any real recent_completed_sales array (1..N points) —
  // oldest first, matching the order the JSON already provides.
  function buildSparkline(sales) {
    if (!sales.length) return '';
    const prices = sales.map((s) => s.price);
    const w = 500, h = 90, padX = 4, padTop = 14, padBottom = 18;
    const min = Math.min(...prices), max = Math.max(...prices);
    const range = max - min || 1;
    const plotH = h - padTop - padBottom;
    const step = prices.length > 1 ? (w - padX * 2) / (prices.length - 1) : 0;
    const pts = prices.map((p, i) => [
      padX + i * step,
      padTop + plotH - ((p - min) / range) * plotH,
    ]);

    const trendUp = prices[prices.length - 1] > prices[0];
    const color = trendUp ? 'var(--red)' : 'var(--green-strong)';
    const gradId = 'spark-grad-' + (sparkGradCounter++);
    const linePath = pts.length > 1 ? smoothPath(pts) : `M${pts[0][0]},${pts[0][1]} L${pts[0][0]},${pts[0][1]}`;
    const baseline = h - padBottom;
    const last = pts[pts.length - 1];
    const areaPath = `${linePath} L${last[0].toFixed(1)},${baseline} L${pts[0][0].toFixed(1)},${baseline} Z`;

    const svg = `<svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none">
      <defs>
        <linearGradient id="${gradId}" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="${color}" stop-opacity="0.35"/>
          <stop offset="100%" stop-color="${color}" stop-opacity="0"/>
        </linearGradient>
      </defs>
      <path d="${areaPath}" fill="url(#${gradId})" />
      <path d="${linePath}" fill="none" stroke="${color}" stroke-width="2" />
      <circle cx="${last[0].toFixed(1)}" cy="${last[1].toFixed(1)}" r="3.5" fill="${color}" />
    </svg>`;

    const dateLabels = `<div class="spark-dates"><span>${escapeHtml(sales[0].when)} · ${fmtYen(sales[0].price)}</span><span>${escapeHtml(sales[sales.length - 1].when)} · ${fmtYen(sales[sales.length - 1].price)}</span></div>`;

    return `<div class="spark-block"><div class="lbl">Sales history — ${escapeHtml(sales[0].when)} → ${escapeHtml(sales[sales.length - 1].when)}</div>${svg}${dateLabels}</div>`;
  }

  function smoothPath(pts) {
    if (pts.length === 2) return `M${pts[0][0].toFixed(1)},${pts[0][1].toFixed(1)} L${pts[1][0].toFixed(1)},${pts[1][1].toFixed(1)}`;
    let d = `M${pts[0][0].toFixed(1)},${pts[0][1].toFixed(1)} `;
    for (let i = 0; i < pts.length - 1; i++) {
      const p0 = pts[i - 1] || pts[i];
      const p1 = pts[i];
      const p2 = pts[i + 1];
      const p3 = pts[i + 2] || p2;
      const cp1x = p1[0] + (p2[0] - p0[0]) / 6;
      const cp1y = p1[1] + (p2[1] - p0[1]) / 6;
      const cp2x = p2[0] - (p3[0] - p1[0]) / 6;
      const cp2y = p2[1] - (p3[1] - p1[1]) / 6;
      d += `C${cp1x.toFixed(1)},${cp1y.toFixed(1)} ${cp2x.toFixed(1)},${cp2y.toFixed(1)} ${p2[0].toFixed(1)},${p2[1].toFixed(1)} `;
    }
    return d.trim();
  }

  // ---------- render: tables ----------

  function renderTables(cards, prevCards) {
    const validCards = cards.filter((c) => c.grades && c.grades.psa10 && c.grades.psa10.lowest_price != null);

    const diySection = document.getElementById('diy-table-section');
    const diyTableEl = document.getElementById('diy-table');
    const withDiy = validCards.map((c) => {
      const rep = getRep(c);
      const diy = computeDiyEconomics(c, rep);
      return diy ? { card: c, repPrice: rep, diy } : null;
    }).filter(Boolean);
    const diyHtml = buildDiyTable(withDiy);
    if (diyHtml) { diyTableEl.innerHTML = diyHtml; diySection.hidden = false; }
    else { diySection.hidden = true; }

    const cmpSection = document.getElementById('comparison-table-section');
    const cmpTableEl = document.getElementById('comparison-table');
    const cmpHtml = buildComparisonTable(validCards, prevCards);
    if (cmpHtml) { cmpTableEl.innerHTML = cmpHtml; cmpSection.hidden = false; }
    else { cmpSection.hidden = true; }
  }

  function buildDiyTable(entries) {
    if (!entries.length) return null;
    const thead = '<thead><tr><th></th>' + entries.map((e) => `<th>${escapeHtml(e.card.card_name_ja)}</th>`).join('') + '</tr></thead>';

    let rows = '';
    rows += '<tr><td>Buy the slab (PSA10)</td>' + entries.map((e) => `<td>${fmtYen(e.repPrice)}${e.card.analysis && e.card.analysis.price_source === 'sales_confirmed' ? ' <em>(sales-confirmed)</em>' : ''}</td>`).join('') + '</tr>';
    rows += '<tr><td>Buy raw A-rank</td>' + entries.map((e) => `<td>${fmtYen(e.diy.rawPrice)}</td>`).join('') + '</tr>';
    rows += '<tr><td>Raw + grade it yourself (expected cost)</td>' + entries.map((e) => `<td>${fmtYen(e.diy.diyExpected)}</td>`).join('') + '</tr>';
    rows += '<tr><td>vs. just buying the slab</td>' + entries.map((e) => `<td>${e.diy.delta >= 0 ? '+' : '−'}${fmtYen(Math.abs(e.diy.delta))}</td>`).join('') + '</tr>';

    const anyRawTiers = entries.some((e) => e.card.analysis && e.card.analysis.raw_tiers);
    if (anyRawTiers) {
      rows += `<tr class="divider"><td colspan="${entries.length + 1}">If buying raw anyway — as a PSA hedge, not a saving</td></tr>`;
      rows += '<tr><td>Raw: definitely buy</td>' + entries.map((e) => { const t = e.card.analysis.raw_tiers; return `<td>${t ? '≤' + fmtYen(t.definitely_buy) : '—'}</td>`; }).join('') + '</tr>';
      rows += '<tr><td>Raw: buy</td>' + entries.map((e) => { const t = e.card.analysis.raw_tiers; return `<td>${t ? fmtYen(t.definitely_buy) + '–' + fmtYen(t.buy_upper) : '—'}</td>`; }).join('') + '</tr>';
      rows += "<tr><td>Raw: don't-buy ceiling</td>" + entries.map((e) => { const t = e.card.analysis.raw_tiers; return `<td>${t ? fmtYen(t.ceiling) : '—'}</td>`; }).join('') + '</tr>';
    }

    return thead + '<tbody>' + rows + '</tbody>';
  }

  function buildComparisonTable(cards, prevCards) {
    if (!cards.length) return null;
    const thead = '<thead><tr><th></th>' + cards.map((c) => `<th>${escapeHtml(c.card_name_ja)}</th>`).join('') + '</tr></thead>';

    const rowsData = [
      ['Current PSA10', cards.map((c) => {
        const rep = getRep(c);
        const confirmed = c.analysis && c.analysis.price_source === 'sales_confirmed';
        return fmtYen(rep) + (confirmed ? ' (sales-confirmed)' : '');
      })],
      ['Order-book depth', cards.map((c) => { const d = depthInfo(c.grades.psa10); return `${d.within}/${d.total}`; })],
      ['Sales window range', cards.map((c) => salesRangeText(c.grades.psa10.recent_completed_sales))],
      ['Favorite count', cards.map((c) => {
        const prev = prevCards.find((p) => p.url === c.url);
        let s = c.favorite_count != null ? c.favorite_count.toLocaleString() : '—';
        if (prev && prev.favorite_count != null && c.favorite_count != null && prev.favorite_count !== c.favorite_count) {
          s += c.favorite_count > prev.favorite_count ? ' ↑' : ' ↓';
        }
        return s;
      })],
      ['Population / gem rate', cards.map((c) => `${c.psa10_population != null ? c.psa10_population.toLocaleString() : '—'} · ${c.psa10_gem_rate_pct != null ? c.psa10_gem_rate_pct + '%' : '—'}`)],
      ['Off peak (where known)', cards.map((c) => {
        const peak = c.analysis && c.analysis.peak;
        if (peak && peak.price) {
          const rep = getRep(c);
          const pct = computeOffPeakPct(peak.price, rep);
          return `${pct >= 0 ? '−' : '+'}${Math.abs(pct).toFixed(0)}% (${fmtYen(peak.price)}${peak.when ? ', ' + escapeHtml(peak.when) : ''})`;
        }
        return 'unknown — no history';
      })],
    ];

    let body = rowsData.map(([label, vals]) => `<tr><td>${label}</td>${vals.map((v) => `<td>${v}</td>`).join('')}</tr>`).join('');

    body += `<tr class="divider"><td colspan="${cards.length + 1}">PSA10 price tiers</td></tr>`;
    const tierRow = (label, fn) => `<tr><td>${label}</td>${cards.map((c) => { const t = c.analysis && c.analysis.tiers; return `<td>${t ? fn(t) : 'Not yet established'}</td>`; }).join('')}</tr>`;
    body += tierRow('Definitely-buy', (t) => '≤' + fmtYen(t.definitely_buy));
    body += tierRow('Buy', (t) => fmtYen(t.definitely_buy) + '–' + fmtYen(t.buy_upper));
    body += tierRow('Watch closely', (t) => fmtYen(t.buy_upper) + '–' + fmtYen(t.ceiling));
    body += tierRow("Don't-buy ceiling", (t) => fmtYen(t.ceiling));

    body += `<tr><td>Verdict</td>${cards.map((c) => {
      const tag = displayTagFor(c);
      if (tag) {
        return `<td><span class="pill ${tag}">${escapeHtml(tagLabel(tag))}</span></td>`;
      }
      return '<td>—</td>';
    }).join('')}</tr>`;

    return thead + '<tbody>' + body + '</tbody>';
  }

  // Pending "Add card" requests (open GitHub issues labeled add-card). Public,
  // unauthenticated read; if GitHub is unreachable or rate-limited, show nothing.
  async function loadCardRequests() {
    const el = document.getElementById('card-requests');
    if (!el) return;
    try {
      const r = await fetch('https://api.github.com/repos/sprdl/psa10-tracker/issues?state=open&per_page=50',
        { headers: { Accept: 'application/vnd.github+json' } });
      if (!r.ok) return;
      const issues = (await r.json()).filter((i) => !i.pull_request);
      const has = (i, name) => (i.labels || []).some((l) => l.name === name);
      const cards = issues.filter((i) => has(i, 'add-card')).length;
      // Purchases are handled by GitHub Actions within a minute or so; one still open
      // after 5 minutes couldn't be read and has a comment saying what to fix.
      const buys = issues.filter((i) => has(i, 'bought') || has(i, 'remove-purchase'));
      const stuck = buys.filter((i) => Date.now() - new Date(i.updated_at).getTime() > 5 * 60e3);
      const parts = [];
      if (cards) parts.push(escapeHtml(`${cards} card request${cards === 1 ? '' : 's'} waiting for the next price check`));
      if (buys.length - stuck.length) parts.push('Recording a purchase… reload in a minute');
      if (stuck.length) parts.push(`<a href="${escapeAttr(stuck[0].html_url)}" target="_blank" rel="noopener">A purchase couldn't be recorded. See why ↗</a>`);
      if (!parts.length) return;
      [el, document.getElementById('card-requests-m')].forEach((x) => { if (x) { x.innerHTML = parts.join(' · '); x.hidden = false; } });
      if (state.currentData) renderCollection(state.currentData.cards || []);
    } catch (e) { /* offline or blocked — the button still works */ }
  }

  init();
  loadCardRequests();
})();

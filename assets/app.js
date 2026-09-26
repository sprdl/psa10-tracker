(function () {
  'use strict';

  const state = {
    manifest: null,
    currentIndex: -1, // index into manifest.snapshots (chronological ascending)
    currentData: null,
    previousData: null,
    calls: null, // data/calls.json — track record of past calls (scripts/build_calls.py)
    oddsModel: null, // data/odds_model.json — odds of a listing reaching a price
    syncedLimits: {}, // data/limits.json — limits saved for every device
    hist: null, // data/history.json — per-card price series + when each card's tiers were last reviewed
    customIndex: null, // data/custom_index.json — My-tier index (scripts/add_custom_index.py)
    events: null, // data/events.json — release calendar for the event rule (scripts/events.py)
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
    try { state.customIndex = await fetchJSON('data/custom_index.json'); } catch (e) { state.customIndex = null; }
    try { state.events = await fetchJSON('data/events.json'); } catch (e) { state.events = null; }
    state.hist = await loadHistoryIndex();
    try { state.syncedLimits = (await fetchJSON('data/limits.json')).limits || {}; } catch (e) { state.syncedLimits = {}; }
    try { state.oddsModel = await fetchJSON('data/odds_model.json'); } catch (e) { state.oddsModel = null; }
    reconcileLimits();
    initSortUi();

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
  // Correction rule: while the market is still falling (see correctionState), a
  // price in the Buy zone shows as Watch; only Definitely-buy stays a buy.
  function displayTagFor(card) {
    const a = card.analysis;
    if (!a) return null;
    const written = a.verdict && a.verdict.tag;
    if (written === 'defer') return 'defer';
    const live = liveTagOf(a.tiers, getRep(card));
    if (live === 'buy' && (correctionState().active || eventFor(card))) return 'watch';
    return live || written || null;
  }

  // ---------- event rule ----------
  // Same as the card-evaluation skill: within window_days before a major release or
  // announcement (and on the day itself), a Buy-zone price shows as Watch. An event's
  // scope is "all" or a list of set codes (the first part of the card code, e.g. M6a).
  // Undated (rumoured) events are listed but never applied.
  function todayJst() { return new Date(Date.now() + 9 * 3600000).toISOString().slice(0, 10); }
  function daysUntil(d) { return Math.round((Date.parse(d + 'T00:00:00Z') - Date.parse(todayJst() + 'T00:00:00Z')) / 86400000); }
  function eventWindow() { return (state.events && state.events.window_days) || 3; }
  function upcomingEvents() {
    const evs = (state.events && state.events.events) || [];
    return evs.filter((e) => !e.d || daysUntil(e.d) >= 0)
      .sort((a, b) => (a.d ? 0 : 1) - (b.d ? 0 : 1) || String(a.d).localeCompare(String(b.d)));
  }
  function eventApplies(e, card) {
    if (!e.scope || e.scope === 'all') return true;
    const set = (parseCardName(card.card_name_ja).code.split(/\s+/)[0] || '').toLowerCase();
    return e.scope.some((x) => String(x).toLowerCase() === set);
  }
  function activeEvents() {
    return upcomingEvents().filter((e) => e.d && e.major !== false && daysUntil(e.d) <= eventWindow());
  }
  function eventFor(card) { return activeEvents().find((e) => eventApplies(e, card)) || null; }
  function eventWhen(e) {
    if (!e.d) return e.when || 'date TBA';
    const n = daysUntil(e.d);
    return `${e.d.slice(5).replace('-', '/')} (${n === 0 ? 'today' : n === 1 ? 'tomorrow' : 'in ' + n + ' days'})`;
  }
  function eventScope(e) { return !e.scope || e.scope === 'all' ? 'all cards' : e.scope.join(', ') + ' cards'; }

  // True when the card's price is in the Buy zone but the event rule holds it at Watch.
  function heldByEvent(card) {
    const a = card.analysis;
    return !!(a && a.tiers && (!a.verdict || a.verdict.tag !== 'defer')
      && liveTagOf(a.tiers, getRep(card)) === 'buy' && eventFor(card));
  }

  function renderEvents() {
    const el = document.getElementById('events-panel');
    if (!el) return;
    const up = upcomingEvents();
    if (!up.length) { el.hidden = true; return; }
    el.hidden = false;
    const win = eventWindow();
    el.innerHTML = `<h2 class="section-title">Release calendar</h2>
      <p class="ci-note">Event rule: in the ${win} days before a major release (and on the day), Buy-zone prices show as Watch until it's out. Rumoured dates are listed but don't trigger the rule. Edited with scripts/events.py.</p>
      <ul class="ev-list">${up.map((e) => {
        const on = e.d && e.major !== false && daysUntil(e.d) <= win;
        return `<li class="${on ? 'on' : ''}${e.d ? '' : ' tba'}"><span class="ev-when">${escapeHtml(eventWhen(e))}</span>
          <span class="ev-name">${escapeHtml(e.name)}</span>
          <span class="ev-meta">${escapeHtml(eventScope(e))}${e.major === false ? ' · minor' : ''}${on ? ' · <b>rule on</b>' : ''}${e.note ? ' · ' + escapeHtml(e.note) : ''}</span></li>`;
      }).join('')}</ul>`;
  }

  // True when the card's price is in the Buy zone but the correction rule holds it at Watch.
  function heldByCorrection(card) {
    const a = card.analysis;
    return !!(a && a.tiers && (!a.verdict || a.verdict.tag !== 'defer')
      && liveTagOf(a.tiers, getRep(card)) === 'buy' && correctionState().active);
  }

  // Correction rule (same as the card-evaluation skill): the market counts as still
  // correcting while the My-tier index is down more than CORRECTION_PCT over 30 days.
  // Until the My-tier index has 30 days of data, the pokeca-chart PSA10 index's
  // month change is used instead.
  const CORRECTION_PCT = 10;
  let correctionCache = null;
  function correctionState() {
    const key = (state.currentData && state.currentData.collected_at_jst) || '';
    if (correctionCache && correctionCache.key === key) return correctionCache.v;
    let v = { active: false, pct: null, name: null };
    const ref = key || new Date().toISOString();
    const ser = (state.customIndex && state.customIndex.series) || [];
    const day = ref.slice(0, 10);
    const past = new Date(Date.parse(day + 'T00:00:00Z') - 30 * 86400000).toISOString().slice(0, 10);
    let now = null, then = null;
    for (const e of ser) { if (e.d <= day) now = e; if (e.d <= past) then = e; }
    if (now && then) {
      const pct = (now.level / then.level - 1) * 100;
      v = { active: pct <= -CORRECTION_PCT, pct, name: 'My-tier index' };
    } else {
      const m = (((state.currentData || {}).pokeca_chart_index || {}).psa10 || {}).month_change_pct;
      if (m != null) v = { active: m <= -CORRECTION_PCT, pct: m, name: 'PSA10 index' };
    }
    correctionCache = { key, v };
    return v;
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
  // Limits live in two places: data/limits.json (saved through a GitHub issue form,
  // the same on every device) and this browser's own edits (`limits`, 0 = cleared
  // here). A local edit wins until the synced file catches up, then it's dropped.
  let limits = store.get('psa10.limits', {});
  const LIMIT_STEP = 500;
  function syncedLimit(url) {
    const e = state.syncedLimits && state.syncedLimits[url];
    return e && typeof e.price === 'number' ? e.price : null;
  }
  function reconcileLimits() {
    let changed = false;
    Object.keys(limits).forEach((url) => {
      const local = limits[url], synced = syncedLimit(url);
      if ((local === 0 && synced == null) || (local > 0 && local === synced)) { delete limits[url]; changed = true; }
    });
    if (changed) store.set('psa10.limits', limits);
  }
  function getLimit(card) {
    if (Object.prototype.hasOwnProperty.call(limits, card.url)) return limits[card.url] > 0 ? limits[card.url] : null;
    return syncedLimit(card.url);
  }
  // 'local' = changed on this device only (not saved to all devices yet), 'synced', or null (no limit anywhere).
  function limitSync(card) {
    if (Object.prototype.hasOwnProperty.call(limits, card.url)) return 'local';
    return syncedLimit(card.url) != null ? 'synced' : null;
  }
  function setLimit(card, v) {
    limits[card.url] = v == null ? 0 : Math.max(LIMIT_STEP, Math.round(v / LIMIT_STEP) * LIMIT_STEP);
    store.set('psa10.limits', limits);
    reconcileLimits();
  }
  function limitFormUrl(card) {
    const v = getLimit(card);
    const q = new URLSearchParams({ template: 'set-limit.yml',
      title: `Limit: ${parseCardName(card.card_name_ja).short} ${v ? '¥' + v.toLocaleString('en-US') : '(remove)'}`,
      url: card.url, limit: String(v || 0) });
    return `${REPO_URL}/issues/new?${q}`;
  }

  // ---------- odds of a listing reaching a price ----------
  // Model in data/odds_model.json (see its "about"): zero drift, the card's own
  // volatility from ~2 years of pokeca-chart PSA10 prices shrunk toward the pool of
  // 125 modern cards, and empirical z-curves instead of a normal curve, so fat tails
  // are kept. Backtested out of sample on 2024–26 data; trend/momentum made it worse.
  function oddsModelCode(card) {
    const m = state.oddsModel;
    if (!m) return null;
    const code = (parseCardName(card.card_name_ja).code || '').toLowerCase().trim();
    if (m.cards[code]) return code;
    const promo = code.match(/^([a-z]+-p)\s+(\d+)$/);             // "sv-p 098" -> "098/sv-p"
    if (promo && m.cards[`${promo[2]}/${promo[1]}`]) return `${promo[2]}/${promo[1]}`;
    return null;
  }
  function zShare(qs, z) {                                          // share of history at or below z
    if (z <= qs[0]) return 0;
    const n = qs.length - 1;
    if (z >= qs[n]) return 1;
    let i = 0; while (i < n && qs[i + 1] < z) i++;
    const f = (z - qs[i]) / ((qs[i + 1] - qs[i]) || 1);
    return (i + f) / n;
  }
  function touchOdds(card, price) {
    const S = lowestAsk(card), m = state.oddsModel;
    if (!S || !price) return null;
    if (price >= S) return { reached: true };
    if (!m) return null;
    const code = oddsModelCode(card);
    const [s30, s90, nOwn] = code ? m.cards[code] : [m.pool_sigma[0], m.pool_sigma[1], 0];
    const x = Math.log(price / S), cap = m.about.cap || 0.99;
    const p30 = Math.min(cap, m.about.touch_factor_30 * zShare(m.z_end30, x / s30));
    const p90 = Math.max(p30, Math.min(cap, m.about.touch_factor_90 * zShare(m.z_touch90, x / s90)));
    return { p30, p90, own: !!code && nOwn >= 4, s30, drop: -x };
  }
  function fmtOdds(x) { return x < 0.05 ? '<5%' : x > 0.95 ? '>95%' : '~' + Math.round(x * 20) * 5 + '%'; }
  // The evaluation's own stated odds for a nearby price, as a cross-check.
  function evalOddsNear(card, price) {
    const preds = (((card.analysis || {}).verdict || {}).predictions || []).filter((q) => q.type === 'touch_below' && q.price && typeof q.p === 'number');
    if (!preds.length) return null;
    const best = preds.reduce((a, b) => (Math.abs(b.price - price) < Math.abs(a.price - price) ? b : a));
    return Math.abs(best.price - price) / price <= 0.07 ? best : null;
  }
  function limitOddsHtml(card, price) {
    const o = touchOdds(card, price);
    if (!o) return '';
    if (o.reached) return `<div class="limit-odds">A listing is already at or below ${fmtYen(price)}.</div>`;
    const ev = evalOddsNear(card, price);
    return `<div class="limit-odds">Chance a listing reaches ${fmtYen(price)} (${Math.round(o.drop * 100)}% below today's lowest ask): <b>${fmtOdds(o.p30)}</b> within 30 days · <b>${fmtOdds(o.p90)}</b> within 90 days
      <span class="limit-odds-note">${o.own ? `From this card's own price swings over the last months` : `This card has no pokeca-chart history, so it uses the typical swings of modern PSA10s`}, calibrated on ~2 years of prices for 125 modern PSA10s and tested on 2024–26 data. It assumes no trend, because trend and momentum made the backtest worse.${ev ? ` The written evaluation said ${Math.round(ev.p * 100)}% for ≤${fmtYen(ev.price)} by ${escapeHtml(ev.by)}.` : ''}</span></div>`;
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
      el.innerHTML = `<div class="signals-head">Buy signals</div><div class="signals-empty">None right now. ${correctionState().active || activeEvents().length ? `No card is at Definitely-buy or your limit (${correctionState().active ? 'correction' : 'event'} rule on; Buy-zone cards count as Watch)` : 'No card is in a Buy zone or at your limit'} (${tracked} tracked).</div>`;
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

  // ---------- render: My-tier index (data/custom_index.json) ----------
  // Equal-weighted index of the tier actually being bought; base date = 100.
  // Everything shown is computed here from the stored prices and base prices.

  function customIndexStats() {
    const ci = state.customIndex;
    const ser = (ci && ci.series) || [];
    if (!ser.length) return null;
    const last = ser[ser.length - 1];
    const before = (days) => {
      const t = new Date(last.d + 'T00:00:00+09:00').getTime() - days * 86400000;
      let hit = null;
      for (const e of ser) if (new Date(e.d + 'T00:00:00+09:00').getTime() <= t) hit = e;
      return hit;
    };
    const pct = (e) => (e && e !== last ? (last.level / e.level - 1) * 100 : null);
    return { ci, ser, last, day: pct(ser.length > 1 ? ser[ser.length - 2] : null), week: pct(before(7)), month: pct(before(30)) };
  }


  function renderCustomIndex() {
    let el = document.getElementById('custom-index');
    if (!el) return;
    const st = customIndexStats();
    if (!st) { el.hidden = true; return; }
    el.hidden = false;
    const { ci, ser, last } = st;
    const meta = ci.meta || {};
    // pokeca-chart line is rebased to 100 on the index's base day (not the first back value)
    const base = ser.find((e) => e.d === meta.base_date && e.pokeca_psa10) || [...ser].reverse().find((e) => e.pokeca_psa10) || null;
    const cell = (k, v, cls) => `<div class="ci-stat"><div class="lbl">${k}</div><div class="ci-v ${cls || ''}">${v}</div></div>`;
    const since = last.level - (meta.base_level || 100);
    const pokecaRel = (e) => (base && e.pokeca_psa10 ? (e.pokeca_psa10 / base.pokeca_psa10) * 100 : null);
    const pk = pokecaRel(last);
    const firstReal = ser.find((e) => !e.backfill);
    const bf = meta.backfill && ser[0].backfill ? meta.backfill : null;

    // chart: my-tier level vs pokeca-chart PSA10 index (both 100 on the base day); x axis is time,
    // so monthly back values and daily readings sit at their real dates
    const RANGES = [['3M', 92], ['1Y', 366], ['All', 0]];
    const rng = store.get('psa10.ciRange', '1Y');
    const span = (RANGES.find((r) => r[0] === rng) || RANGES[1])[1];
    const tOf = (e) => Date.parse(e.d + 'T00:00:00Z');
    const tLast = tOf(last);
    const view = span ? ser.filter((e) => tOf(e) >= tLast - span * 86400000) : ser;
    let chart = '';
    if (view.length >= 2) {
      chart = `<figure class="ci-fig">
        <figcaption class="ci-cap"><span class="ci-cap-t">My-tier index vs pokeca-chart PSA10 index</span>
          <span class="ci-cap-s">Both indexed to 100 on ${escapeHtml(base ? base.d : meta.base_date || '')} · hover or tap for values</span></figcaption>
        <div class="ci-plot" tabindex="0" role="img" aria-label="Line chart of the My-tier index and the pokeca-chart PSA10 index, ${escapeHtml(view[0].d)} to ${escapeHtml(last.d)}. Use the arrow keys to step through the values."></div>
        <div class="ci-legend"><span class="ci-key ci-key-me"></span>My tier <span class="ci-key ci-key-pk"></span>pokeca-chart PSA10 (100 on ${escapeHtml(base ? base.d : '')})${view[0].backfill && firstReal ? ' <span class="ci-key-bf"></span>backfilled from per-card charts' : ''}</div>
      </figure>`;
    } else {
      chart = `<p class="ci-note">Chart appears after the second daily reading.</p>`;
    }
    const rangeBtns = `<div class="ci-range" role="group" aria-label="Chart range">${RANGES.map(([k]) =>
      `<button type="button" class="ci-rng${k === rng ? ' on' : ''}" data-rng="${k}" aria-pressed="${k === rng}">${k}</button>`).join('')}</div>`;
    const bfNote = bf ? ` Values before ${escapeHtml(firstReal ? firstReal.d : '')} are backfilled from pokeca-chart's per-card PSA10 charts (month-end points until Jul 2026, daily after; a card counts ${bf.join_days || 90} days after its first price; fewer cards before Mar 2026).` : '';

    const rows = (meta.constituents || []).map((c) => {
      const p = last.prices && last.prices[c.code];
      const ch = p != null ? (p / c.base - 1) * 100 : null;
      return { c, p, ch, carried: (last.carried || []).includes(c.code) };
    }).sort((a, b) => (a.ch ?? 1e9) - (b.ch ?? 1e9));
    const table = `<details class="ci-members"><summary>${rows.length} cards · weakest first</summary>
      <div class="table-scroll"><table><thead><tr><th>Card</th><th>Code</th><th>Base</th><th>Now</th><th>vs base</th></tr></thead><tbody>
      ${rows.map(({ c, p, ch, carried }) => `<tr><td>${escapeHtml(c.name)}</td><td>${escapeHtml(c.code)}</td><td>${fmtYen(c.base)}</td>
        <td>${fmtYen(p)}${carried ? ' <span class="muted">(carried)</span>' : ''}</td><td class="${dirClass(ch)}">${fmtPct(ch)}</td></tr>`).join('')}
      </tbody></table></div></details>`;

    el.innerHTML = `
      <h2 class="section-title">My-tier index</h2>
      <p class="ci-note">${escapeHtml(meta.selection || '')} Base ${escapeHtml(meta.base_date || '')} = ${meta.base_level || 100}. Updated once a day with the full check.${bfNote}</p>
      <div class="ci-stats">
        ${cell('Level · ' + escapeHtml(last.d), last.level.toFixed(2))}
        ${cell('Day', fmtPct(st.day), dirClass(st.day))}
        ${cell('7 days', fmtPct(st.week), dirClass(st.week))}
        ${cell('30 days', fmtPct(st.month), dirClass(st.month))}
        ${cell('Since base', fmtPct(since), dirClass(since))}
        ${cell('pokeca idx since base', fmtPct(pk != null ? pk - 100 : null), dirClass(pk != null ? pk - 100 : null))}
      </div>
      ${rangeBtns}
      ${chart}
      ${table}`;
    el.querySelectorAll('[data-rng]').forEach((b) => b.addEventListener('click', () => { store.set('psa10.ciRange', b.dataset.rng); renderCustomIndex(); }));
    const plot = el.querySelector('.ci-plot');
    if (plot) drawIndexChart(plot, view, { base, firstReal, pokecaRel, baseLevel: meta.base_level || 100 });
  }

  // Time-based line chart with axes, gridlines and a hover/tap/keyboard crosshair.
  // Drawn at the container's real pixel width so text never stretches; redrawn on resize.
  let ciObserver = null;
  function drawIndexChart(box, view, o) {
    // hidden views have no width yet: redraw whenever the box's width changes (incl. first show)
    if (ciObserver) ciObserver.disconnect();
    if (window.ResizeObserver) {
      let lastW = box.clientWidth;
      ciObserver = new ResizeObserver(() => { const w = box.clientWidth; if (w && Math.abs(w - lastW) > 2) { lastW = w; drawIndexChart(box, view, o); } });
      ciObserver.observe(box);
    }
    if (!box.clientWidth) return;
    const W = Math.max(280, Math.round(box.clientWidth)), H = W < 520 ? 210 : 250;
    const m = { l: 46, r: 14, t: 12, b: 28 };
    const iw = W - m.l - m.r, ih = H - m.t - m.b;
    const tOf = (e) => Date.parse(e.d + 'T00:00:00Z');
    const t0 = tOf(view[0]), t1 = tOf(view[view.length - 1]);
    const pts = view.map((e) => ({ e, t: tOf(e), me: e.level, pk: o.pokecaRel(e) }));
    const vals = pts.flatMap((p) => [p.me, p.pk]).filter((v) => v != null).concat([100]);
    let lo = Math.min(...vals), hi = Math.max(...vals);
    // nice y ticks
    const span = hi - lo || 10, raw = span / 4, mag = Math.pow(10, Math.floor(Math.log10(raw)));
    const step = [1, 2, 2.5, 5, 10].map((k) => k * mag).find((k) => k >= raw) || 10 * mag;
    lo = Math.floor((lo - span * 0.04) / step) * step; hi = Math.ceil((hi + span * 0.04) / step) * step;
    const X = (t) => m.l + ((t - t0) * iw) / (t1 - t0 || 1);
    const Y = (v) => m.t + ih * (1 - (v - lo) / (hi - lo));
    const yTicks = []; for (let v = lo; v <= hi + 1e-9; v += step) yTicks.push(v);
    // x ticks: month starts, thinned to fit
    const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    const months = [];
    const d0 = new Date(t0); for (let y = d0.getUTCFullYear(), mo = d0.getUTCMonth() + 1; ; mo++) {
      if (mo === 12) { mo = 0; y++; } const t = Date.UTC(y, mo, 1); if (t > t1) break; months.push(t); }
    const every = Math.max(1, Math.ceil(months.length / Math.max(2, Math.floor(iw / 70))));
    const xTicks = months.filter((_, i) => i % every === 0);
    const fmtTick = (t) => { const d = new Date(t); return (d.getUTCMonth() === 0 || xTicks.length <= 4 || every >= 12) ? `${MON[d.getUTCMonth()]} ${String(d.getUTCFullYear()).slice(2)}` : MON[d.getUTCMonth()]; };
    const path = (k) => pts.filter((p) => p[k] != null).map((p, i) => `${i ? 'L' : 'M'}${X(p.t).toFixed(1)},${Y(p[k]).toFixed(1)}`).join(' ');
    const bfEnd = view[0].backfill && o.firstReal ? Math.min(X(tOf(o.firstReal)), m.l + iw) : null;
    box.innerHTML = `<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" aria-hidden="true">
      ${bfEnd != null && bfEnd > m.l ? `<rect x="${m.l}" y="${m.t}" width="${(bfEnd - m.l).toFixed(1)}" height="${ih}" class="ci-bf"/>` : ''}
      ${yTicks.map((v) => `<line x1="${m.l}" x2="${m.l + iw}" y1="${Y(v).toFixed(1)}" y2="${Y(v).toFixed(1)}" class="ci-grid"/><text x="${m.l - 8}" y="${(Y(v) + 4).toFixed(1)}" class="ci-ytick">${+v.toFixed(1)}</text>`).join('')}
      ${xTicks.map((t) => `<line x1="${X(t).toFixed(1)}" x2="${X(t).toFixed(1)}" y1="${m.t + ih}" y2="${m.t + ih + 4}" class="ci-axis"/><text x="${X(t).toFixed(1)}" y="${m.t + ih + 18}" class="ci-xtick">${fmtTick(t)}</text>`).join('')}
      <line x1="${m.l}" x2="${m.l + iw}" y1="${m.t + ih}" y2="${m.t + ih}" class="ci-axis"/>
      <line x1="${m.l}" x2="${m.l + iw}" y1="${Y(100).toFixed(1)}" y2="${Y(100).toFixed(1)}" class="ci-base"/>
      <text x="${m.l + iw}" y="${(Y(100) - 5).toFixed(1)}" class="ci-basel">100 = base</text>
      <path d="${path('pk')}" class="ci-line-pk"/>
      <path d="${path('me')}" class="ci-line"/>
      <g class="ci-hover" style="display:none">
        <line class="ci-cross" y1="${m.t}" y2="${m.t + ih}"/>
        <circle class="ci-dot-pk" r="4"/><circle class="ci-dot-me" r="4.5"/>
      </g>
    </svg><div class="ci-tip" role="status" aria-live="polite" hidden></div>`;
    const svg = box.querySelector('svg'), g = svg.querySelector('.ci-hover'), tip = box.querySelector('.ci-tip');
    const cross = g.querySelector('.ci-cross'), dm = g.querySelector('.ci-dot-me'), dp = g.querySelector('.ci-dot-pk');
    const fmtD = (d) => { const [y, mo, dd] = d.split('-'); return `${+dd} ${MON[+mo - 1]} ${y}`; };
    const pct = (v) => (v == null ? '' : ` <span class="${dirClass(v - o.baseLevel)}">(${fmtPct(v - o.baseLevel)} vs base)</span>`);
    let cur = -1;
    const show = (i) => {
      if (i < 0 || i >= pts.length) return;
      cur = i; const p = pts[i], x = X(p.t);
      g.style.display = ''; cross.setAttribute('x1', x); cross.setAttribute('x2', x);
      dm.setAttribute('cx', x); dm.setAttribute('cy', Y(p.me));
      if (p.pk != null) { dp.style.display = ''; dp.setAttribute('cx', x); dp.setAttribute('cy', Y(p.pk)); } else dp.style.display = 'none';
      const e = p.e;
      tip.innerHTML = `<div class="ci-tip-d">${fmtD(e.d)}${e.backfill ? ' · <span class="muted">backfilled' + (e.n ? `, ${e.n} cards` : '') + '</span>' : (e.n ? ` · <span class="muted">${e.n} cards</span>` : '')}</div>
        <div><span class="ci-key ci-key-me"></span>My tier <b>${e.level.toFixed(2)}</b>${pct(e.level)}</div>
        ${e.pokeca_psa10 ? `<div><span class="ci-key ci-key-pk"></span>PSA10 index <b>${fmtYen(e.pokeca_psa10)}</b>${p.pk != null ? ` <span class="muted">= ${p.pk.toFixed(1)}</span>` : ''}</div>` : '<div class="muted">PSA10 index: no value that day</div>'}`;
      tip.hidden = false;
      const tw = tip.offsetWidth, left = Math.min(Math.max(x - tw / 2, 0), W - tw);
      const topY = Math.min(Y(p.me), p.pk != null ? Y(p.pk) : Infinity);
      tip.style.left = left + 'px';
      tip.style.top = Math.max(0, topY - tip.offsetHeight - 12) + 'px';
    };
    const hide = () => { g.style.display = 'none'; tip.hidden = true; cur = -1; };
    const nearest = (clientX) => {
      const r = svg.getBoundingClientRect(); const t = t0 + ((clientX - r.left - m.l) / iw) * (t1 - t0);
      let best = 0; for (let i = 1; i < pts.length; i++) if (Math.abs(pts[i].t - t) < Math.abs(pts[best].t - t)) best = i;
      return best;
    };
    svg.addEventListener('pointermove', (ev) => show(nearest(ev.clientX)));
    svg.addEventListener('pointerdown', (ev) => show(nearest(ev.clientX)));
    svg.addEventListener('pointerleave', (ev) => { if (ev.pointerType === 'mouse') hide(); });
    box.addEventListener('keydown', (ev) => {
      if (ev.key === 'ArrowLeft' || ev.key === 'ArrowRight') { ev.preventDefault(); show(cur < 0 ? pts.length - 1 : cur + (ev.key === 'ArrowLeft' ? -1 : 1)); }
      else if (ev.key === 'Home') show(0); else if (ev.key === 'End') show(pts.length - 1); else if (ev.key === 'Escape') hide();
    });
    box.addEventListener('blur', hide);
  }


  // ---------- tier review status + card vs market ----------
  // Tiers are fixed yen amounts. They're flagged for review when they are more than
  // TIER_MAX_AGE_DAYS old, or when the market has moved TIER_MAX_INDEX_MOVE since
  // they were set (My-tier index if it existed then, else the pokeca-chart PSA10
  // index). The flag only asks for a human review; nothing moves the tiers itself.
  const TIER_MAX_AGE_DAYS = 30;
  const TIER_MAX_INDEX_MOVE = 10; // percent

  function refTime() { return (state.currentData && state.currentData.collected_at_jst) || new Date().toISOString(); }
  function daysBetween(a, b) { return (new Date(b) - new Date(a)) / 86400000; }

  function myTierAt(ts) {
    const ser = (state.customIndex && state.customIndex.series) || [];
    const day = ts.slice(0, 10);
    let hit = null;
    for (const e of ser) if (e.d <= day) hit = e;
    return hit;
  }
  function pokecaAt(ts) {
    const snaps = (state.hist && state.hist.snapshots) || [];
    let v = null;
    for (const e of snaps) if (e.d <= ts && e.i) v = e.i;
    return v;
  }

  // Market move between two times: My-tier index when it covers both, else pokeca PSA10.
  function marketMove(from, to, fromPokeca) {
    const a = myTierAt(from), b = myTierAt(to);
    if (a && b) return { pct: (b.level / a.level - 1) * 100, name: 'My-tier index' };
    const pa = fromPokeca || pokecaAt(from), pb = pokecaAt(to);
    if (pa && pb) return { pct: (pb / pa - 1) * 100, name: 'PSA10 index' };
    return null;
  }

  function tierReview(card) {
    const t = state.hist && state.hist.tiers && state.hist.tiers[card.url];
    if (!t || !(card.analysis && card.analysis.tiers)) return null;
    const now = refTime();
    const days = Math.max(0, daysBetween(t.since, now));
    const mv = marketMove(t.since, now, t.i);
    const reasons = [];
    if (days > TIER_MAX_AGE_DAYS) reasons.push(`over ${TIER_MAX_AGE_DAYS} days old`);
    if (mv && Math.abs(mv.pct) >= TIER_MAX_INDEX_MOVE) reasons.push(`market moved more than ${TIER_MAX_INDEX_MOVE}%`);
    return { since: t.since, days, move: mv, due: reasons.length > 0, reasons };
  }

  function tierReviewHtml(card) {
    const r = tierReview(card);
    if (!r) return '';
    const d = Math.floor(r.days);
    const age = d === 0 ? 'today' : d === 1 ? '1 day ago' : `${d} days ago`;
    const mv = r.move ? ` · ${escapeHtml(r.move.name)} <span class="${dirClass(r.move.pct)}">${fmtPct(r.move.pct)}</span> since` : '';
    return `<div class="tier-age${r.due ? ' due' : ''}">Tiers set ${escapeHtml(fmtDateShort(r.since).slice(0, 10))} (${age})${mv}${r.due
      ? ` · <b>Review due</b>: ${escapeHtml(r.reasons.join(', '))}`
      : ` · review due after ${TIER_MAX_AGE_DAYS} days or a ${TIER_MAX_INDEX_MOVE}% market move`}</div>`;
  }

  // Card price change vs the market over a window, from data/history.json.
  function cardPriceAt(card, ts) {
    const snaps = (state.hist && state.hist.snapshots) || [];
    let v = null;
    for (const e of snaps) if (e.d <= ts && e.p && e.p[card.url]) v = { d: e.d, price: e.p[card.url][0] };
    return v;
  }

  function vsMarketHtml(card) {
    if (!state.hist || !hasMarket(card)) return '';
    const now = refTime();
    const cur = cardPriceAt(card, now);
    if (!cur) return '';
    const rows = [7, 30].map((days) => {
      const from = new Date(new Date(now).getTime() - days * 86400000).toISOString();
      const past = cardPriceAt(card, from);
      if (!past) return { days, empty: true };
      const c = (cur.price / past.price - 1) * 100;
      const m = marketMove(past.d, now);
      return { days, c, m, gap: m ? c - m.pct : null };
    });
    if (rows.every((r) => r.empty)) {
      return `<div class="vs-mkt"><span class="lbl">Vs. the market</span><span class="muted">Needs at least 7 days of price history.</span></div>`;
    }
    const cell = (r) => r.empty
      ? `<div class="vs-row"><span>${r.days} days</span><span class="muted">not enough history yet</span></div>`
      : `<div class="vs-row"><span>${r.days} days</span><span>card <b class="${dirClass(r.c)}">${fmtPct(r.c)}</b></span>${r.m
          ? `<span>${escapeHtml(r.m.name)} <b class="${dirClass(r.m.pct)}">${fmtPct(r.m.pct)}</b></span><span class="vs-gap ${dirClass(r.gap)}">${Math.abs(r.gap) < 1 ? 'in line with the market' : `${Math.abs(r.gap).toFixed(1)} pts ${r.gap > 0 ? 'stronger' : 'weaker'}`}</span>`
          : '<span class="muted">no index data</span>'}</div>`;
    return `<div class="vs-mkt"><span class="lbl">Vs. the market</span>${rows.map(cell).join('')}
      <p class="cd-note">Weaker than the market means the card is falling for its own reasons (new supply, fading interest); in line means it is moving with a market-wide dip.</p></div>`;
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
    const act = activeEvents();
    if (act.length) {
      const held = (data.cards || []).filter(heldByEvent).map((c) => parseCardName(c.card_name_ja).short);
      html += `<div class="banner warning"><strong>Event rule on: ${escapeHtml(act.map((e) => e.name + ' ' + eventWhen(e)).join(' · '))}.</strong>Right before a major release prices often dip, so Buy-zone prices show as Watch until it's out (${escapeHtml([...new Set(act.map(eventScope))].join(', '))})${held.length ? `; now: ${escapeHtml(held.join(', '))}` : ''}. Definitely-buy prices and your own limits still count.</div>`;
    } else {
      const next = upcomingEvents().find((e) => e.d && e.major !== false && daysUntil(e.d) <= 14);
      if (next) html += `<div class="banner auto"><strong>Coming up: ${escapeHtml(next.name)}, ${escapeHtml(eventWhen(next))}</strong>The event rule holds Buy calls for ${escapeHtml(eventScope(next))} in the ${eventWindow()} days before it.</div>`;
    }
    const cs = correctionState();
    if (cs.active) {
      const held = (data.cards || []).filter(heldByCorrection).map((c) => parseCardName(c.card_name_ja).short);
      html += `<div class="banner warning"><strong>Correction rule on: ${escapeHtml(cs.name)} ${fmtPct(cs.pct)} over 30 days.</strong>While the market is still falling more than ${CORRECTION_PCT}% a month, only Definitely-buy prices count as a buy; cards in the Buy zone show as Watch${held.length ? ` (now: ${escapeHtml(held.join(', '))})` : ''}. Your own limit prices still trigger signals.</div>`;
    }
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

  // ---------- card photos: zoom each one so the card fills its frame ----------
  // SNKRDUNK's cut-out photos sit on a transparent canvas with a different amount of
  // empty margin per upload. Measure the card's bounding box once per photo (from the
  // alpha channel, on a small canvas) and size/center the <img> so the card itself
  // takes ~92% of the frame height. Measuring needs CORS; if the CDN refuses, the
  // photo keeps a default zoom that fits SNKRDUNK's usual margin. Results are cached
  // in this browser.
  const TRIM_KEY = 'psa10.imgTrim.v1';
  const trimCache = store.get(TRIM_KEY, {});
  const trimPending = {};
  function measureTrim(url) {
    return new Promise((resolve) => {
      const im = new Image();
      im.crossOrigin = 'anonymous';
      im.onload = () => {
        try {
          const W = 160, H = Math.max(1, Math.round((W * im.naturalHeight) / im.naturalWidth));
          const cv = document.createElement('canvas');
          cv.width = W; cv.height = H;
          const g = cv.getContext('2d');
          g.drawImage(im, 0, 0, W, H);
          const d = g.getImageData(0, 0, W, H).data;
          let x0 = W, y0 = H, x1 = -1, y1 = -1;
          for (let y = 0; y < H; y++) {
            for (let x = 0; x < W; x++) {
              if (d[(y * W + x) * 4 + 3] > 24) {
                if (x < x0) x0 = x; if (x > x1) x1 = x;
                if (y < y0) y0 = y; if (y > y1) y1 = y;
              }
            }
          }
          if (x1 < 0 || (y1 - y0) < H * 0.2) return resolve(null);
          resolve({ x0: x0 / W, y0: y0 / H, x1: (x1 + 1) / W, y1: (y1 + 1) / H });
        } catch (e) { resolve(null); } // canvas tainted: no CORS on the CDN
      };
      im.onerror = () => resolve(null);
      im.src = url;
    });
  }
  function applyTrim(img, t) {
    img.style.setProperty('--h', (92 / (t.y1 - t.y0)).toFixed(1) + '%');
    img.style.setProperty('--cx', ((t.x0 + t.x1) / 2).toFixed(4));
    img.style.setProperty('--cy', ((t.y0 + t.y1) / 2).toFixed(4));
  }
  function trimImages(root) {
    (root || document).querySelectorAll('img.card-img').forEach((img) => {
      const url = img.getAttribute('src');
      if (!url) return;
      if (trimCache[url]) { applyTrim(img, trimCache[url]); return; }
      (trimPending[url] = trimPending[url] || measureTrim(url)).then((t) => {
        if (!t) return;
        if (!trimCache[url]) { trimCache[url] = t; store.set(TRIM_KEY, trimCache); }
        if (img.isConnected) applyTrim(img, t);
        document.querySelectorAll('img.card-img').forEach((o) => { if (o.getAttribute('src') === url) applyTrim(o, t); });
      });
    });
  }

  // ---------- render ----------

  function render() {
    const data = state.currentData;
    const cards = data.cards || [];
    const prevCards = (state.previousData && state.previousData.cards) || [];
    els.collectedAt.textContent = fmtDateJST(data.collected_at_jst);
    renderMarketStrip(data);
    renderCustomIndex();
    renderEvents();
    renderHeat();
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
    trimImages(document);
  }

  // Order used by the list and the display case: cards with a listing at or below
  // your limit first, then Definitely-buy / Buy zones, otherwise the snapshot's order.
  // ---------- sorting (overview + collection) ----------
  // Default = signals first (your limit, then Definitely-buy / Buy), then the tracker order.
  // Other keys come from the overview's column headers (desktop) or the Sort menu (phone).
  // Cards without a value (e.g. no 30-day history yet) always go last.
  const VERDICT_RANK = { definitely_buy: 0, buy: 1, watch: 2, dont_buy: 3, defer: 4 };
  const SORTS = {
    default: { label: 'Signals first', dir: 1 },
    name: { label: 'Card name', dir: 1, v: (c) => parseCardName(c.card_name_ja).short },
    price: { label: 'Price', dir: -1, v: (c) => getRep(c) },
    zone: { label: 'Closest to Buy', dir: 1, v: (c) => { const t = c.analysis && c.analysis.tiers; const p = getRep(c); return t && p != null ? p / t.buy_upper : null; } },
    chgLast: { label: 'Change since last check', dir: 1, v: (c) => (priceChangeLast(c) || {}).pct ?? null },
    chg7: { label: '7-day change', dir: 1, v: (c) => (priceChangeAgo(c, 7) || {}).pct ?? null },
    chg30: { label: '30-day change', dir: 1, v: (c) => (priceChangeAgo(c, 30) || {}).pct ?? null },
    verdict: { label: 'Verdict', dir: 1, v: (c) => (limitHit(c) ? -1 : VERDICT_RANK[displayTagFor(c)] ?? 5) },
    heat: { label: 'Trading activity', dir: -1, v: (c) => { const h = heatOf(c); return h && h.psa ? h.psa.rate : null; } },
  };
  let sortState = store.get('psa10.sort', { key: 'default', dir: 1 });
  if (!SORTS[sortState.key]) sortState = { key: 'default', dir: 1 };

  function sortCardsBy(cards, defs, st) {
    const rank = (c) => (limitHit(c) ? 0 : 3) + ({ definitely_buy: 0, buy: 1 }[displayTagFor(c)] ?? 2);
    const base = cards.map((card, i) => ({ card, i }));
    const sd = defs[st.key] || defs.default;
    if (!sd.v) return base.sort((a, b) => rank(a.card) - rank(b.card) || a.i - b.i).map((x) => x.card);
    const vals = new Map(base.map((x) => [x.card, sd.v(x.card)]));
    return base.sort((a, b) => {
      const va = vals.get(a.card), vb = vals.get(b.card);
      if (va == null && vb == null) return a.i - b.i;
      if (va == null) return 1;
      if (vb == null) return -1;
      const c = typeof va === 'string' ? va.localeCompare(vb, 'ja') : va - vb;
      return c * st.dir || rank(a.card) - rank(b.card) || a.i - b.i;
    }).map((x) => x.card);
  }
  function sortedMarketCards(cards) { return sortCardsBy(cards.filter(hasMarket), SORTS, sortState); }

  // Tables page: same keys plus the extra statistics shown there; its own remembered order.
  const TABLE_SORTS = Object.assign({}, SORTS, {
    depth: { label: 'Order-book depth', dir: -1, v: (c) => { const d = depthInfo(c.grades.psa10); return d.total ? d.within / d.total : null; } },
    favorites: { label: 'Favorites', dir: -1, v: (c) => c.favorite_count ?? null },
    population: { label: 'PSA10 population', dir: -1, v: (c) => c.psa10_population ?? null },
    gem: { label: 'Gem rate', dir: -1, v: (c) => c.psa10_gem_rate_pct ?? null },
    offpeak: { label: 'Off peak', dir: -1, v: (c) => { const pk = c.analysis && c.analysis.peak; return pk && pk.price ? computeOffPeakPct(pk.price, getRep(c)) : null; } },
    raw: { label: 'Raw A-rank price', dir: 1, v: (c) => { const r = c.grades && c.grades.raw_a_grade; return r ? r.lowest_price ?? null : null; } },
    diy: { label: 'DIY vs. slab', dir: 1, v: (c) => { const d = computeDiyEconomics(c, getRep(c)); return d ? d.delta : null; } },
  });
  let tableSort = store.get('psa10.tableSort', { key: 'default', dir: 1 });
  if (!TABLE_SORTS[tableSort.key]) tableSort = { key: 'default', dir: 1 };
  function setTableSort(key, dir) {
    if (!TABLE_SORTS[key]) return;
    tableSort = { key, dir: dir != null ? dir : (tableSort.key === key ? -tableSort.dir : TABLE_SORTS[key].dir) };
    store.set('psa10.tableSort', tableSort);
    if (state.currentData) renderTables(state.currentData.cards || [], (state.previousData && state.previousData.cards) || []);
  }
  function sortableLabel(key, label) {
    const on = tableSort.key === key, dir = on ? (tableSort.dir > 0 ? 'asc' : 'desc') : '';
    return `<button type="button" class="tsort${on ? ' on' : ''}" data-tsort="${key}" data-dir="${dir}" aria-sort="${on ? (tableSort.dir > 0 ? 'ascending' : 'descending') : 'none'}" title="Sort the cards by this row">${label}</button>`;
  }
  function wireTableSort() {
    const bar = document.getElementById('tbl-sortbar');
    if (bar) {
      bar.innerHTML = `<label for="tbl-sort-select">Sort cards by</label><select id="tbl-sort-select">${Object.entries(TABLE_SORTS).map(([k, d]) => `<option value="${k}"${k === tableSort.key ? ' selected' : ''}>${escapeHtml(d.label)}</option>`).join('')}</select>${tableSort.key !== 'default' ? `<button type="button" id="tbl-sort-dir" aria-label="Reverse order">${tableSort.dir > 0 ? '↑' : '↓'}</button>` : ''}`;
      bar.querySelector('select').addEventListener('change', (e) => setTableSort(e.target.value, TABLE_SORTS[e.target.value].dir));
      const d = bar.querySelector('#tbl-sort-dir'); if (d) d.addEventListener('click', () => setTableSort(tableSort.key, -tableSort.dir));
    }
    document.querySelectorAll('[data-tsort]').forEach((b) => b.addEventListener('click', () => {
      if (b.dataset.tsort === tableSort.key && tableSort.dir !== TABLE_SORTS[tableSort.key].dir) return setTableSort('default', 1);
      setTableSort(b.dataset.tsort);
    }));
  }

  function setSort(key, dir) {
    if (!SORTS[key]) return;
    sortState = { key, dir: dir != null ? dir : (sortState.key === key ? -sortState.dir : SORTS[key].dir) };
    store.set('psa10.sort', sortState);
    syncSortUi();
    if (state.currentData) { renderOverviewList(state.currentData.cards || []); renderCollection(state.currentData.cards || []); }
  }
  function syncSortUi() {
    document.querySelectorAll('.wl-head [data-sort]').forEach((b) => {
      const on = b.dataset.sort === sortState.key;
      b.classList.toggle('on', on);
      b.dataset.dir = on ? (sortState.dir > 0 ? 'asc' : 'desc') : '';
      b.setAttribute('aria-sort', on ? (sortState.dir > 0 ? 'ascending' : 'descending') : 'none');
    });
    const sel = document.getElementById('wl-sort-select'), dirBtn = document.getElementById('wl-sort-dir');
    if (sel) sel.value = sortState.key;
    if (dirBtn) { dirBtn.textContent = sortState.dir > 0 ? '↑' : '↓'; dirBtn.hidden = sortState.key === 'default'; }
  }
  function initSortUi() {
    document.querySelectorAll('.wl-head [data-sort]').forEach((b) => b.addEventListener('click', () => {
      // clicking the active column a third time goes back to the default order
      if (b.dataset.sort === sortState.key && sortState.dir !== SORTS[sortState.key].dir) return setSort('default', 1);
      setSort(b.dataset.sort);
    }));
    const sel = document.getElementById('wl-sort-select');
    if (sel) {
      sel.innerHTML = Object.entries(SORTS).map(([k, d]) => `<option value="${k}">${escapeHtml(d.label)}</option>`).join('');
      sel.addEventListener('change', () => setSort(sel.value, SORTS[sel.value].dir));
    }
    const dirBtn = document.getElementById('wl-sort-dir');
    if (dirBtn) dirBtn.addEventListener('click', () => setSort(sortState.key, -sortState.dir));
    syncSortUi();
  }

  // ---------- render: key numbers ----------

  function renderKpis(data) {
    const idx = data.pokeca_chart_index || {};
    const p = idx.psa10 || {}, r = idx.raw_bihin || {};
    const st = plannerState();
    const spent = state.holdings.reduce((a, h) => a + holdingCost(h), 0);
    const chg = (x) => `<span class="${dirClass(x.day_change_pct)}">${fmtPct(x.day_change_pct)} day</span> · <span class="${dirClass(x.month_change_pct)}">${fmtPct(x.month_change_pct)} month</span>`;
    const ci = customIndexStats();
    const ciD = !ci ? 'no readings yet'
      : ci.ser.length === 1 ? `base ${escapeHtml(ci.ci.meta.base_date)} = 100 · first reading`
      : [ci.day != null ? `<span class="${dirClass(ci.day)}">${fmtPct(ci.day)} day</span>` : 'day: —',
         ci.month != null ? `<span class="${dirClass(ci.month)}">${fmtPct(ci.month)} month</span>` : `since ${escapeHtml(ci.ci.meta.base_date)}: <span class="${dirClass(ci.last.level - 100)}">${fmtPct(ci.last.level - 100)}</span>`].join(' · ');
    const tiles = [
      { href: '#/market', k: 'PSA10 index', v: fmtYen(p.latest_index_value_jpy), d: chg(p) },
      { href: '#/market', k: 'Raw A-rank index', v: fmtYen(r.latest_index_value_jpy), d: chg(r) },
      { href: '#/market', k: 'My-tier index', v: ci ? ci.last.level.toFixed(2) : '—', d: ciD },
      { href: '#/planner', k: 'Budget left', v: fmtYen(st.budget - spent), d: `of ${fmtYen(st.budget)} · ${fmtYen(spent)} spent` },
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
      const thumbHtml = imgSrc ? `<img class="card-img" src="${escapeAttr(imgSrc)}" alt="" loading="lazy" onerror="this.remove();">` : '';
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

  // ---------- trading activity ("heat") ----------
  // How fast a card trades on SNKRDUNK: recent one-copy completed sales (up to 20 per
  // grade, as read by the price check) divided by the days since the oldest of them.
  // Same rule as scripts/build_history.py, which stores it per snapshot in history.json.
  // Calibrated 2026-09-26 on 110 modern PSA10 cards (pokeca-chart September trade counts, ≈1.9× SNKRDUNK
  // one-copy sales): Hot ≈ top 10%, Active ≈ top 25%, Slow = middle half, Cold ≈ bottom 25%.
  const HEAT_LEVELS = [[5, 'hot', 'Hot'], [3, 'active', 'Active'], [1.2, 'slow', 'Slow'], [0, 'cold', 'Cold']];
  const REL_DAYS = { '秒': 1 / 86400, '分': 1 / 1440, '時間': 1 / 24, '日': 1, '週間': 7, 'ヶ月': 30, 'か月': 30 };
  function saleAgeDays(when, refMs) {
    const w = String(when || '').trim();
    if (w === 'たった今' || w === '今') return 0;
    let m = w.match(/^(\d+)\s*(秒|分|時間|日|週間|ヶ月|か月)前/);
    if (m) return (Number(m[1]) + 0.5) * REL_DAYS[m[2]];
    m = w.match(/^(\d{4})\/(\d{1,2})\/(\d{1,2})/);
    if (m) return Math.max(0, (refMs - Date.parse(`${m[1]}-${m[2].padStart(2, '0')}-${m[3].padStart(2, '0')}T12:00:00+09:00`)) / 86400000);
    return null;
  }
  function salesPerDay(sales, refIso) {
    const ref = Date.parse(refIso);
    const ages = (sales || []).map((x) => saleAgeDays(x.when, ref)).filter((a) => a != null);
    if (ages.length < 2 || isNaN(ref)) return null;
    const span = Math.max(Math.max(...ages), 0.25);
    // 20 sales within SNKRDUNK's coarsest timestamp ("1日前") means the true rate may be higher
    return { rate: ages.length / span, n: ages.length, span, sat: ages.length >= 20 && span <= 1.6 };
  }
  function rateTxt(x) { return x ? fmtRate(x.rate) + (x.sat ? '+' : '') : '—'; }
  function heatLevel(rate) { return rate == null ? null : HEAT_LEVELS.find(([min]) => rate >= min); }
  function fmtRate(r) { return r == null ? '—' : r >= 10 ? String(Math.round(r)) : r >= 1 ? r.toFixed(1) : r.toFixed(2); }
  function heatOf(card) {
    const ref = (state.currentData && state.currentData.collected_at_jst) || new Date().toISOString();
    const g = card.grades || {};
    const psa = salesPerDay((g.psa10 || {}).recent_completed_sales, ref);
    const raw = salesPerDay((g.raw_a_grade || {}).recent_completed_sales, ref);
    if (!psa && !raw) return null;
    // a week ago, from history.json
    const snaps = (state.hist && state.hist.snapshots) || [];
    const weekAgo = new Date(Date.parse(ref) - 7 * 86400000).toISOString();
    let prev = null;
    for (const e of snaps) { if (Date.parse(e.d) <= Date.parse(weekAgo) && e.h && e.h[card.url] && e.h[card.url][0] != null) prev = { d: e.d, rate: e.h[card.url][0] }; }
    const within = (g.psa10 || {}).count_within_15pct;
    const cover = psa && within ? within / psa.rate : null;
    return { psa, raw, prev, cover, within, level: heatLevel(psa ? psa.rate : null) };
  }
  // Raw A-rank sells far more often than PSA10, so it has its own thresholds (watching page).
  const HEAT_LEVELS_RAW = [[40, 'hot', 'Hot'], [15, 'active', 'Active'], [5, 'slow', 'Slow'], [0, 'cold', 'Cold']];
  const HEAT_ICON = {
    hot: '<svg viewBox="0 0 16 16" aria-hidden="true"><path fill="currentColor" d="M8.2 1c.6 2.6 3.8 4 3.8 8.1A4 4 0 0 1 4 9.3c0-1.9.9-3.1 1.9-3.9 0 1.4.6 2.3 1.4 2.6C7 5.9 7 3.4 8.2 1z"/></svg>',
    slow: '<svg viewBox="0 0 16 16" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><path d="M8 1.5v13M2.4 4.75l11.2 6.5M2.4 11.25l11.2-6.5M6.2 2.9 8 4.4l1.8-1.5M6.2 13.1 8 11.6l1.8 1.5"/></svg>',
  };
  function heatChip(card, grade) {
    const h = heatOf(card);
    const x = h && (grade === 'raw' ? h.raw : h.psa);
    if (!x) return '';
    const lv = (grade === 'raw' ? HEAT_LEVELS_RAW : HEAT_LEVELS).find(([min]) => x.rate >= min);
    const what = grade === 'raw' ? 'raw A-rank' : 'PSA10';
    return `<span class="heat-chip heat-${lv[1]}" title="About ${rateTxt(x)} ${what} sales a day on SNKRDUNK">${HEAT_ICON[lv[1]] || ''}${lv[2]}</span>`;
  }
  function heatStatHtml(card) {
    const h = heatOf(card);
    if (!h || !h.psa) return `<div class="cd-stat"><div class="lbl">PSA10 trading</div><div class="val">—</div><div class="heat-sub">No recent PSA10 sales on SNKRDUNK</div></div>`;
    const ch = h.prev && h.prev.rate ? (h.psa.rate / h.prev.rate - 1) * 100 : null;
    const spanTxt = h.psa.span < 1 ? `${Math.max(1, Math.round(h.psa.span * 24))} h` : `${h.psa.span.toFixed(h.psa.span < 10 ? 1 : 0)} days`;
    return `<div class="cd-stat"><div class="lbl">PSA10 trading (SNKRDUNK)</div>
      <div class="val">≈${rateTxt(h.psa)} / day ${heatChip(card)}</div>
      <div class="heat-sub">Last ${h.psa.n} sales in ${spanTxt}${h.prev ? ` · a week ago ≈${fmtRate(h.prev.rate)}/day${ch != null ? ` <span class="${dirClass(ch)}">(${fmtPct(ch)})</span>` : ''}` : ''}${h.cover != null ? `<br>Cheap listings (${h.within}) ≈ ${h.cover < 1 ? Math.max(1, Math.round(h.cover * 24)) + ' h' : h.cover.toFixed(1) + ' days'} of sales` : ''}${h.raw ? ` · raw A ≈${fmtRate(h.raw.rate)}/day` : ''}</div></div>`;
  }
  function renderHeat() {
    const el = document.getElementById('heat-panel');
    if (!el) return;
    const cards = ((state.currentData && state.currentData.cards) || []).map((c) => ({ c, h: heatOf(c) })).filter((x) => x.h && (x.h.psa || x.h.raw));
    if (!cards.length) { el.hidden = true; return; }
    el.hidden = false;
    cards.sort((a, b) => ((b.h.psa || {}).rate || -1) - ((a.h.psa || {}).rate || -1) || ((b.h.raw || {}).rate || 0) - ((a.h.raw || {}).rate || 0));
    const rows = cards.map(({ c, h }) => {
      const { short, code } = parseCardName(c.card_name_ja);
      const ch = h.psa && h.prev && h.prev.rate ? (h.psa.rate / h.prev.rate - 1) * 100 : null;
      return `<tr><td><a href="#/card/${escapeAttr(cardId(c))}"><b class="jp">${escapeHtml(short)}</b></a> <small class="muted">${escapeHtml(code)}</small></td>
        <td class="num">${rateTxt(h.psa)}</td><td>${heatChip(c)}</td>
        <td class="num">${h.prev ? fmtRate(h.prev.rate) : '—'}${ch != null ? ` <span class="${dirClass(ch)}">${fmtPct(ch)}</span>` : ''}</td>
        <td class="num">${h.cover != null ? (h.cover < 1 ? Math.max(1, Math.round(h.cover * 24)) + ' h' : h.cover.toFixed(1) + ' d') : '—'}</td>
        <td class="num">${h.raw ? fmtRate(h.raw.rate) : '—'}</td></tr>`;
    }).join('');
    el.innerHTML = `<h2 class="section-title">Trading activity</h2>
      <p class="ci-note">How often each card actually sells on SNKRDUNK, from its recent one-copy completed sales (the last 20 per grade; "13+" means 20 sales within about a day, so the true rate may be higher). Hot ≥ 5 PSA10 sales a day (about the busiest 10% of modern PSA10 cards), Active ≥ 3 (top quarter), Slow ≥ 1.2 (the middle half), Cold below. "Cheap listings last" = listings within 15% of the lowest ask ÷ daily PSA10 sales: a short time means the cheap end gets bought up fast; a long time means copies sit.</p>
      <div class="table-scroll"><table class="heat-table"><thead><tr><th>Card</th><th class="num">PSA10 sales / day</th><th></th><th class="num">A week ago</th><th class="num">Cheap listings last</th><th class="num">Raw A sales / day</th></tr></thead><tbody>${rows}</tbody></table></div>`;
  }

  function tagChip(card) {
    const tag = displayTagFor(card);
    return tag ? `<span class="vtag ${tag}">${escapeHtml(tagLabel(tag))}</span>` : `<span class="vtag none">No tiers</span>`;
  }

  function slabHtml(card, size) {
    const code = parseCardName(card.card_name_ja).code;
    const img = card.image_url ? `<img class="card-img" src="${escapeAttr(card.image_url)}" alt="" loading="lazy" onerror="this.remove()">` : '';
    return `<span class="slab ${size || ''}"><span class="slab-label"><b>${escapeHtml(code)}</b><b>GEM MT 10</b></span><span class="slab-art ${artClassFor(card)}">${img}</span></span>`;
  }

  // Price change vs the latest snapshot at least `days` old (history.json, same price rule as getRep).
  function priceChangeAgo(card, days) {
    const snaps = (state.hist && state.hist.snapshots) || [];
    const ref = Date.parse((state.currentData && state.currentData.collected_at_jst) || new Date().toISOString());
    const cut = ref - days * 86400000;
    let then = null;
    for (const e of snaps) { if (Date.parse(e.d) <= cut && e.p && e.p[card.url]) then = e; }
    const now = getRep(card);
    if (!then || now == null) return null;
    const old = then.p[card.url][0];
    return old ? { pct: (now / old - 1) * 100, from: then.d.slice(0, 10), old } : null;
  }
  // Change vs the previous snapshot (the check before the one being shown).
  function priceChangeLast(card) {
    const prev = prevCardOf(card), now = getRep(card), old = prev ? getRep(prev) : null;
    if (old == null || now == null || !old) return null;
    return { pct: (now / old - 1) * 100, old, from: ((state.previousData && state.previousData.collected_at_jst) || '').slice(0, 16).replace('T', ' ') };
  }
  function changeLastCell(card, cls) {
    const c = priceChangeLast(card);
    if (!c) return `<span class="${cls} muted" title="No earlier snapshot for this card">—</span>`;
    return `<span class="${cls} ${dirClass(c.pct)}" title="${fmtYen(c.old)} at the previous check (${escapeHtml(c.from)} JST)">${c.pct === 0 ? '±0' : fmtPct(c.pct)}</span>`;
  }
  function changeCell(card, days, cls) {
    const c = priceChangeAgo(card, days);
    if (!c) return `<span class="${cls} muted" title="No snapshot from ${days} days ago yet (history starts 2026-09-15)">—</span>`;
    return `<span class="${cls} ${dirClass(c.pct)}" title="${fmtYen(c.old)} on ${c.from}">${fmtPct(c.pct)}</span>`;
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
        ${changeLastCell(card, 'wl-chg')}${changeCell(card, 7, 'wl-chg')}${changeCell(card, 30, 'wl-chg')}
        <span class="wl-tag">${tagChip(card)}${owned ? '<span class="owned-chip">Owned</span>' : ''}${limitHit(card) ? '<span class="limit-chip">Limit</span>' : ''}${(tierReview(card) || {}).due ? '<span class="due-chip" title="Tiers are due for a review">Review</span>' : ''}</span>
        <span class="wl-heat">${heatChip(card)}</span>
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
    trimImages(el);
  }

  function renderCardPage(card) {
    const el = document.getElementById('card-page');
    el.innerHTML = buildCardDetail(card, prevCardOf(card), 'page');
    wireCardDetail(el, card);
    trimImages(el);
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
          <span class="tile-chips">${heatChip(card)}${tagChip(card)}</span>
          ${lim != null ? `<span class="tile-limit">Limit ${fmtYen(lim)}</span>` : ''}
          ${owned ? '<span class="tile-owned">Owned</span>' : ''}
        </span>
        <span class="tile-name jp">${escapeHtml(short)}</span>
        <span class="tile-price"><b class="display">${fmtYen(getRep(card))}</b><span class="tile-chg"><small>7d</small>${changeCell(card, 7, 'tc')}<small>30d</small>${changeCell(card, 30, 'tc')}</span></span>
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
      const thumbHtml = card.image_url ? `<img class="card-img" src="${escapeAttr(card.image_url)}" alt="" loading="lazy" onerror="this.remove();">` : '';
      return `<a class="watch-row" href="${escapeAttr(card.url)}" target="_blank" rel="noopener">
        <span class="wthumb">${thumbHtml}</span>
        <span class="wname"><b class="jp">${escapeHtml(short || card.card_name_ja)}</b><small>${escapeHtml(code)}</small></span>
        <span class="wraw"><small>Raw A</small><b class="display">${raw && raw.lowest_price != null ? fmtYen(raw.lowest_price) : '—'}</b></span>
        <span class="wheat">${heatChip(card, 'raw')}${(heatOf(card) || {}).raw ? `<small>≈${rateTxt(heatOf(card).raw)} raw A sales / day</small>` : ''}</span>
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
      : `<button type="button" class="limit-btn" data-act="edit">+ Set my limit</button><span class="limit-gap">get a Buy signal when a listing drops to it</span>`}${limitSyncHtml(card)}</div>${limit != null ? limitOddsHtml(card, limit) : ''}`;

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
        ${heatStatHtml(card)}
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
      if (heldByEvent(card)) {
        const ev = eventFor(card);
        staleHtml = `<div class="verdict-stale">Price is in the Buy zone, shown as Watch by the event rule: ${escapeHtml(ev.name)} ${escapeHtml(eventWhen(ev))}. Prices often dip around a big release; it becomes a buy again after that, or now at Definitely-buy (≤${fmtYen(analysis.tiers.definitely_buy)}).</div>`;
      } else if (heldByCorrection(card)) {
        const cs = correctionState();
        staleHtml = `<div class="verdict-stale">Price is in the Buy zone, shown as Watch by the correction rule (${escapeHtml(cs.name)} ${fmtPct(cs.pct)} over 30 days). It becomes a buy at Definitely-buy (≤${fmtYen(analysis.tiers.definitely_buy)}) or once the market steadies.</div>`;
      } else if (v.tag && v.tag !== 'defer' && displayTag && v.tag !== displayTag) {
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
          ${tierReviewHtml(card)}
          ${limitRowHtml}
          ${vsMarketHtml(card)}
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
    const mo = sm.model_odds;
    const modelTile = mo && mo.logged
      ? (mo.brier != null
        ? `<div class="pl-stat"><div class="lbl">Limit-odds model (Brier)</div><div class="val ${mo.brier <= 0.2 ? 'pos' : mo.brier > 0.25 ? 'neg' : ''}">${mo.brier.toFixed(2)}</div><div class="tr-hint">${mo.expected_yes} expected vs ${mo.actual_yes} happened, of ${mo.resolved} resolved · ${mo.open} open</div></div>`
        : `<div class="pl-stat"><div class="lbl">Limit-odds model</div><div class="val muted">${mo.open} open</div><div class="tr-hint">weekly forecasts for tier prices and your limits; first results after 30 days</div></div>`)
      : '';
    const headline = sm.calls_scored
      ? `${c.right || 0} right · ${c.wrong || 0} wrong${c.neutral ? ` · ${c.neutral} neutral` : ''}`
      : 'no calls scored yet';

    // Grouped by card: one collapsible block per card with its calls and stated odds,
    // cards with the most recent activity first.
    const callRow = (k) => {
      const so = k.status === 'pending'
        ? `day ${k.days_in}/${win} · low so far ${k.low != null ? fmtYen(k.low) + ' (' + trPct(k.low_pct) + ')' : '—'} · now ${k.now != null ? fmtYen(k.now) + ' (' + trPct(k.now_pct) + ')' : '—'}`
        : escapeHtml(k.why);
      return `<div class="tr-row">
        <div class="tr-main"><span class="vtag ${k.tag}">${escapeHtml(tagLabel(k.tag))}</span>
          <span class="tr-meta">${trDate(k.made)} at ${fmtYen(k.price)}${k.reaffirmed ? ` · reaffirmed ${k.reaffirmed}×` : ''}</span></div>
        <div class="tr-res">${trPill(k.status)}</div>
        <div class="tr-sub">${escapeHtml(k.label || '')}<br>${so}</div>
      </div>`;
    };
    const predRow = (p) => {
      const detail = p.status === 'open'
        ? `now ${p.now != null ? fmtYen(p.now) : '—'}${p.gap_pct != null ? ` · needs ${trPct(p.gap_pct)}` : ''} · ${escapeHtml(p.why)}`
        : escapeHtml(p.why);
      return `<div class="tr-row">
        <div class="tr-main"><span class="tr-odds">${Math.round(p.p * 100)}%</span>
          <span class="tr-meta">${p.type === 'touch_below' ? '≤' : '≥'}${fmtYen(p.price)} by ${trDate(p.by)}</span></div>
        <div class="tr-res">${trPill(p.status)}</div>
        <div class="tr-sub">${escapeHtml(p.text)} (said ${trDate(p.made)})<br>${detail}</div>
      </div>`;
    };
    const groups = new Map();
    const groupOf = (url, name) => {
      if (!groups.has(url)) groups.set(url, { url, name, calls: [], preds: [], last: '' });
      return groups.get(url);
    };
    tr.calls.forEach((k) => { const g = groupOf(k.url, k.name); g.calls.push(k); if (k.made > g.last) g.last = k.made; });
    (tr.predictions || []).forEach((p) => { const g = groupOf(p.url, p.name); g.preds.push(p); if ((p.made || '') > g.last) g.last = p.made || ''; });
    const openSet = new Set(store.get('psa10.trOpen', []));
    const cnt = (arr, st) => arr.filter((x) => x.status === st).length;
    const groupHtml = [...groups.values()].sort((x, y) => (x.last < y.last ? 1 : x.last > y.last ? -1 : 0)).map((g) => {
      const { short, code } = parseCardName(g.name);
      g.calls.sort((x, y) => (x.made < y.made ? 1 : -1));
      g.preds.sort((x, y) => (x.by < y.by ? -1 : x.by > y.by ? 1 : 0));
      const cur = g.calls[0];
      const callSum = [['right', 'right'], ['wrong', 'wrong'], ['neutral', 'neutral'], ['pending', 'pending']]
        .map(([st, l]) => (cnt(g.calls, st) ? `${cnt(g.calls, st)} ${l}` : '')).filter(Boolean).join(' · ');
      const oddsSum = [['yes', 'happened'], ['no', "didn't"], ['open', 'open'], ['void', 'void']]
        .map(([st, l]) => (cnt(g.preds, st) ? `${cnt(g.preds, st)} ${l}` : '')).filter(Boolean).join(' · ');
      return `<details class="tr-card" data-url="${escapeAttr(g.url)}"${openSet.has(g.url) ? ' open' : ''}>
        <summary>
          <span class="tr-cname"><span class="tr-name jp">${escapeHtml(short)}</span><span class="tr-meta">${escapeHtml(code)}</span></span>
          <span class="tr-csum">${cur ? `<span class="tr-meta">Latest call</span><span class="vtag ${cur.tag}">${escapeHtml(tagLabel(cur.tag))}</span>` : ''}
            <span class="tr-meta">${g.calls.length ? `Calls: ${callSum}` : 'No calls'}${g.preds.length ? ` <span class="tr-dot">·</span> Odds: ${oddsSum}` : ''}</span></span>
        </summary>
        <div class="tr-cbody">
          ${g.calls.length ? `<div class="tr-sh">Calls</div><div class="tr-list">${g.calls.map(callRow).join('')}</div>` : ''}
          ${g.preds.length ? `<div class="tr-sh">Stated odds</div><div class="tr-list">${g.preds.map(predRow).join('')}</div>` : ''}
        </div>
      </details>`;
    }).join('');

    sec.innerHTML = `
        <div class="pl-summary">
          <div class="pl-stat"><div class="lbl">Buy / Watch calls</div><div class="val">${escapeHtml(headline)}</div><div class="tr-hint">${c.pending || 0} still inside their ${win}-day window</div></div>
          ${brier}
          ${modelTile}
        </div>
        <div class="tr-bar"><h3 class="tr-h">By card</h3><button type="button" class="limit-btn tr-toggle">Expand all</button></div>
        <div class="tr-cards">${groupHtml}</div>
        <p class="tr-note">How it's scored: each change of verdict is one call, measured on the lowest PSA10 ask over the next ${win} days.
          A <b>Buy</b> is wrong if the price drops more than the card's threshold below the call price (you could have bought cheaper), otherwise right.
          A <b>Watch</b> is right if it drops more than the threshold (waiting paid off), wrong if it ends more than the threshold higher without a dip, otherwise neutral.
          The threshold is ${th}% or the card's own normal swing between checks if larger (up to ${Math.round((tr.noise_threshold_cap || 0.1) * 100)}%), and a drop only counts after ${tr.confirm_readings || 2} checks in a row below it, so one stray cheap listing can't decide a call.
          Stated odds are checked against their deadline; the Brier score rewards odds that match how often things actually happen.
          Updated with every price check (as of ${escapeHtml(fmtDateShort(tr.as_of))}).</p>`;
    const saveOpen = () => store.set('psa10.trOpen', [...sec.querySelectorAll('details.tr-card[open]')].map((d) => d.dataset.url));
    const toggle = sec.querySelector('.tr-toggle');
    const syncToggle = () => {
      const all = [...sec.querySelectorAll('details.tr-card')];
      toggle.textContent = all.length && all.every((d) => d.open) ? 'Collapse all' : 'Expand all';
    };
    sec.querySelectorAll('details.tr-card').forEach((d) => d.addEventListener('toggle', () => { saveOpen(); syncToggle(); }));
    toggle.addEventListener('click', () => {
      const all = [...sec.querySelectorAll('details.tr-card')];
      const open = !all.every((d) => d.open);
      all.forEach((d) => { d.open = open; });
      saveOpen(); syncToggle();
    });
    syncToggle();
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

  function limitSyncHtml(card) {
    const st = limitSync(card);
    if (st === 'synced') return '<span class="limit-sync ok">✓ Saved on all devices</span>';
    if (st !== 'local') return '';
    const clearing = getLimit(card) == null;
    return `<span class="limit-sync">${clearing ? 'Removed on this device only' : 'Only on this device'} · <a href="${escapeAttr(limitFormUrl(card))}" target="_blank" rel="noopener">${clearing ? 'Remove everywhere' : 'Save to all devices'} ↗</a><span class="limit-sync-hint">opens a GitHub form; submit it and every device updates in about a minute</span></span>`;
  }

  function openLimitEditor(row, card) {
    const t = card.analysis && card.analysis.tiers;
    const start = getLimit(card) || (t && t.buy_upper) || lowestAsk(card) || '';
    row.innerHTML = `<span class="limit-lbl">My limit</span> ¥<input type="number" class="limit-input" inputmode="numeric" min="${LIMIT_STEP}" step="${LIMIT_STEP}" value="${start}">
      <button type="button" class="limit-btn primary" data-act="save">Save</button><button type="button" class="limit-btn" data-act="cancel">Cancel</button>
      <span class="limit-hint">${t ? `Buy line is ${fmtYen(t.buy_upper)}. ` : ''}Rounded to ¥${LIMIT_STEP}; drag the gold handle on the bar to fine-tune.</span>
      <span class="limit-live"></span>`;
    const input = row.querySelector('.limit-input');
    const live = row.querySelector('.limit-live');
    const showOdds = () => {
      const v = Math.round(Number(input.value) / LIMIT_STEP) * LIMIT_STEP;
      const o = v > 0 ? touchOdds(card, v) : null;
      live.textContent = !o ? '' : o.reached ? 'A listing is already at or below this.'
        : `Chance of a listing at ≤${fmtYen(v)}: ${fmtOdds(o.p30)} in 30 days · ${fmtOdds(o.p90)} in 90 days`;
    };
    input.addEventListener('input', showOdds);
    showOdds();
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
    const validCards = sortCardsBy(cards.filter((c) => c.grades && c.grades.psa10 && c.grades.psa10.lowest_price != null), TABLE_SORTS, tableSort);

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
    wireTableSort();
  }

  function buildDiyTable(entries) {
    if (!entries.length) return null;
    const thead = '<thead><tr><th></th>' + entries.map((e) => `<th>${escapeHtml(e.card.card_name_ja)}</th>`).join('') + '</tr></thead>';

    let rows = '';
    rows += `<tr><td>${sortableLabel('price', 'Buy the slab (PSA10)')}</td>` + entries.map((e) => `<td>${fmtYen(e.repPrice)}${e.card.analysis && e.card.analysis.price_source === 'sales_confirmed' ? ' <em>(sales-confirmed)</em>' : ''}</td>`).join('') + '</tr>';
    rows += `<tr><td>${sortableLabel('raw', 'Buy raw A-rank')}</td>` + entries.map((e) => `<td>${fmtYen(e.diy.rawPrice)}</td>`).join('') + '</tr>';
    rows += '<tr><td>Raw + grade it yourself (expected cost)</td>' + entries.map((e) => `<td>${fmtYen(e.diy.diyExpected)}</td>`).join('') + '</tr>';
    rows += `<tr><td>${sortableLabel('diy', 'vs. just buying the slab')}</td>` + entries.map((e) => `<td>${e.diy.delta >= 0 ? '+' : '−'}${fmtYen(Math.abs(e.diy.delta))}</td>`).join('') + '</tr>';

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
    const thead = `<thead><tr><th>${sortableLabel('name', 'Card')}</th>` + cards.map((c) => `<th>${escapeHtml(c.card_name_ja)}</th>`).join('') + '</tr></thead>';

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

    const ROW_KEYS = { 'Current PSA10': 'price', 'Order-book depth': 'depth', 'Favorite count': 'favorites', 'Population / gem rate': 'population', 'Off peak (where known)': 'offpeak' };
    let body = rowsData.map(([label, vals]) => `<tr><td>${ROW_KEYS[label] ? sortableLabel(ROW_KEYS[label], label) : label}</td>${vals.map((v) => `<td>${v}</td>`).join('')}</tr>`).join('');
    body += `<tr><td>${sortableLabel('chg7', '7-day change')}</td>${cards.map((c) => { const x = priceChangeAgo(c, 7); return `<td class="${x ? dirClass(x.pct) : ''}">${x ? fmtPct(x.pct) : '—'}</td>`; }).join('')}</tr>`;
    body += `<tr><td>${sortableLabel('chg30', '30-day change')}</td>${cards.map((c) => { const x = priceChangeAgo(c, 30); return `<td class="${x ? dirClass(x.pct) : ''}">${x ? fmtPct(x.pct) : '—'}</td>`; }).join('')}</tr>`;
    body += `<tr><td>${sortableLabel('heat', 'PSA10 sales / day')}</td>${cards.map((c) => { const h = heatOf(c); return `<td>${h && h.psa ? rateTxt(h.psa) + ' ' + heatChip(c) : '—'}</td>`; }).join('')}</tr>`;

    body += `<tr class="divider"><td colspan="${cards.length + 1}">PSA10 price tiers</td></tr>`;
    const tierRow = (label, fn) => `<tr><td>${label}</td>${cards.map((c) => { const t = c.analysis && c.analysis.tiers; return `<td>${t ? fn(t) : 'Not yet established'}</td>`; }).join('')}</tr>`;
    body += tierRow('Definitely-buy', (t) => '≤' + fmtYen(t.definitely_buy));
    body += tierRow('Buy', (t) => fmtYen(t.definitely_buy) + '–' + fmtYen(t.buy_upper));
    body += tierRow('Watch closely', (t) => fmtYen(t.buy_upper) + '–' + fmtYen(t.ceiling));
    body += tierRow("Don't-buy ceiling", (t) => fmtYen(t.ceiling));

    body += `<tr><td>${sortableLabel('verdict', 'Verdict')}</td>${cards.map((c) => {
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

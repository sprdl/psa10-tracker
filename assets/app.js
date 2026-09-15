(function () {
  'use strict';

  const state = {
    manifest: null,
    currentIndex: -1, // index into manifest.snapshots (chronological ascending)
    currentData: null,
    previousData: null,
  };

  const els = {
    snapshotSelect: document.getElementById('snapshot-select'),
    collectedAt: document.getElementById('collected-at'),
    marketStrip: document.getElementById('market-strip'),
    notesBody: document.getElementById('notes-body'),
    cards: document.getElementById('cards'),
  };

  function fmtYen(n) {
    if (n === null || n === undefined || isNaN(n)) return '—';
    return '¥' + Math.round(n).toLocaleString('en-US');
  }

  function fmtPct(n, digits) {
    if (n === null || n === undefined || isNaN(n)) return '—';
    const d = digits === undefined ? 1 : digits;
    const sign = n > 0 ? '+' : '';
    return sign + n.toFixed(d) + '%';
  }

  function fmtDateJST(iso) {
    // iso like 2026-09-15T16:26:00+09:00 -- display as-is, no TZ conversion needed
    const m = iso.match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/);
    if (!m) return iso;
    const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
    const [, y, mo, d, h, mi] = m;
    return `${months[parseInt(mo, 10) - 1]} ${parseInt(d, 10)}, ${y} ${h}:${mi} JST`;
  }

  function fmtDateShort(iso) {
    const m = iso.match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/);
    if (!m) return iso;
    const [, y, mo, d, h, mi] = m;
    return `${y}/${mo}/${d} ${h}:${mi}`;
  }

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
      return;
    }

    const snaps = state.manifest.snapshots || [];
    if (!snaps.length) {
      els.cards.innerHTML = `<div class="empty-state">No snapshots yet — run add_snapshot to publish the first one.</div>`;
      return;
    }

    // populate the select, newest first
    els.snapshotSelect.innerHTML = '';
    for (let i = snaps.length - 1; i >= 0; i--) {
      const opt = document.createElement('option');
      opt.value = String(i);
      opt.textContent = fmtDateShort(snaps[i].collected_at_jst);
      els.snapshotSelect.appendChild(opt);
    }
    els.snapshotSelect.value = String(snaps.length - 1);

    els.snapshotSelect.addEventListener('change', () => {
      loadIndex(parseInt(els.snapshotSelect.value, 10));
    });

    await loadIndex(snaps.length - 1);
  }

  async function loadIndex(idx) {
    const snaps = state.manifest.snapshots;
    state.currentIndex = idx;
    state.currentData = await fetchJSON('data/snapshots/' + snaps[idx].file);
    state.previousData = idx > 0 ? await fetchJSON('data/snapshots/' + snaps[idx - 1].file) : null;
    render();
  }

  function findPrevCard(url) {
    if (!state.previousData) return null;
    return (state.previousData.cards || []).find((c) => c.url === url) || null;
  }

  function render() {
    const data = state.currentData;
    els.collectedAt.textContent = fmtDateJST(data.collected_at_jst);
    renderMarketStrip(data.pokeca_chart_index);
    els.notesBody.textContent = data.notes || '';
    renderCards(data.cards || []);
  }

  function renderMarketStrip(idx) {
    if (!idx) {
      els.marketStrip.innerHTML = '';
      return;
    }
    const psa10 = idx.psa10 || {};
    const raw = idx.raw_bihin || {};
    els.marketStrip.innerHTML = `
      <div class="cell">
        <div class="k">PSA10 index</div>
        <div class="v">${fmtYen(psa10.latest_index_value_jpy)}</div>
        <div class="d ${dirClass(psa10.day_change_pct)}">${fmtPct(psa10.day_change_pct)} day</div>
      </div>
      <div class="cell">
        <div class="k">Raw A-rank index</div>
        <div class="v">${fmtYen(raw.latest_index_value_jpy)}</div>
        <div class="d ${dirClass(raw.day_change_pct)}">${fmtPct(raw.day_change_pct)} day</div>
      </div>
      <div class="cell">
        <div class="k">PSA10 momentum</div>
        <div class="v">${fmtPct(psa10.month_change_pct)}</div>
        <div class="d">month · ${fmtPct(psa10.year_change_pct)} year</div>
      </div>
      <div class="cell">
        <div class="k">Volume trend</div>
        <div class="v" style="font-size:1rem; text-transform:capitalize;">${psa10.volume_trend || '—'}</div>
        <div class="d">vs raw: ${raw.volume_trend || '—'}</div>
      </div>
    `;
  }

  function dirClass(pct) {
    if (pct === null || pct === undefined || isNaN(pct) || pct === 0) return '';
    return pct > 0 ? 'pos' : 'neg';
  }

  function depthInfo(grade) {
    const within = grade.count_within_15pct || 0;
    const total = (grade.top20_cheapest_listings || []).length || 20;
    const ratio = within / total;
    let cls = 'depth-thin';
    if (ratio >= 0.5) cls = 'depth-tight';
    else if (ratio >= 0.2) cls = 'depth-mid';
    return { within, total, ratio, cls };
  }

  function renderCards(cards) {
    els.cards.innerHTML = '';
    cards.forEach((card, i) => {
      const psa10 = card.grades && card.grades.psa10;
      if (!psa10) return;
      const depth = depthInfo(psa10);
      const prev = findPrevCard(card.url);
      const prevPsa10 = prev && prev.grades && prev.grades.psa10;

      let deltaHtml = '<span class="flat">first snapshot on file</span>';
      if (prevPsa10 && typeof prevPsa10.lowest_price === 'number') {
        const diff = psa10.lowest_price - prevPsa10.lowest_price;
        const pct = (diff / prevPsa10.lowest_price) * 100;
        if (diff === 0) {
          deltaHtml = '<span class="flat">unchanged</span> since last check';
        } else {
          const cls = diff > 0 ? 'up' : 'down';
          const arrow = diff > 0 ? '▲' : '▼';
          deltaHtml = `<span class="${cls}">${arrow} ${fmtPct(pct)}</span> since last check (${fmtYen(prevPsa10.lowest_price)})`;
        }
      }

      const article = document.createElement('article');
      article.className = `card ${depth.cls}`;
      article.innerHTML = `
        <div class="card-summary" data-idx="${i}">
          <div class="eyebrow">
            <span>Pop. ${card.psa10_population != null ? card.psa10_population.toLocaleString() : '—'} · gem rate ${card.psa10_gem_rate_pct != null ? card.psa10_gem_rate_pct + '%' : '—'}</span>
            <svg class="chevron" width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M6 9l6 6 6-6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
          </div>
          <h2>${escapeHtml(card.card_name_ja)}</h2>
          <div class="subtitle">♥ ${card.favorite_count != null ? card.favorite_count.toLocaleString() : '—'} favorites</div>
          <div class="price-row"><span class="price">${fmtYen(psa10.lowest_price)}</span><span class="label">lowest PSA10 ask</span></div>
          <div class="delta-line">${deltaHtml}</div>
          <div class="card-stats">
            <div>
              <div class="stat-label">Listing depth (within 15% of lowest)</div>
              <div class="stat-value">${depth.within}/${depth.total}</div>
              <div class="depth-bar-track"><div class="depth-bar-fill" style="width:${Math.round(depth.ratio * 100)}%"></div></div>
            </div>
            <div>
              <div class="stat-label">Raw A lowest</div>
              <div class="stat-value">${card.grades.raw_a_grade ? fmtYen(card.grades.raw_a_grade.lowest_price) : '—'}</div>
            </div>
          </div>
        </div>
        <div class="card-detail" id="detail-${i}" hidden></div>
      `;

      const summary = article.querySelector('.card-summary');
      summary.addEventListener('click', () => toggleCard(article, i, card));

      els.cards.appendChild(article);
    });
  }

  function toggleCard(article, i, card) {
    const detail = article.querySelector('.card-detail');
    const isOpen = article.classList.contains('expanded');
    if (isOpen) {
      article.classList.remove('expanded');
      detail.hidden = true;
      return;
    }
    if (!detail.dataset.built) {
      detail.innerHTML = buildDetailHtml(card);
      detail.dataset.built = '1';
    }
    article.classList.add('expanded');
    detail.hidden = false;
  }

  function buildDetailHtml(card) {
    const psa10 = card.grades.psa10;
    const raw = card.grades.raw_a_grade;
    let html = '';
    html += buildGradeDetail('PSA10', psa10);
    if (raw) html += buildGradeDetail('Raw A-rank', raw);
    html += `<a class="card-link" href="${card.url}" target="_blank" rel="noopener">View on SNKRDUNK ↗</a>`;
    return html;
  }

  function buildGradeDetail(label, grade) {
    const listings = grade.top20_cheapest_listings || [];
    const withinSet = new Set(grade.listings_within_15pct_of_lowest || []);
    let usedWithin = 0;
    const chips = listings.map((p) => {
      let isWithin = false;
      if (withinSet.has(p) && usedWithin < (grade.listings_within_15pct_of_lowest || []).length) {
        // naive membership check is fine since duplicates are rare edge cases
        isWithin = true;
      }
      return `<span class="chip ${isWithin ? 'within' : 'excluded'}">${fmtYen(p)}</span>`;
    }).join('');

    const sales = grade.recent_completed_sales || [];
    const sparkline = buildSparkline(sales.map((s) => s.price));
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
        <div class="listing-chips">${chips}</div>
        ${sales.length ? `<div class="sparkline-wrap">${sparkline}</div>` : ''}
        ${sales.length ? `<ul class="sales-list">${salesList}</ul>` : ''}
      </div>
    `;
  }

  function buildSparkline(prices) {
    if (!prices.length) return '';
    const w = 600, h = 48, pad = 4;
    const min = Math.min(...prices), max = Math.max(...prices);
    const range = max - min || 1;
    const step = prices.length > 1 ? (w - pad * 2) / (prices.length - 1) : 0;
    const points = prices.map((p, i) => {
      const x = pad + i * step;
      const y = h - pad - ((p - min) / range) * (h - pad * 2);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(' ');
    const trendUp = prices[prices.length - 1] > prices[0];
    const color = trendUp ? '#b15b49' : '#5fa377';
    return `<svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none"><polyline points="${points}" fill="none" stroke="${color}" stroke-width="2" vector-effect="non-scaling-stroke"/></svg>`;
  }

  function escapeHtml(str) {
    if (str === null || str === undefined) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  init();
})();

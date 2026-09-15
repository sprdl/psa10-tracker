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
    banners: document.getElementById('banners'),
    notesBody: document.getElementById('notes-body'),
    cards: document.getElementById('cards'),
  };

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
      return;
    }

    const snaps = state.manifest.snapshots || [];
    if (!snaps.length) {
      els.cards.innerHTML = `<div class="empty-state">No snapshots yet — run add_snapshot to publish the first one.</div>`;
      return;
    }

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
        <div class="d ${dirClass(psa10.day_change_pct)}">${fmtPct(psa10.day_change_pct)} day</div>
      </div>
      <div class="cell">
        <div class="k">Raw A-rank index</div>
        <div class="v">${fmtYen(raw.latest_index_value_jpy)}</div>
        <div class="d ${dirClass(raw.day_change_pct)}">${fmtPct(raw.day_change_pct)} day</div>
      </div>
      <div class="cell">
        <div class="k">Both indices' volume</div>
        <div class="v" style="font-size:1rem; text-transform:capitalize;">${psa10.volume_trend || '—'}</div>
        <div class="d">vs raw: ${raw.volume_trend || '—'}</div>
      </div>
      ${fourthCell}
    `;
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

  // ---------- render: cards ----------

  function render() {
    const data = state.currentData;
    const prevCards = (state.previousData && state.previousData.cards) || [];
    els.collectedAt.textContent = fmtDateJST(data.collected_at_jst);
    renderMarketStrip(data);
    renderBanners(data, state.previousData);
    els.notesBody.textContent = data.notes || '';
    renderCards(data.cards || [], prevCards);
    renderTables(data.cards || [], prevCards);
  }

  function renderCards(cards, prevCards) {
    els.cards.innerHTML = '';
    cards.forEach((card, i) => {
      const psa10 = card.grades && card.grades.psa10;
      if (!psa10) return;
      const prevCard = prevCards.find((c) => c.url === card.url) || null;
      const depth = depthInfo(psa10);
      const analysis = card.analysis;

      let cardClass = 'card';
      if (analysis && analysis.verdict && analysis.verdict.tag) cardClass += ' verdict-' + analysis.verdict.tag;
      else cardClass += ' ' + depth.cls;

      const article = document.createElement('article');
      article.className = cardClass;
      article.innerHTML = buildCardSummaryHtml(card, prevCard, i, depth);

      const summary = article.querySelector('.card-summary');
      summary.addEventListener('click', () => toggleCard(article, i, card));
      els.cards.appendChild(article);
    });
  }

  function buildCardSummaryHtml(card, prevCard, i, depth) {
    const psa10 = card.grades.psa10;
    const analysis = card.analysis || null;
    const repPrice = getRep(card);

    let flagHtml = '';
    if (analysis && analysis.price_source) {
      const confirmed = analysis.price_source === 'sales_confirmed';
      flagHtml = `<span class="price-flag ${confirmed ? '' : 'unconfirmed'}">${confirmed ? 'sales-confirmed' : analysis.price_source.replace(/_/g, ' ')}</span>`;
    }

    let offPeakHtml;
    const peak = analysis && analysis.peak;
    if (peak && peak.price) {
      const pct = computeOffPeakPct(peak.price, repPrice);
      offPeakHtml = `<div class="off-peak">Peak was ${fmtYen(peak.price)}${peak.when ? ' (' + escapeHtml(peak.when) + ')' : ''} — <span class="pct">${pct >= 0 ? '−' : '+'}${Math.abs(pct).toFixed(0)}%</span> off the high</div>`;
    } else {
      offPeakHtml = `<div class="off-peak">No price history pulled yet — peak unknown</div>`;
    }

    let deltaHtml = '<span class="flat">first snapshot on file</span>';
    if (prevCard) {
      const prevRep = getRep(prevCard);
      if (prevRep != null && repPrice != null) {
        const diff = repPrice - prevRep;
        const pct = prevRep ? (diff / prevRep) * 100 : 0;
        if (diff === 0) deltaHtml = '<span class="flat">unchanged</span> since last check';
        else {
          const cls = diff > 0 ? 'up' : 'down';
          const arrow = diff > 0 ? '▲' : '▼';
          deltaHtml = `<span class="${cls}">${arrow} ${fmtPct(pct)}</span> since last check (${fmtYen(prevRep)})`;
        }
      }
    }

    let gaugeHtml = '';
    if (analysis && analysis.tiers && peak && peak.price) {
      const g = computeGauge(analysis.tiers, peak.price, repPrice);
      if (g) {
        gaugeHtml = `
          <div class="gauge-wrap">
            <div class="gauge-track">
              <div class="gauge-fill" style="background: linear-gradient(to right,
                var(--green-strong) 0%, var(--green-strong) ${g.dbPct.toFixed(1)}%,
                var(--green) ${g.dbPct.toFixed(1)}%, var(--green) ${g.buPct.toFixed(1)}%,
                var(--amber) ${g.buPct.toFixed(1)}%, var(--amber) ${g.watchMidPct.toFixed(1)}%,
                var(--amber-strong) ${g.watchMidPct.toFixed(1)}%, var(--amber-strong) ${g.ceilPct.toFixed(1)}%,
                var(--red) ${g.ceilPct.toFixed(1)}%, var(--red) 100%);"></div>
              <div class="marker" style="left:${g.curPct.toFixed(1)}%"><div class="tag">${fmtYenShort(repPrice)}</div><div class="stem"></div></div>
              <div class="marker peak" style="left:${g.peakPct.toFixed(1)}%"><div class="tag">${fmtYenShort(peak.price)}</div><div class="stem"></div></div>
            </div>
            <div class="gauge-labels"><span>¥0</span><span>${fmtYen(g.scaleMax)}</span></div>
          </div>`;
      }
    }

    let favHtml = card.favorite_count != null ? card.favorite_count.toLocaleString() : '—';
    if (prevCard && prevCard.favorite_count != null && card.favorite_count != null) {
      const fdiff = card.favorite_count - prevCard.favorite_count;
      if (fdiff !== 0) favHtml += ` <span class="${fdiff > 0 ? 'up' : 'down'}" style="font-size:0.75em;">${fdiff > 0 ? '▲' : '▼'}</span>`;
    }

    const basicStatsHtml = gaugeHtml ? '' : `
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
      </div>`;

    const extendedStatsHtml = gaugeHtml ? `
      <div class="card-stats">
        <div><div class="stat-label">Order-book depth</div><div class="stat-value">${depth.within}/${depth.total}</div></div>
        <div><div class="stat-label">Recent sales range</div><div class="stat-value">${salesRangeText(psa10.recent_completed_sales)}</div></div>
        <div><div class="stat-label">Favorite count</div><div class="stat-value">${favHtml}</div></div>
        <div><div class="stat-label">Population / gem rate</div><div class="stat-value">${card.psa10_population != null ? card.psa10_population.toLocaleString() : '—'} · ${card.psa10_gem_rate_pct != null ? card.psa10_gem_rate_pct + '%' : '—'}</div></div>
      </div>` : '';

    let verdictHtml;
    if (analysis && analysis.verdict) {
      verdictHtml = `<div class="verdict-line"><span class="verdict-tag ${analysis.verdict.tag}">${escapeHtml(analysis.verdict.label || analysis.verdict.tag)}</span><div>${escapeHtml(analysis.verdict.reasoning || '')}</div></div>`;
    } else {
      verdictHtml = `<div class="tier-pending">Tiers not yet established for this card — showing raw stats only.</div>`;
    }

    return `
      <div class="card-summary" data-idx="${i}">
        <div class="eyebrow">
          <span>Pop. ${card.psa10_population != null ? card.psa10_population.toLocaleString() : '—'} · gem rate ${card.psa10_gem_rate_pct != null ? card.psa10_gem_rate_pct + '%' : '—'}</span>
          <svg class="chevron" width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M6 9l6 6 6-6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
        </div>
        <h2>${escapeHtml(card.card_name_ja)}</h2>
        <div class="subtitle">♥ ${card.favorite_count != null ? card.favorite_count.toLocaleString() : '—'} favorites</div>
        <div class="price-row"><span class="price">${fmtYen(repPrice)}</span><span class="label">${analysis && analysis.representative_price != null ? 'representative PSA10 price' : 'lowest PSA10 ask'}</span>${flagHtml}</div>
        ${offPeakHtml}
        <div class="delta-line">${deltaHtml}</div>
        ${gaugeHtml}
        ${basicStatsHtml}
        ${extendedStatsHtml}
        ${verdictHtml}
      </div>
      <div class="card-detail" id="detail-${i}" hidden></div>
    `;
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
    const chips = listings.map((p) => {
      const isWithin = withinSet.has(p);
      return `<span class="chip ${isWithin ? 'within' : 'excluded'}">${fmtYen(p)}</span>`;
    }).join('');

    const sales = grade.recent_completed_sales || [];
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
        <div class="listing-chips">${chips}</div>
        ${sales.length ? sparkline : ''}
        ${sales.length ? `<ul class="sales-list">${salesList}</ul>` : ''}
      </div>
    `;
  }

  // Sparkline with price labels (min/max, drawn on the chart) and date labels
  // (oldest/newest "when" strings, drawn below it) — oldest is left, newest is right,
  // matching the order recent_completed_sales is already given in.
  function buildSparkline(sales) {
    if (!sales.length) return '';
    const prices = sales.map((s) => s.price);
    const w = 600, h = 70, padX = 4, padTop = 16, padBottom = 4;
    const min = Math.min(...prices), max = Math.max(...prices);
    const range = max - min || 1;
    const plotH = h - padTop - padBottom;
    const step = prices.length > 1 ? (w - padX * 2) / (prices.length - 1) : 0;
    const points = prices.map((p, i) => {
      const x = padX + i * step;
      const y = padTop + plotH - ((p - min) / range) * plotH;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(' ');
    const trendUp = prices[prices.length - 1] > prices[0];
    const color = trendUp ? 'var(--red)' : 'var(--green)';
    const minY = padTop + plotH;

    const svg = `<svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none">
      <line x1="${padX}" y1="${padTop}" x2="${w - padX}" y2="${padTop}" class="spark-grid" />
      <line x1="${padX}" y1="${minY}" x2="${w - padX}" y2="${minY}" class="spark-grid" />
      <text x="${padX}" y="${padTop - 4}" class="spark-price-label">${fmtYen(max)}</text>
      <text x="${padX}" y="${h}" class="spark-price-label">${fmtYen(min)}</text>
      <polyline class="spark-line" points="${points}" style="stroke:${color}" />
    </svg>`;

    const dateLabels = `<div class="spark-date-labels"><span>${escapeHtml(sales[0].when)}</span><span>${escapeHtml(sales[sales.length - 1].when)}</span></div>`;

    return `<div class="sparkline-wrap">${svg}</div>${dateLabels}`;
  }

  // ---------- render: tables ----------

  function renderTables(cards, prevCards) {
    const validCards = cards.filter((c) => c.grades && c.grades.psa10);

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
      if (c.analysis && c.analysis.verdict) return `<td><span class="pill ${c.analysis.verdict.tag}">${escapeHtml(c.analysis.verdict.label || c.analysis.verdict.tag)}</span></td>`;
      return '<td>—</td>';
    }).join('')}</tr>`;

    return thead + '<tbody>' + body + '</tbody>';
  }

  init();
})();

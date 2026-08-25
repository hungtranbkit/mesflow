// Kiosk trình chiếu năng suất nhân viên -- read-only TV/wallboard screen.
// Standalone (no app.js/sidebar dependency), mirrors kiosk.js's isolation.
//
// Two data sources, chosen by the URL, never mixed:
//   - Real route (/kiosk/employee-productivity, no query params): fetches
//     the PUBLIC /api/wallboard/employee-productivity, which server-side
//     reads whatever the Report screen last Published. No filters are ever
//     read from this page's own URL/inputs -- there are none.
//   - Preview (?preview=1&from=...&to=...&department=...&sort=...&
//     employees_per_page=...&columns=...&auto_page_flip=...&
//     auto_page_flip_seconds=...&refresh=...), opened from the Report
//     screen while still logged in: calls the SAME authenticated
//     /api/reports/employee-productivity the Report page itself uses, with
//     those still-unsaved filter values -- so Preview can never change the
//     public config (it never calls the publish endpoint at all).
// Either way, the percentage/aggregation itself always comes from
// ReportRepository.employee_productivity() -- this file only renders.
//
// Completed-session-only, same rule as the Report (2026-08-22 revision):
// there is no running-session/active-worker/online concept anywhere on
// this screen -- employee_productivity() itself never returns one any
// more, so there is nothing here to filter out. It only ever shows
// results of Work Sessions that have already ended.

// --- Pure display-settings logic (2026-08-23 revision) --------------------
// Pulled out of the IIFE below so it can be unit-tested directly under Node
// (see tests/test_employee_productivity_display_settings.py) without a
// browser/DOM -- the module.exports guard is a no-op in the browser
// (`module` is undefined there) so this changes nothing at runtime.

const PRODUCTIVITY_MIN_CARD_WIDTH = 300; // px -- "3 columns must not go unreadably narrow" floor
const PRODUCTIVITY_CARD_GAP = 24; // px, matches --gap used in wallboard.css .wb-list

// columns: 'auto' | 1 | 2 | 3 (or their string forms, e.g. from a URL param
// or a JSON round-trip). viewportWidth: window.innerWidth in practice.
function computeProductivityColumns(viewportWidth, columns) {
  const w = Number(viewportWidth) || 0;
  let cols;
  if (columns === 'auto' || columns === undefined || columns === null || columns === '') {
    cols = w >= 1400 ? 3 : w >= 900 ? 2 : 1; // AUTO COLUMN RULES thresholds
  } else {
    cols = Math.round(Number(columns)) || 1;
  }
  cols = Math.max(1, Math.min(3, cols));
  // Responsive safety: even an explicit user choice of 3 (or AUTO's own
  // pick) must not produce cards narrower than PRODUCTIVITY_MIN_CARD_WIDTH.
  while (cols > 1 && (w - (cols - 1) * PRODUCTIVITY_CARD_GAP) / cols < PRODUCTIVITY_MIN_CARD_WIDTH) {
    cols -= 1;
  }
  return cols;
}

function productivityPageCount(totalEmployees, employeesPerPage) {
  const size = Math.max(1, Number(employeesPerPage) || 1);
  return Math.max(1, Math.ceil(Math.max(0, Number(totalEmployees) || 0) / size));
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { computeProductivityColumns, productivityPageCount, PRODUCTIVITY_MIN_CARD_WIDTH, PRODUCTIVITY_CARD_GAP };
}

(() => {
  // Lets this file be `require()`d under plain Node (see the pure-function
  // exports above and their test file) without a DOM/location -- the
  // browser always has `document`, so this never short-circuits there.
  if (typeof document === 'undefined') return;
  const params = new URLSearchParams(location.search);
  const isPreview = params.get('preview') === '1';
  const MIN_REFRESH_MS = 5000;
  // Display-settings defaults mirror WallboardConfigRepository.DEFAULTS
  // server-side -- kept in sync manually since Preview mode has no server
  // round-trip for these values (it builds its own config from the URL).
  const DISPLAY_DEFAULTS = { employees_per_page: 20, columns: 'auto', auto_page_flip: true, auto_page_flip_seconds: 10 };

  const SORTERS = {
    productivity_desc: (a, b) => (a.productivity_percent === null) - (b.productivity_percent === null) || (b.productivity_percent || 0) - (a.productivity_percent || 0),
    productivity_asc: (a, b) => (a.productivity_percent === null) - (b.productivity_percent === null) || (a.productivity_percent || 0) - (b.productivity_percent || 0),
    name_asc: (a, b) => String(a.employee_name || '').localeCompare(String(b.employee_name || ''), 'vi'),
    sessions_desc: (a, b) => b.completed_sessions - a.completed_sessions,
  };

  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])); }
  function pctText(v) { return v === null || v === undefined ? '—' : `${Number(v).toLocaleString('vi-VN', { minimumFractionDigits: 1, maximumFractionDigits: 2 })}%`; }
  function dur(seconds) {
    seconds = Math.max(0, Number(seconds || 0));
    const h = Math.floor(seconds / 3600), m = Math.floor((seconds % 3600) / 60);
    return h ? `${h}g ${String(m).padStart(2, '0')}p` : `${m}p`;
  }
  function dateShort(iso) {
    if (!iso) return '—';
    const parts = String(iso).split('-');
    return parts.length === 3 ? `${parts[2]}/${parts[1]}` : iso;
  }
  function nowHm() { return new Intl.DateTimeFormat('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh', hour: '2-digit', minute: '2-digit', hour12: false }).format(new Date()); }
  function boolParam(v, fallback) { return v === null || v === undefined || v === '' ? fallback : v !== '0' && v !== 'false'; }

  async function fetchPreview() {
    const qs = new URLSearchParams();
    ['from', 'to', 'department', 'team', 'employee_id'].forEach(k => { const v = params.get(k); if (v) qs.set(k, v); });
    const response = await fetch(`/api/reports/employee-productivity?${qs}`, { credentials: 'same-origin' });
    const body = await response.json().catch(() => ({}));
    if (!response.ok || body.ok === false) throw new Error(body.message || `HTTP ${response.status}`);
    const sort = params.get('sort') || 'productivity_desc';
    const employees = [...(body.employees || [])].sort(SORTERS[sort] || SORTERS.productivity_desc);
    return {
      configured: true,
      config: {
        sort,
        refresh_interval_seconds: Math.max(5, Number(params.get('refresh') || 20)),
        employees_per_page: Number(params.get('employees_per_page') || DISPLAY_DEFAULTS.employees_per_page),
        columns: params.get('columns') || DISPLAY_DEFAULTS.columns,
        auto_page_flip: boolParam(params.get('auto_page_flip'), DISPLAY_DEFAULTS.auto_page_flip),
        auto_page_flip_seconds: Number(params.get('auto_page_flip_seconds') || DISPLAY_DEFAULTS.auto_page_flip_seconds),
      },
      summary: body.summary,
      employees,
    };
  }

  async function fetchPublished() {
    const response = await fetch('/api/wallboard/employee-productivity', { credentials: 'same-origin' });
    const body = await response.json().catch(() => ({}));
    if (!response.ok || body.ok === false) throw new Error(body.message || `HTTP ${response.status}`);
    return body;
  }

  function drawKpis(summary) {
    // Completed-session-only wallboard (2026-08-22 revision): same 4 KPIs
    // as the Report screen, all from completed sessions -- no realtime
    // "who's working right now" card, no online/live indicator anywhere
    // on this screen (Section 7). It only ever shows finished results.
    const host = document.getElementById('wbKpis');
    if (!summary) { host.innerHTML = ''; return; }
    host.innerHTML = [
      ['Năng suất trung bình', pctText(summary.avg_employee_productivity_percent)],
      ['Nhân viên có dữ liệu', Number(summary.employee_count || 0).toLocaleString('vi-VN')],
      ['Session đã kết thúc', Number(summary.completed_sessions || 0).toLocaleString('vi-VN')],
      ['Tổng sản lượng đạt', Number(summary.total_good_qty || 0).toLocaleString('vi-VN')],
    ].map(([label, value]) => `<article class="wb-kpi"><small>${esc(label)}</small><strong>${value}</strong></article>`).join('');
  }

  // No progress bar (2026-08-23 revision): the % text itself is the only
  // visual indicator of standing. band() gives it a quick color/label the
  // same way the admin Report screen's assessment does, purely from the
  // already-computed productivity_percent -- no new formula.
  function band(pct) {
    if (pct === null || pct === undefined) return ['Chưa đủ dữ liệu', 'neutral'];
    if (pct >= 110) return ['Vượt định mức', 'good'];
    if (pct >= 90) return ['Đạt định mức', 'good'];
    if (pct >= 75) return ['Gần đạt', 'warn'];
    return ['Cần xem xét', 'bad'];
  }
  function rowHtml(x, rank) {
    const pct = x.productivity_percent;
    const [bandLabel, bandClass] = band(pct);
    const rankNo = String(rank).padStart(2, '0');
    // Sample size stays next to the percent even without the bar -- a lone
    // 100%/1-session score must never read the same as a well-sampled one.
    const sampleNote = pct === null ? 'Không đủ dữ liệu' : `${x.completed_sessions} session`;
    return `<article class="wb-card">
      <div class="wb-card-top">
        <span class="wb-card-rank">#${rankNo}</span>
        <span class="wb-card-name">${esc(x.employee_name)}</span>
        <span class="wb-card-pct ${bandClass}">${pctText(pct)}</span>
      </div>
      <div class="wb-card-sub">
        <span>${esc(x.employee_code)}${x.department ? ' · ' + esc(x.department) : ''} · ${esc(sampleNote)} · ${dur(x.worked_seconds)}</span>
        <span class="wb-card-band ${bandClass}">${esc(bandLabel)}</span>
      </div>
    </article>`;
  }

  const state = {
    page: 0, pageTimer: null, refreshTimer: null, resizeTimer: null, resumeTimer: null,
    lastEmployees: [], lastConfig: null, paused: false,
    employeesPerPage: DISPLAY_DEFAULTS.employees_per_page,
    columnsSetting: DISPLAY_DEFAULTS.columns,
    autoPageFlip: DISPLAY_DEFAULTS.auto_page_flip,
    autoPageFlipMs: DISPLAY_DEFAULTS.auto_page_flip_seconds * 1000,
  };

  function applyColumns() {
    const cols = computeProductivityColumns(window.innerWidth, state.columnsSetting);
    document.getElementById('wbList').style.setProperty('--productivity-columns', String(cols));
    return cols;
  }

  function drawEmpty(text) {
    document.getElementById('wbEmpty').hidden = false;
    document.getElementById('wbEmpty').textContent = text;
    document.getElementById('wbList').innerHTML = '';
    document.getElementById('wbPageIndicator').textContent = '';
    document.getElementById('wbPrev').hidden = true;
    document.getElementById('wbNext').hidden = true;
  }

  function drawPage() {
    applyColumns();
    const pageSize = Math.max(1, Number(state.employeesPerPage) || 20);
    const employees = state.lastEmployees;
    if (!employees.length) { drawEmpty('Chưa có dữ liệu năng suất trong khoảng đang chọn'); return; }
    document.getElementById('wbEmpty').hidden = true;
    const totalPages = productivityPageCount(employees.length, pageSize);
    state.page = ((state.page % totalPages) + totalPages) % totalPages;
    const start = state.page * pageSize;
    const slice = employees.slice(start, start + pageSize);
    document.getElementById('wbList').innerHTML = slice.map((x, i) => rowHtml(x, start + i + 1)).join('');
    const prevBtn = document.getElementById('wbPrev'), nextBtn = document.getElementById('wbNext');
    prevBtn.hidden = nextBtn.hidden = totalPages <= 1;
    document.getElementById('wbPageIndicator').textContent = totalPages > 1
      ? `${start + 1}–${start + slice.length} / ${employees.length} · Trang ${state.page + 1}/${totalPages}`
      : `${employees.length} nhân viên`;
  }

  function goToPage(delta) {
    const totalPages = productivityPageCount(state.lastEmployees.length, state.employeesPerPage);
    if (totalPages <= 1) return;
    state.page = ((state.page + delta) % totalPages + totalPages) % totalPages;
    drawPage();
    startPaging(); // manual nav resets the auto-flip timer
  }
  document.getElementById('wbPrev').addEventListener('click', () => goToPage(-1));
  document.getElementById('wbNext').addEventListener('click', () => goToPage(1));

  function startPaging() {
    clearInterval(state.pageTimer);
    state.pageTimer = null;
    // "If total employees <= page size: show one page and disable auto
    // flip" -- and the config-level auto_page_flip toggle, both gate here.
    const totalPages = productivityPageCount(state.lastEmployees.length, state.employeesPerPage);
    if (!state.autoPageFlip || totalPages <= 1) return;
    state.pageTimer = setInterval(() => {
      if (state.paused || document.hidden) return; // pause on interaction / hidden tab
      state.page += 1;
      drawPage();
    }, state.autoPageFlipMs);
  }

  // A TV wallboard has no mouse most of the time, but ?preview=1 is opened
  // in a real browser window by a manager. #wbShell covers the entire
  // viewport (100vw/100vh) -- there is no "outside" it to leave to, so a
  // mouseenter/mouseleave pair can never fire a real leave (worse, a
  // mouseenter fires the instant the page loads if the cursor is already
  // resting anywhere over the window, pausing auto-flip forever). Instead:
  // any interaction pauses, and it auto-resumes after a short idle window --
  // the same pattern a video player's on-screen controls use.
  const RESUME_AFTER_IDLE_MS = 4000;
  const wbShell = document.getElementById('wbShell');
  const markInteraction = () => {
    state.paused = true;
    clearTimeout(state.resumeTimer);
    state.resumeTimer = setTimeout(() => { state.paused = false; }, RESUME_AFTER_IDLE_MS);
  };
  wbShell.addEventListener('mousemove', markInteraction);
  wbShell.addEventListener('mousedown', markInteraction);
  wbShell.addEventListener('keydown', markInteraction);
  wbShell.addEventListener('focusin', markInteraction);

  // Viewport can change (window resize, a preview tab, a TV switching
  // orientation) -- recompute the AUTO/explicit column count and redraw
  // (page size itself never changes from a resize, only the column count).
  window.addEventListener('resize', () => {
    clearTimeout(state.resizeTimer);
    state.resizeTimer = setTimeout(() => { if (state.lastEmployees.length) drawPage(); }, 150);
  });

  function setConnState(text) {
    const el = document.getElementById('wbConnState');
    if (!text) { el.hidden = true; return; }
    el.hidden = false; el.textContent = text;
  }

  async function refresh() {
    try {
      const data = isPreview ? await fetchPreview() : await fetchPublished();
      setConnState('');
      if (!data.configured) {
        drawKpis(null);
        drawEmpty('Chưa cấu hình trình chiếu — vào Báo cáo năng suất nhân viên để Public lên Kiosk.');
        document.getElementById('wbRange').textContent = 'Chưa cấu hình';
        return schedule(20000);
      }
      const cfg = data.config || {};
      state.lastConfig = cfg;
      state.lastEmployees = data.employees || [];
      state.employeesPerPage = Number(cfg.employees_per_page) || DISPLAY_DEFAULTS.employees_per_page;
      state.columnsSetting = cfg.columns === undefined || cfg.columns === null || cfg.columns === '' ? DISPLAY_DEFAULTS.columns : cfg.columns;
      state.autoPageFlip = cfg.auto_page_flip !== undefined ? !!cfg.auto_page_flip : DISPLAY_DEFAULTS.auto_page_flip;
      state.autoPageFlipMs = Math.max(1000, Number(cfg.auto_page_flip_seconds || DISPLAY_DEFAULTS.auto_page_flip_seconds) * 1000);
      drawKpis(data.summary);
      const from = data.summary?.from, to = data.summary?.to;
      document.getElementById('wbRange').textContent = from && to ? `${dateShort(from)} → ${dateShort(to)}` : '';
      document.getElementById('wbUpdatedAt').textContent = `Cập nhật: ${nowHm()}`;
      drawPage();
      startPaging();
      schedule(Math.max(MIN_REFRESH_MS, Number(cfg.refresh_interval_seconds || 20) * 1000));
    } catch (e) {
      // Section 11: keep the last good render, small persistent banner --
      // never blank the screen on a transient API error.
      setConnState('Mất kết nối · đang thử lại');
      schedule(MIN_REFRESH_MS);
    }
  }

  function schedule(ms) {
    clearTimeout(state.refreshTimer);
    state.refreshTimer = setTimeout(refresh, ms);
  }

  if (isPreview) {
    const btn = document.getElementById('wbFullscreen');
    btn.hidden = false;
    btn.onclick = () => { document.documentElement.requestFullscreen?.().catch(() => {}); };
  }

  document.addEventListener('visibilitychange', () => {
    // A backgrounded TV tab still ticks (browsers throttle timers, not stop
    // them); refresh immediately on return so a long-backgrounded tab
    // doesn't sit on stale data until its next scheduled tick.
    if (document.visibilityState === 'visible') refresh();
  });

  refresh();
})();

// Kiosk trình chiếu năng suất nhân viên -- read-only TV/wallboard screen.
// Standalone (no app.js/sidebar dependency), mirrors kiosk.js's isolation.
//
// Two data sources, chosen by the URL, never mixed:
//   - Real route (/kiosk/employee-productivity, no query params): fetches
//     the PUBLIC /api/wallboard/employee-productivity, which server-side
//     reads whatever the Report screen last Published. No filters are ever
//     read from this page's own URL/inputs -- there are none.
//   - Preview (?preview=1&from=...&to=...&department=...&sort=...&
//     page_size=...&refresh=...), opened from the Report screen while
//     still logged in: calls the SAME authenticated
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

(() => {
  const params = new URLSearchParams(location.search);
  const isPreview = params.get('preview') === '1';
  const PAGE_ROTATE_MS = 12000;
  const MIN_REFRESH_MS = 5000;

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
        page_size: Math.max(1, Number(params.get('page_size') || 10)),
        refresh_interval_seconds: Math.max(5, Number(params.get('refresh') || 20)),
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

  function rowHtml(x) {
    const pct = x.productivity_percent;
    const barWidth = pct === null ? 0 : Math.min(Math.max(pct, 0), 100);
    const sampleNote = pct === null ? 'Không đủ dữ liệu' : `${x.completed_sessions} session`;
    return `<div class="wb-row">
      <span class="wb-row-name">${esc(x.employee_name)}<small>${esc(x.employee_code)}${x.department ? ' · ' + esc(x.department) : ''}</small></span>
      <span class="wb-row-pct">${pctText(pct)}</span>
      <span class="wb-row-bar"><i style="width:${barWidth}%"></i></span>
      <span class="wb-row-count">${esc(sampleNote)}</span>
    </div>`;
  }

  const state = { page: 0, pageTimer: null, refreshTimer: null, lastEmployees: [], lastConfig: null };

  function drawEmpty(text) {
    document.getElementById('wbEmpty').hidden = false;
    document.getElementById('wbEmpty').textContent = text;
    document.getElementById('wbList').innerHTML = '';
    document.getElementById('wbPageIndicator').textContent = '';
  }

  function drawPage() {
    const pageSize = Math.max(1, Number(state.lastConfig?.page_size || 10));
    const employees = state.lastEmployees;
    if (!employees.length) { drawEmpty('Chưa có dữ liệu năng suất trong khoảng đang chọn'); return; }
    document.getElementById('wbEmpty').hidden = true;
    const totalPages = Math.max(1, Math.ceil(employees.length / pageSize));
    state.page = state.page % totalPages;
    const start = state.page * pageSize;
    const slice = employees.slice(start, start + pageSize);
    document.getElementById('wbList').innerHTML = slice.map(rowHtml).join('');
    document.getElementById('wbPageIndicator').textContent = totalPages > 1
      ? `${start + 1}–${start + slice.length} / ${employees.length} · trang ${state.page + 1}/${totalPages}`
      : `${employees.length} nhân viên`;
  }

  function startPaging() {
    clearInterval(state.pageTimer);
    state.pageTimer = setInterval(() => { state.page += 1; drawPage(); }, PAGE_ROTATE_MS);
  }

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

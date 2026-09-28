// Năng suất -> tab "Operation" (UI consolidation P3).
//
// Replaces the raw renderSimple('KPI Operation','/api/kpi/operations') dump
// that `kpi-operations` used to be. Same page ID, same API, same permission
// (none -- any signed-in user, unchanged); only the screen is real now:
//   - filter bar (search / PO / trạng thái), same MFUI.filterBar as the
//     Nhân viên tab (pages/employee-productivity.js);
//   - KPI cards recalculated from the rows the active filters leave visible,
//     never from the unfiltered list;
//   - sortable table using the Nhân viên tab's .ep-table styles so both tabs
//     share one look and one responsive behavior.
// In refactor mode (?ui_refactor=1) core/canonical-nav.js shows this as the
// second tab of the canonical `productivity` screen. /api/kpi/operations has
// no date parameter, so there is deliberately no date filter here.

registerPage('kpi-operations', () => renderProductivityOperations());

// Filter state survives switching Nhân viên <-> Operation and back within the
// same page load (tab switches re-render the whole screen).
const kpoFilterMemory = { search: '', po: '', status: '', sortKey: 'updated', sortDir: 1 };

// Operation status wording, same vocabulary as the Production Order screen
// (app.js statusText); unknown codes fall back to the raw value.
const KPO_STATUS_LABELS = { DRAFT: 'Bản nháp', PLANNED: 'Kế hoạch', RELEASED: 'Sẵn sàng sản xuất', PENDING: 'Chờ', IN_PROGRESS: 'Đang sản xuất', RUNNING: 'Đang chạy', PAUSED: 'Tạm dừng', COMPLETED: 'Hoàn tất', DONE: 'Hoàn tất', CLOSED: 'Đã đóng', CANCELLED: 'Đã hủy' };
const kpoStatusLabel = s => KPO_STATUS_LABELS[String(s || '').toUpperCase()] || String(s || '—');

function kpoPct(value) {
  return value === null || value === undefined || !Number.isFinite(Number(value))
    ? '—'
    : `${Number(value).toLocaleString('vi-VN', { minimumFractionDigits: 1, maximumFractionDigits: 2 })}%`;
}

// Aggregates over the VISIBLE rows. Percentages are quantity-weighted
// (Σ đạt / Σ kế hoạch, Σ đạt / Σ (đạt + lỗi)), not an average of the
// per-operation percentages, so one tiny operation cannot swing the total.
function kpoSummary(rows) {
  const sum = key => rows.reduce((n, x) => n + Number(x[key] || 0), 0);
  const plan = sum('plan_qty'), done = sum('done_qty'), defect = sum('defect_qty');
  return {
    operation_count: rows.length,
    po_count: new Set(rows.map(x => x.po_code).filter(Boolean)).size,
    session_count: sum('session_count'),
    plan_qty: plan,
    done_qty: done,
    defect_qty: defect,
    completion_percent: plan > 0 ? done / plan * 100 : null,
    yield_percent: done + defect > 0 ? done / (done + defect) * 100 : null,
  };
}

function kpoFilterRows(items, { search = '', po = '', status = '' } = {}) {
  const q = String(search || '').trim().toLowerCase();
  return items.filter(x => (!po || x.po_code === po)
    && (!status || String(x.status || '') === status)
    && (!q || `${x.code || ''} ${x.name || ''} ${x.po_code || ''}`.toLowerCase().includes(q)));
}

async function renderProductivityOperations() {
  title.textContent = 'Năng suất';
  subtitle.textContent = 'Operation · tiến độ và tỷ lệ đạt theo bộ lọc';
  content.innerHTML = `<div class="page-shell mf-report" data-report="productivity" data-report-tab="operations">
    ${MFUI.reportBar({ tabs: MFUI.screenTabs({ screen: 'productivity', active: 'kpi-operations', canOpen: canOpenPage }), actions: '<button class="btn" id="kpoReload" type="button">Làm mới</button>' })}
    ${MFUI.filterBar({ content: `<label><span>Tìm Operation</span><input id="kpoSearch" placeholder="Mã, tên Operation hoặc PO"></label><label><span>PO</span><select id="kpoPo"><option value="">Tất cả PO</option></select></label><label><span>Trạng thái</span><select id="kpoStatus"><option value="">Tất cả trạng thái</option></select></label>`, clearId: 'kpoClear' })}
    <section class="mf-kpis" id="kpoKpis" aria-live="polite"></section>
    <section class="content-panel mf-table-panel"><div class="content-panel-head"><div><h3>Năng suất theo Operation</h3><p id="kpoRangeLabel"></p></div><span class="mf-count" id="kpoCount" aria-live="polite"></span></div><div class="content-panel-body" id="kpoTableHost">${MFUI.loadingState('Đang tải Operation…')}</div></section>
  </div>`;
  MFUI.bindScreenTabs(content, openPage);

  const mem = kpoFilterMemory;
  let items = [];
  let rows = [];

  const SORTERS = {
    updated: null, // API order: most recently updated first
    code: x => String(x.code || ''),
    po: x => String(x.po_code || ''),
    completion: x => Number(x.completion_percent ?? -Infinity),
    yield: x => Number(x.yield_percent ?? -Infinity),
    done: x => Number(x.done_qty || 0),
    sessions: x => Number(x.session_count || 0),
  };
  const sortRows = () => {
    const fn = SORTERS[mem.sortKey];
    if (!fn) return;
    rows.sort((a, b) => (fn(a) < fn(b) ? -1 : fn(a) > fn(b) ? 1 : 0) * mem.sortDir);
  };

  const n = v => Number(v || 0).toLocaleString('vi-VN');
  const drawKpis = s => {
    document.getElementById('kpoKpis').innerHTML = MFUI.kpiCards([
      { label: 'Operation', value: n(s.operation_count), context: `${n(s.po_count)} PO · ${n(s.session_count)} phiên làm việc` },
      { label: 'Hoàn thành', value: kpoPct(s.completion_percent), context: `Đạt ${n(s.done_qty)} / kế hoạch ${n(s.plan_qty)}`, tone: 'info' },
      { label: 'Tỷ lệ đạt', value: kpoPct(s.yield_percent), context: `Lỗi ${n(s.defect_qty)}`, tone: s.defect_qty ? 'warning' : '' },
      { label: 'Tổng sản lượng đạt', value: n(s.done_qty), context: `Trên ${n(s.operation_count)} Operation đang lọc` },
    ]);
  };

  const drawTable = () => {
    const host = document.getElementById('kpoTableHost');
    document.getElementById('kpoCount').textContent = items.length ? `${rows.length}/${items.length} Operation` : '';
    if (!rows.length) {
      host.innerHTML = items.length
        ? MFUI.emptyState('Không có Operation khớp bộ lọc', 'Đổi từ khoá, PO hoặc trạng thái, hoặc bấm "Xóa bộ lọc".')
        : MFUI.emptyState('Chưa có dữ liệu Operation');
      return;
    }
    host.innerHTML = `<div class="table-wrap mf-table-wrap"><table class="ep-table mf-table kpo-table">${MFUI.tableHead([
      { key: 'code', label: 'Operation' },
      { key: 'po', label: 'PO' },
      { label: 'Trạng thái', sortable: false },
      { key: 'done', label: 'Sản lượng đạt', num: true },
      { label: 'Lỗi', num: true, sortable: false },
      { label: 'Kế hoạch PO', num: true, sortable: false },
      { key: 'completion', label: 'Hoàn thành', num: true },
      { key: 'yield', label: 'Tỷ lệ đạt', num: true },
      { key: 'sessions', label: 'Phiên làm việc', num: true },
    ], { sortKey: mem.sortKey, sortDir: mem.sortDir })}<tbody>${rows.map(x => `<tr>
        <td class="mf-cell-id"><b>${esc(x.code)}</b><small>${esc(x.name || '')}</small></td>
        <td class="mf-mono">${esc(x.po_code || '—')}</td>
        <td>${MFUI.statusBadge(x.status, kpoStatusLabel(x.status))}</td>
        <td class="num"><b>${n(x.done_qty)}</b></td>
        <td class="num${Number(x.defect_qty) ? ' is-danger' : ''}">${n(x.defect_qty)}</td>
        <td class="num">${n(x.plan_qty)}</td>
        <td class="num"><b class="ep-pct">${kpoPct(x.completion_percent)}</b>${MFUI.meter(x.completion_percent)}</td>
        <td class="num">${kpoPct(x.yield_percent)}</td>
        <td class="num">${n(x.session_count)}</td>
      </tr>`).join('')}</tbody></table></div>`;
    host.querySelectorAll('th.sortable').forEach(th => th.onclick = () => {
      const key = th.dataset.sort;
      if (mem.sortKey === key) mem.sortDir *= -1; else { mem.sortKey = key; mem.sortDir = key === 'code' || key === 'po' ? 1 : -1; }
      applyFilters();
    });
  };

  const applyFilters = () => {
    mem.search = document.getElementById('kpoSearch').value || '';
    mem.po = document.getElementById('kpoPo').value;
    mem.status = document.getElementById('kpoStatus').value;
    rows = kpoFilterRows(items, mem);
    drawKpis(kpoSummary(rows));
    sortRows(); drawTable();
    const active = [mem.search.trim(), mem.po, mem.status].filter(Boolean).length;
    document.getElementById('kpoRangeLabel').textContent = `Hoàn thành = đạt / kế hoạch PO · Tỷ lệ đạt = đạt / (đạt + lỗi) · Operation cập nhật gần nhất${active ? ` · ${active} bộ lọc đang áp dụng` : ''}`;
  };

  const fillSelect = (id, values, allLabel, current, label = v => v) => {
    const sel = document.getElementById(id);
    sel.innerHTML = `<option value="">${allLabel}</option>` + values.map(v => `<option value="${esc(v)}">${esc(label(v))}</option>`).join('');
    sel.value = values.includes(current) ? current : '';
  };

  const load = async () => {
    const host = document.getElementById('kpoTableHost');
    host.innerHTML = MFUI.loadingState('Đang tải Operation…');
    try {
      const d = await api('/api/kpi/operations?limit=1000');
      items = d.items || [];
      fillSelect('kpoPo', [...new Set(items.map(x => x.po_code).filter(Boolean))].sort(), 'Tất cả PO', mem.po);
      fillSelect('kpoStatus', [...new Set(items.map(x => String(x.status || '')).filter(Boolean))].sort(), 'Tất cả trạng thái', mem.status, kpoStatusLabel);
      applyFilters();
    } catch (e) {
      document.getElementById('kpoCount').textContent = '';
      host.innerHTML = MFUI.errorState(e.message, 'kpoRetry');
      document.getElementById('kpoRetry').onclick = load;
    }
  };

  document.getElementById('kpoSearch').value = mem.search;
  document.getElementById('kpoSearch').oninput = () => applyFilters();
  document.getElementById('kpoPo').onchange = () => applyFilters();
  document.getElementById('kpoStatus').onchange = () => applyFilters();
  document.getElementById('kpoReload').onclick = load;
  document.getElementById('kpoClear').onclick = () => {
    document.getElementById('kpoSearch').value = '';
    document.getElementById('kpoPo').value = '';
    document.getElementById('kpoStatus').value = '';
    applyFilters();
  };

  await load();
}

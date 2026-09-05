// Báo cáo năng suất nhân viên -- new page, additive only:
// - Adds one entry to the "Điều hành" sidebar group + PAGE_PERMISSION in
//   app.js (menu/PAGE_PERMISSION are built into the sidebar DOM eagerly at
//   parse time, unlike renderTutorials()/attachGuideTabs(), so unlike
//   text-guide.js this one genuinely needs a small app.js edit -- nothing
//   else in app.js changes).
// - Everything else (openPage routing, rendering, the detail modal) lives
//   here, wired the same way pages/production-trace.js already wires a new
//   page id: capture the previous openPage, add one more `if`, delegate.

const openPageWithoutProductivity = openPage;
openPage = async function (id, btn) {
  if (id === 'employee-productivity') { setActive(btn || document.querySelector('[data-page="employee-productivity"]')); return renderEmployeeProductivity(); }
  return openPageWithoutProductivity(id, btn);
};

function productivityText(pct) {
  return pct === null || pct === undefined ? '—' : `${Number(pct).toLocaleString('vi-VN', { minimumFractionDigits: 1, maximumFractionDigits: 2 })}%`;
}
function epDur(seconds) {
  seconds = Math.max(0, Number(seconds || 0));
  const h = Math.floor(seconds / 3600), m = Math.floor((seconds % 3600) / 60);
  if (h) return `${h}g ${String(m).padStart(2, '0')}p`;
  return `${m}p`;
}
function epTodayHcm() {
  return new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Ho_Chi_Minh', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date());
}
function epMonthStartHcm() {
  const today = epTodayHcm();
  return `${today.slice(0, 7)}-01`;
}
function epDateShort(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? '—' : new Intl.DateTimeFormat('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh', day: '2-digit', month: '2-digit' }).format(d);
}
function epTimeShort(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? '—' : new Intl.DateTimeFormat('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh', hour: '2-digit', minute: '2-digit', hour12: false }).format(d);
}

async function renderEmployeeProductivity() {
  title.textContent = 'Báo cáo năng suất nhân viên';
  subtitle.textContent = 'Năng suất = trung bình cộng % hoàn thành các Session đã kết thúc của từng nhân viên trong khoảng ngày.';
  content.innerHTML = `<div class="page-shell">
    ${MFUI.filterBar({ content: `<label><span>Từ ngày</span><input type="date" id="epFrom" value="${epMonthStartHcm()}"></label><label><span>Đến ngày</span><input type="date" id="epTo" value="${epTodayHcm()}"></label><label><span>Tìm nhân viên</span><input id="epSearch" placeholder="Tên hoặc mã nhân viên"></label><label><span>Bộ phận</span><select id="epDept"><option value="">Tất cả bộ phận</option></select></label>`, actions: '<button class="btn primary" id="epReload">Làm mới</button>' })}
    <section class="daily-kpis" id="epKpis" aria-live="polite"></section>
    <!-- Section 21: giữ tách biệt khỏi filter bar phía trên -- panel riêng,
    không dùng chung state với bộ lọc bảng (epFrom/epTo/epDept chỉ ảnh hưởng
    bảng bên dưới cho tới khi bấm "Trình chiếu trên Kiosk"). -->
    <section class="content-panel wallboard-panel" id="epWbPanel">
      <div class="content-panel-head">
        <div><h3>Trình chiếu Kiosk</h3><p class="wallboard-hint">TV 1080p: nên dùng 24–30 nhân viên, 3 cột.</p></div>
      </div>
      <div class="content-panel-body">
        <p id="epWbState" class="wallboard-state">Đang tải trạng thái...</p>
        <div class="wallboard-config">
          <fieldset class="wallboard-group">
            <legend>Cấu hình hiển thị</legend>
            <div class="wallboard-field-grid">
              <label><span>Sắp xếp</span><select id="epWbSort">
                <option value="productivity_desc">Năng suất giảm dần</option>
                <option value="productivity_asc">Năng suất tăng dần</option>
                <option value="name_asc">Tên A→Z</option>
                <option value="sessions_desc">Số session giảm dần</option>
              </select></label>
              <label><span>Số nhân viên / trang</span><select id="epWbEmployeesPerPage">
                <option value="10">10</option><option value="12">12</option><option value="16">16</option>
                <option value="20" selected>20</option><option value="24">24</option><option value="30">30</option>
              </select></label>
              <label><span>Số cột</span><select id="epWbColumns">
                <option value="auto" selected>Tự động</option>
                <option value="1">1 cột</option><option value="2">2 cột</option><option value="3">3 cột</option>
              </select></label>
            </div>
          </fieldset>
          <fieldset class="wallboard-group wallboard-group-auto">
            <legend>Tự động hóa</legend>
            <div class="wallboard-toggle-row">
              <label class="wallboard-toggle"><input type="checkbox" id="epWbDynamicMtd" checked> <span>Tự động dùng đầu tháng → hôm nay</span></label>
              <label class="wallboard-toggle"><input type="checkbox" id="epWbAutoFlip" checked> <span>Tự động chuyển trang</span></label>
            </div>
            <div class="wallboard-field-grid">
              <label><span>Thời gian mỗi trang</span><select id="epWbFlipSeconds">
                <option value="5">5 giây</option><option value="10" selected>10 giây</option>
                <option value="15">15 giây</option><option value="30">30 giây</option>
              </select></label>
              <label><span>Làm mới dữ liệu (giây)</span><input type="number" id="epWbRefresh" min="5" max="300" value="20"></label>
            </div>
            <p class="wallboard-group-hint">Khi tắt "Tự động dùng đầu tháng → hôm nay", Kiosk dùng đúng khoảng "Từ ngày" / "Đến ngày" đang chọn ở bộ lọc phía trên.</p>
          </fieldset>
        </div>
        <div class="wallboard-actions">
          <p class="wallboard-actions-hint"><b>Xem trước</b>: mở thử ở tab mới bằng cấu hình đang chỉnh, không lưu lại. <b>Trình chiếu trên Kiosk</b>: áp dụng ngay cho màn hình Kiosk thật tại xưởng.</p>
          <div class="wallboard-actions-buttons">
            <button class="btn" id="epWbPreview" type="button">Xem trước</button>
            <button class="btn primary" id="epWbPublish" type="button">Trình chiếu trên Kiosk</button>
          </div>
        </div>
        <div id="epWbBody"></div>
      </div>
    </section>
    <section class="content-panel"><div class="content-panel-head"><div><h3>Năng suất theo nhân viên</h3><p id="epRangeLabel"></p></div></div><div class="content-panel-body" id="epTableHost">Đang tải...</div></section>
  </div>`;

  let rows = [];
  let sortKey = 'productivity_percent';
  let sortDir = -1; // section 6: mặc định giảm dần theo năng suất

  const SORTERS = {
    employee: x => String(x.employee_name || ''),
    session: x => x.completed_sessions,
    productivity: x => x.productivity_percent === null ? -Infinity : x.productivity_percent,
    output: x => x.good_qty,
    time: x => x.worked_seconds,
  };
  const sortRows = () => {
    const key = { productivity_percent: 'productivity', employee_name: 'employee', session: 'session', good_qty: 'output', worked_seconds: 'time' }[sortKey] || sortKey;
    const fn = SORTERS[key] || SORTERS.productivity;
    rows.sort((a, b) => (fn(a) < fn(b) ? -1 : fn(a) > fn(b) ? 1 : 0) * sortDir);
  };

  const drawKpis = summary => {
    // Completed-session-only report (2026-08-22 revision): exactly the 4
    // KPIs the task specifies, all derived from completed sessions --
    // no realtime "who's working right now" card of any kind, and the
    // backend summary for this endpoint no longer computes any such field.
    document.getElementById('epKpis').innerHTML = [
      ['Nhân viên có dữ liệu', summary.employee_count || 0, (summary.completed_sessions || 0) + ' session đã kết thúc'],
      ['Tổng Session đã kết thúc', summary.completed_sessions || 0, (summary.completed_invalid_sessions || 0) + ' không đủ dữ liệu định mức'],
      ['Năng suất trung bình', productivityText(summary.avg_employee_productivity_percent), 'Trung bình của từng nhân viên, không phải trung bình mọi session'],
      ['Tổng sản lượng đạt', summary.total_good_qty || 0, 'Lỗi ' + Number(summary.total_defect_qty || 0).toLocaleString('vi-VN')],
    ].map((x, i) => `<article class="daily-kpi k${i}"><small>${x[0]}</small><strong>${typeof x[1] === 'number' ? Number(x[1]).toLocaleString('vi-VN') : x[1]}</strong><span>${x[2]}</span></article>`).join('');
  };

  const drawTable = () => {
    const host = document.getElementById('epTableHost');
    if (!rows.length) { host.innerHTML = '<div class="empty">Không có Session hoàn thành trong khoảng ngày đã chọn.</div>'; return; }
    const arrow = key => sortKey === key ? (sortDir === 1 ? ' ▲' : ' ▼') : '';
    host.innerHTML = `<div class="table-wrap"><table class="ep-table"><thead><tr>
      <th data-sort="employee_name" class="sortable">Nhân viên${arrow('employee_name')}</th>
      <th data-sort="session" class="sortable">Session đã kết thúc${arrow('session')}</th>
      <th data-sort="productivity_percent" class="sortable">Năng suất trung bình${arrow('productivity_percent')}</th>
      <th data-sort="good_qty" class="sortable">Sản lượng đạt / lỗi${arrow('good_qty')}</th>
      <th data-sort="worked_seconds" class="sortable">Tổng thời gian làm việc${arrow('worked_seconds')}</th>
    </tr></thead><tbody>${rows.map(x => {
      return `<tr class="ep-row" data-employee="${x.employee_id}" tabindex="0" role="button">
        <td><b>${esc(x.employee_name)}</b><small>${esc(x.employee_code)}${x.department ? ' · ' + esc(x.department) : ''}</small></td>
        <td><b>${x.completed_sessions} session</b>${x.completed_invalid_sessions ? `<small>${x.completed_invalid_sessions} không đủ dữ liệu</small>` : ''}</td>
        <td><b class="ep-pct">${productivityText(x.productivity_percent)}</b><small>${x.completed_valid_sessions} session hợp lệ</small></td>
        <td><b>Đạt ${Number(x.good_qty).toLocaleString('vi-VN')}</b><small>NG ${Number(x.defect_qty).toLocaleString('vi-VN')}</small></td>
        <td>${epDur(x.worked_seconds)}</td>
      </tr>`;
    }).join('')}</tbody></table></div>`;
    host.querySelectorAll('.sortable').forEach(th => th.onclick = () => {
      const key = th.dataset.sort;
      if (sortKey === key) sortDir *= -1; else { sortKey = key; sortDir = key === 'employee_name' ? 1 : -1; }
      sortRows(); drawTable();
    });
    host.querySelectorAll('.ep-row').forEach(tr => {
      const open = () => openEmployeeProductivityDetail(Number(tr.dataset.employee), document.getElementById('epFrom').value, document.getElementById('epTo').value);
      tr.onclick = open;
      tr.onkeydown = e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(); } };
    });
  };

  let lastEmployees = [];
  const applyFilters = raw => {
    if (raw) lastEmployees = raw;
    const q = (document.getElementById('epSearch').value || '').trim().toLowerCase();
    const dept = document.getElementById('epDept').value;
    rows = lastEmployees.filter(x => (!dept || x.department === dept) && (!q || `${x.employee_name} ${x.employee_code}`.toLowerCase().includes(q)));
    sortRows(); drawTable();
  };

  const load = async () => {
    const host = document.getElementById('epTableHost');
    host.innerHTML = 'Đang tải...';
    try {
      const from = document.getElementById('epFrom').value, to = document.getElementById('epTo').value;
      const d = await api(`/api/reports/employee-productivity?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`);
      document.getElementById('epRangeLabel').textContent = `${epDateShort(from)} → ${epDateShort(to)} · sắp xếp theo năng suất giảm dần, có thể đổi cột`;
      drawKpis(d.summary || {});
      const deptSel = document.getElementById('epDept'), currentDept = deptSel.value;
      const depts = [...new Set((d.employees || []).map(x => x.department).filter(Boolean))].sort();
      deptSel.innerHTML = '<option value="">Tất cả bộ phận</option>' + depts.map(x => `<option value="${esc(x)}">${esc(x)}</option>`).join('');
      if (depts.includes(currentDept)) deptSel.value = currentDept;
      applyFilters(d.employees || []);
    } catch (e) {
      host.innerHTML = `<div class="empty danger">${esc(e.message)}</div>`;
    }
  };

  document.getElementById('epReload').onclick = load;
  document.getElementById('epFrom').onchange = load;
  document.getElementById('epTo').onchange = load;
  // Search/department re-filter the already-fetched list -- no re-fetch.
  document.getElementById('epSearch').oninput = () => applyFilters();
  document.getElementById('epDept').onchange = () => applyFilters();

  // --- TRÌNH CHIẾU KIOSK -----------------------------------------------
  // Deliberately isolated from the table's own filter/sort/search state
  // above: this panel only ever reads epFrom/epTo/epDept (Section 21 --
  // "current Report filters") at the moment Preview/Publish is clicked,
  // and Publish is the ONLY thing in this file that calls the
  // wallboard-config endpoint. Nothing here duplicates the productivity
  // formula -- Preview calls the same authenticated report API this page
  // already uses; Publish only ever writes filter/display config.
  const wbStateText = cfg => {
    if (!cfg.configured) return 'Chưa public — Kiosk sẽ hiện màn "Chưa cấu hình trình chiếu".';
    const range = cfg.date_mode === 'dynamic_mtd' ? 'Đầu tháng → hôm nay (tự động)' : `${epDateShort(cfg.from)} → ${epDateShort(cfg.to)}`;
    const sortLabel = { productivity_desc: 'Năng suất giảm dần', productivity_asc: 'Năng suất tăng dần', name_asc: 'Tên A→Z', sessions_desc: 'Số session giảm dần' }[cfg.sort] || cfg.sort;
    const columnsLabel = cfg.columns === 'auto' ? 'Tự động' : `${cfg.columns} cột`;
    const flipLabel = cfg.auto_page_flip ? `Tự động chuyển trang mỗi ${cfg.auto_page_flip_seconds}s` : 'Không tự động chuyển trang';
    return `Đang public: ${range} · Sort: ${sortLabel} · ${cfg.employees_per_page} người/trang · ${columnsLabel} · ${flipLabel} · Refresh dữ liệu: ${cfg.refresh_interval_seconds}s · Cập nhật lần cuối: ${cfg.updated_at ? epTimeShort(cfg.updated_at) + ' ' + epDateShort(cfg.updated_at) : '—'} · Người cập nhật: ${cfg.updated_by || '—'}`;
  };
  const loadWallboardState = async () => {
    try {
      const d = await api('/api/reports/employee-productivity/wallboard-config');
      document.getElementById('epWbState').textContent = wbStateText(d.config);
      if (d.config.configured) {
        document.getElementById('epWbSort').value = d.config.sort;
        document.getElementById('epWbEmployeesPerPage').value = String(d.config.employees_per_page);
        document.getElementById('epWbColumns').value = String(d.config.columns);
        document.getElementById('epWbAutoFlip').checked = !!d.config.auto_page_flip;
        document.getElementById('epWbFlipSeconds').value = String(d.config.auto_page_flip_seconds);
        document.getElementById('epWbRefresh').value = d.config.refresh_interval_seconds;
        document.getElementById('epWbDynamicMtd').checked = d.config.date_mode === 'dynamic_mtd';
      }
    } catch (e) {
      document.getElementById('epWbState').textContent = `Không tải được trạng thái trình chiếu: ${esc(e.message)}`;
    }
  };
  const wbQueryFromCurrentFilters = () => {
    const q = new URLSearchParams();
    q.set('from', document.getElementById('epFrom').value);
    q.set('to', document.getElementById('epTo').value);
    const dept = document.getElementById('epDept').value; if (dept) q.set('department', dept);
    q.set('sort', document.getElementById('epWbSort').value);
    q.set('employees_per_page', document.getElementById('epWbEmployeesPerPage').value || '20');
    q.set('columns', document.getElementById('epWbColumns').value || 'auto');
    q.set('auto_page_flip', document.getElementById('epWbAutoFlip').checked ? '1' : '0');
    q.set('auto_page_flip_seconds', document.getElementById('epWbFlipSeconds').value || '10');
    q.set('refresh', document.getElementById('epWbRefresh').value || '20');
    return q;
  };
  document.getElementById('epWbPreview').onclick = () => {
    // Preview mode: opens the Kiosk layout with ?preview=1 + these params --
    // it calls the authenticated report API directly and NEVER touches the
    // published config, so a manager can check before publishing.
    window.open(`/kiosk/employee-productivity?preview=1&${wbQueryFromCurrentFilters().toString()}`, '_blank');
  };
  document.getElementById('epWbPublish').onclick = async () => {
    const btn = document.getElementById('epWbPublish');
    btn.disabled = true;
    try {
      const dynamic = document.getElementById('epWbDynamicMtd').checked;
      const employeesPerPage = Number(document.getElementById('epWbEmployeesPerPage').value || 20);
      const body = {
        date_mode: dynamic ? 'dynamic_mtd' : 'fixed',
        from: dynamic ? null : document.getElementById('epFrom').value,
        to: dynamic ? null : document.getElementById('epTo').value,
        department: document.getElementById('epDept').value || null,
        sort: document.getElementById('epWbSort').value,
        // page_size kept in lockstep with employees_per_page -- one control
        // in this UI now, but the older field stays valid/round-trippable
        // for anything still reading it (back-compat, no second control).
        page_size: employeesPerPage,
        employees_per_page: employeesPerPage,
        columns: document.getElementById('epWbColumns').value,
        auto_page_flip: document.getElementById('epWbAutoFlip').checked,
        auto_page_flip_seconds: Number(document.getElementById('epWbFlipSeconds').value || 10),
        refresh_interval_seconds: Number(document.getElementById('epWbRefresh').value || 20),
      };
      const d = await api('/api/reports/employee-productivity/wallboard-config', { method: 'POST', body: JSON.stringify(body) });
      document.getElementById('epWbState').textContent = wbStateText(d.config);
      toast('Đã trình chiếu lên Kiosk.');
    } catch (e) {
      toast(e.message || 'Không public được lên Kiosk.', 'danger');
    } finally {
      btn.disabled = false;
    }
  };

  await load();
  await loadWallboardState();
}

async function openEmployeeProductivityDetail(employeeId, from, to) {
  const box = document.createElement('div'); box.className = 'modal-backdrop';
  box.innerHTML = `<div class="modal ep-detail-modal"><div class="catalog-modal-head"><div><h2 id="epdTitle">Đang tải...</h2><p id="epdRange"></p></div><button type="button" class="btn" id="epdClose">Đóng</button></div><div id="epdBody">Đang tải...</div></div>`;
  document.body.appendChild(box);
  const close = () => box.remove();
  box.querySelector('#epdClose').onclick = close;
  box.onclick = e => { if (e.target === box) close(); };
  try {
    const d = await api(`/api/reports/employee-productivity/${employeeId}?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`);
    const emp = d.employee;
    box.querySelector('#epdTitle').textContent = `${emp.employee_name} · ${emp.employee_code}`;
    box.querySelector('#epdRange').textContent = `${epDateShort(d.from)} → ${epDateShort(d.to)} · Năng suất trung bình: ${productivityText(d.productivity_percent)} (${d.valid_session_count} session hợp lệ)`;
    // Only completed sessions are ever returned here (backend filters to
    // status='CLOSED' AND ended_at IS NOT NULL) -- there is no running
    // session to special-case any more, so "Trạng thái" now reports
    // whether the session had enough data to count toward the average
    // (Section 5: "Không hiển thị running session").
    const rows = d.sessions || [];
    box.querySelector('#epdBody').innerHTML = rows.length ? `<div class="table-wrap"><table><thead><tr><th>Ngày</th><th>PO</th><th>Part</th><th>Operation</th><th>Bắt đầu</th><th>Kết thúc</th><th>Thời gian</th><th>GOOD</th><th>DEFECT</th><th>Completion %</th><th>Trạng thái</th></tr></thead><tbody>${rows.map(x => `<tr>
        <td>${epDateShort(x.ended_at)}</td><td>${esc(x.po_code)}</td><td>${esc(x.part_code)}</td><td>${esc(x.operation_code)}</td>
        <td>${epTimeShort(x.started_at)}</td><td>${epTimeShort(x.ended_at)}</td><td>${epDur(x.duration_seconds)}</td>
        <td>${Number(x.good_qty).toLocaleString('vi-VN')}</td><td>${Number(x.defect_qty).toLocaleString('vi-VN')}</td>
        <td>${x.completion_percent === null ? '<span class="badge neutral">Không đủ dữ liệu</span>' : productivityText(x.completion_percent)}</td>
        <td>${x.completion_percent === null ? 'Đã kết thúc · thiếu dữ liệu định mức' : 'Đã kết thúc · hợp lệ'}</td>
      </tr>`).join('')}</tbody></table></div><p class="ep-detail-footnote">Trung bình: ${productivityText(d.productivity_percent)} trên ${d.valid_session_count} session hợp lệ (session đang chạy đã bị loại từ query, không chỉ từ công thức; session thiếu dữ liệu định mức cũng không tính vào trung bình).</p>`
      : '<div class="empty">Không có Session đã kết thúc trong khoảng ngày đã chọn.</div>';
  } catch (e) {
    box.querySelector('#epdBody').innerHTML = `<div class="empty danger">${esc(e.message)}</div>`;
  }
}

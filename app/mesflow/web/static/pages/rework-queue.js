// Hàng chờ sửa -- the UI for the V1 rework queue (migration 0044).
//
// The backend has shipped since 0044 but had no interface at all: the
// 2026-09-09 audit found 13 items sitting in the queue on TEST and zero
// resolutions ever recorded, because the only way to resolve one was to POST
// to the API by hand. This page is that missing interface.
//
// Model (see 0044_rework_queue.py's docstring, which is the spec):
//   defect_qty = NG on the source session
//   rework_qty = of those, how many were FIXED
//   scrap_qty  = of those, how many were WRITTEN OFF
//   pending    = defect_qty - rework_qty - scrap_qty, derived, never stored
// Resolving credits repaired pieces back to the SOURCE operation's good
// output and books scrapped pieces to scrap -- the server does all of that in
// one transaction (ReworkQueueRepository.resolve); this page only collects
// the two numbers and who did the work.
registerPage('rework-queue', () => renderReworkQueue());

const RQ_STATE = { items: [], employees: [] };

function rqNum(value) { return MFUI.formatQuantity(value); }

function rqRow(item) {
  const canResolve = hasPermission('rework.resolve');
  const resolved = Number(item.rework_qty || 0) + Number(item.scrap_qty || 0);
  return `<div class="rq-row" data-rq-row="${Number(item.source_session_id)}">
    <span class="rq-cell rq-what">
      <b>${esc(item.operation_code || '')} · ${esc(item.operation_name || '')}</b>
      <small>${esc(item.po_code || '')} · ${esc(item.part_code || '')} ${esc(item.part_name || '')}</small>
    </span>
    <span class="rq-cell rq-who">
      <b>${esc(item.employee_name || '—')}</b>
      <small>${esc(item.employee_no || '')} · Session #${Number(item.source_session_id)}</small>
    </span>
    <span class="rq-cell rq-when">
      <b>${MFUI.formatDateTime(item.source_finished_at)}</b>
      <small>Kết thúc Session</small>
    </span>
    <span class="rq-cell rq-split">
      <b>NG ${rqNum(item.defect_qty)}</b>
      <small>Đã sửa ${rqNum(item.rework_qty)} · Đã loại ${rqNum(item.scrap_qty)}${resolved ? '' : ' · chưa xử lý'}</small>
    </span>
    <span class="rq-cell rq-pending"><strong>${rqNum(item.pending_qty)}</strong><small>chờ sửa</small></span>
    <span class="rq-cell rq-act">${canResolve
      ? `<button class="btn primary mini" data-rq-resolve="${Number(item.source_session_id)}" type="button">Xử lý</button>`
      : '<small class="rq-noperm">Chỉ Quản lý / Tổ trưởng</small>'}</span>
  </div>`;
}

function rqVisible() {
  const q = (document.getElementById('rqSearch')?.value || '').trim().toLowerCase();
  const po = document.getElementById('rqPo')?.value || '';
  return RQ_STATE.items.filter(x =>
    (!po || String(x.production_order_id) === String(po)) &&
    (!q || `${x.po_code} ${x.part_code} ${x.part_name || ''} ${x.operation_code} ${x.operation_name} ${x.employee_name || ''} ${x.employee_no || ''}`
      .toLowerCase().includes(q)));
}

function rqDraw() {
  const rows = rqVisible();
  const pending = rows.reduce((n, x) => n + Number(x.pending_qty || 0), 0);
  const parts = new Set(rows.map(x => x.part_id)).size;
  document.getElementById('rqStats').innerHTML = [
    ['sản phẩm chờ sửa', rqNum(pending)], ['Session', rqNum(rows.length)], ['Part', rqNum(parts)],
  ].map(([label, value]) => `<span><b>${value}</b> ${label}</span>`).join('');
  document.getElementById('rqCount').textContent = `${rows.length} kết quả`;
  document.getElementById('rqList').innerHTML = rows.length
    ? `<div class="rq-table"><div class="rq-row head"><span>Operation</span><span>Người làm / Session</span>
        <span>Thời điểm</span><span>NG / đã xử lý</span><span>Chờ sửa</span><span></span></div>
        ${rows.map(rqRow).join('')}</div>`
    : MFUI.emptyState('Không có sản phẩm chờ sửa',
        RQ_STATE.items.length ? 'Không có mục nào khớp bộ lọc hiện tại.' : 'Khi một Session ghi nhận NG chưa được sửa hoặc loại, mục đó sẽ xuất hiện ở đây.');
  document.querySelectorAll('[data-rq-resolve]').forEach(button => {
    button.onclick = () => rqOpenResolve(Number(button.dataset.rqResolve));
  });
}

function rqSyncUrl() {
  AppNav.setQuery({ q: document.getElementById('rqSearch')?.value || '', po: document.getElementById('rqPo')?.value || '' });
}

async function rqLoad() {
  const list = document.getElementById('rqList');
  list.innerHTML = MFUI.loadingState('Đang tải hàng chờ sửa…');
  try {
    const data = await api('/api/rework/queue?limit=1000');
    RQ_STATE.items = data.items || [];
    const seen = new Map();
    for (const item of RQ_STATE.items) if (!seen.has(item.production_order_id)) seen.set(item.production_order_id, item.po_code);
    const po = document.getElementById('rqPo'), current = po.value;
    po.innerHTML = '<option value="">Tất cả PO</option>' +
      [...seen.entries()].map(([id, code]) => `<option value="${Number(id)}">${esc(code || '')}</option>`).join('');
    po.value = [...seen.keys()].map(String).includes(String(current)) ? current : '';
    rqDraw();
  } catch (e) {
    list.innerHTML = MFUI.errorState(e.message || 'Không tải được hàng chờ sửa.', 'rqRetry');
    const retry = document.getElementById('rqRetry');
    if (retry) retry.onclick = () => rqLoad();
  }
}

function rqOpenResolve(sessionId) {
  const item = RQ_STATE.items.find(x => Number(x.source_session_id) === Number(sessionId));
  if (!item) return;
  const pending = Number(item.pending_qty || 0);
  const employees = RQ_STATE.employees.length ? RQ_STATE.employees : [{ id: item.employee_id, employee_no: item.employee_no, name: item.employee_name }];
  const modal = MFUI.openModal({
    id: 'rqResolve', title: 'Xử lý hàng chờ sửa', size: 'MD',
    content: `<div class="rq-resolve">
      <div class="rq-resolve-source">
        <b>${esc(item.operation_code || '')} · ${esc(item.operation_name || '')}</b>
        <span>${esc(item.po_code || '')} · ${esc(item.part_code || '')} ${esc(item.part_name || '')}</span>
        <span>Session #${Number(item.source_session_id)} · ${esc(item.employee_name || '')} · NG ${rqNum(item.defect_qty)}</span>
        <strong>Còn chờ sửa: ${rqNum(pending)}</strong>
      </div>
      <div class="form-grid rq-resolve-grid">
        <label>Sửa được<input type="number" id="rqRepaired" min="0" max="${pending}" step="1" value="0" inputmode="numeric"></label>
        <label>Loại (phế)<input type="number" id="rqScrapped" min="0" max="${pending}" step="1" value="0" inputmode="numeric"></label>
        <label class="rq-span">Người thực hiện<select id="rqEmployee">${employees.map(x =>
          `<option value="${Number(x.id)}"${Number(x.id) === Number(item.employee_id) ? ' selected' : ''}>${esc(x.employee_no || '')} · ${esc(x.name || '')}</option>`).join('')}</select></label>
        <label class="rq-span">Ghi chú<input id="rqNote" placeholder="Không bắt buộc — ví dụ: sửa lại mối hàn"></label>
      </div>
      <p class="rq-resolve-preview" id="rqPreview"></p>
      <div class="form-error hidden" id="rqError" role="alert"></div>
    </div>`,
    footer: '<button class="btn" id="rqCancel" type="button">Hủy</button><button class="btn primary" id="rqSave" type="button">Xác nhận</button>',
  });
  const repaired = () => Math.max(0, Number(document.getElementById('rqRepaired').value || 0));
  const scrapped = () => Math.max(0, Number(document.getElementById('rqScrapped').value || 0));
  const error = document.getElementById('rqError');
  const preview = () => {
    const left = pending - repaired() - scrapped();
    document.getElementById('rqPreview').innerHTML = left < 0
      ? `<b class="danger">Vượt quá số chờ sửa ${rqNum(pending)}</b>`
      : `Sau khi lưu: <b>+${rqNum(repaired())}</b> vào sản lượng đạt của Operation gốc · <b>${rqNum(scrapped())}</b> vào phế · còn lại <b>${rqNum(left)}</b> chờ sửa.`;
  };
  document.getElementById('rqRepaired').oninput = preview;
  document.getElementById('rqScrapped').oninput = preview;
  preview();
  document.getElementById('rqCancel').onclick = () => modal.close();
  document.getElementById('rqSave').onclick = async () => {
    const save = document.getElementById('rqSave');
    error.classList.add('hidden');
    const total = repaired() + scrapped();
    if (total <= 0) { error.textContent = 'Nhập số lượng sửa được hoặc loại.'; error.classList.remove('hidden'); return; }
    if (total > pending) { error.textContent = `Tổng ${total} vượt quá số chờ sửa (${pending}).`; error.classList.remove('hidden'); return; }
    save.disabled = true; save.textContent = 'Đang lưu…';
    try {
      await api(`/api/rework/queue/${Number(sessionId)}/resolve`, {
        method: 'POST',
        body: JSON.stringify({
          // Server-side idempotency key: a retry of the same click must never
          // credit the repair twice (kiosk_idempotency, see resolve()).
          request_id: `RQ-${sessionId}-${(crypto.randomUUID && crypto.randomUUID()) || Date.now()}`,
          employee_id: Number(document.getElementById('rqEmployee').value),
          repaired_qty: repaired(), scrapped_qty: scrapped(),
          note: document.getElementById('rqNote').value || '',
        }),
      });
      modal.close();
      toast(`Đã xử lý: sửa được ${repaired()} · loại ${scrapped()}`);
      await rqLoad();
    } catch (e) {
      error.textContent = e.message || 'Không lưu được. Thử lại.';
      error.classList.remove('hidden');
      save.disabled = false; save.textContent = 'Xác nhận';
    }
  };
}

async function renderReworkQueue() {
  if (dashboardTimer) { clearInterval(dashboardTimer); dashboardTimer = null; }
  title.textContent = 'Hàng chờ sửa';
  subtitle.textContent = 'Sản phẩm NG chưa được sửa hoặc loại, gom theo Part và Operation phát sinh';
  const query = new URLSearchParams(location.search);
  content.innerHTML = `<div class="page-shell">
    ${MFUI.filterBar({
      content: `<label>Tìm kiếm<input id="rqSearch" placeholder="PO, Part, Operation, nhân viên…" value="${esc(query.get('q') || '')}"></label>
        <label>Production Order<select id="rqPo"><option value="">Tất cả PO</option></select></label>`,
      actions: '<button class="btn" id="rqReload" type="button">Làm mới</button>',
      count: '',
    })}
    <div class="stats-row rq-stats" id="rqStats" aria-live="polite"></div>
    ${MFUI.contentPanel({
      title: 'Sản phẩm chờ sửa',
      description: 'Xử lý bằng cách ghi nhận số sửa được và số loại. Số sửa được sẽ cộng lại vào sản lượng đạt của Operation gốc.',
      actions: '<span id="rqCount" aria-live="polite"></span>',
      body: '<div id="rqList"></div>',
    })}
  </div>`;
  document.getElementById('rqSearch').oninput = MFUI.debounce(() => { rqSyncUrl(); rqDraw(); }, 250);
  document.getElementById('rqPo').onchange = () => { rqSyncUrl(); rqDraw(); };
  document.getElementById('rqReload').onclick = () => rqLoad();
  // Resolving credits the work to whoever actually did the repair, which is
  // not necessarily the operator who produced the NG -- so the picker needs
  // the real employee list, not just the source session's own worker.
  if (hasPermission('rework.resolve')) {
    try { RQ_STATE.employees = (await api('/api/employees?limit=500')).items || []; } catch (e) { RQ_STATE.employees = []; }
  }
  await rqLoad();
  const po = query.get('po');
  if (po) { document.getElementById('rqPo').value = po; rqDraw(); }
}

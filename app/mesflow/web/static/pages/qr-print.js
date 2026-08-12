async function renderQrPrintCenter(){
  title.textContent='Danh sách QR Code';subtitle.textContent='Lọc, chọn và in tem QR nhân viên, Production Order, Part và Operation';
  content.innerHTML=`<section class="panel qr-print-center"><div class="panel-head"><div><h2>In tem QR</h2><p>Chọn đúng nhóm dữ liệu, kiểm tra nội dung và kích thước tem trước khi in.</p></div><div class="panel-actions"><button class="btn" id="qrSelectAll">Chọn tất cả đang hiển thị</button><button class="btn" id="qrClear">Bỏ chọn</button><button class="btn primary" id="qrPrint">In tem đã chọn</button></div></div><div class="qr-toolbar"><label><span>Loại mã QR</span><select id="qrType"><option value="EMPLOYEE">Nhân viên</option><option value="OPERATION">Operation</option><option value="PART">Part</option><option value="PRODUCTION_ORDER">Production Order</option></select></label><label><span>Production Order</span><select id="qrPo"><option value="">Tất cả Production Order</option></select></label><label class="qr-search-field"><span>Tìm nhanh</span><input id="qrSearch" placeholder="Mã, tên, PO hoặc bộ phận"></label><label><span>Kích thước in</span><select id="qrSize"><option value="50x30">Tem 50 × 30 mm</option><option value="70x40">Tem 70 × 40 mm</option><option value="90x55">Tem 90 × 55 mm</option><option value="a4-card">Thẻ A4 lớn</option></select></label><button class="btn" id="qrReload">Làm mới</button></div><div class="qr-selection-summary" id="qrSummary">Đang tải danh sách...</div><div id="qrList"><div class="empty">Đang tải...</div></div></section><div class="qr-print-sheet" id="qrPrintSheet" aria-hidden="true"></div>`;
  const $=id=>document.getElementById(id);
  const selected=new Map();let items=[];
  const img=x=>`/api/qr-image?data=${encodeURIComponent(x.qr_payload||'')}`;
  const normalize=(raw,type)=>{
    const source=Array.isArray(raw)?raw:Array.isArray(raw?.items)?raw.items:Array.isArray(raw?.data?.items)?raw.data.items:Array.isArray(raw?.data)?raw.data:Array.isArray(raw?.results)?raw.results:[];
    return source.map((row,index)=>({
      id:row.id??row.employee_id??row.operation_id??row.part_id??row.production_order_id??index,
      qr_type:String(row.qr_type||row.type||type||'QR').toUpperCase(),
      code:String(row.code??row.employee_no??row.operation_code??row.part_code??row.po_code??''),
      name:String(row.name??row.employee_name??row.operation_name??row.part_name??row.product??''),
      group_name:String(row.group_name??row.department??row.po_code??row.status??''),
      detail:String(row.detail??row.position??row.part_name??''),
      qr_payload:String(row.qr_payload??row.qr??row.payload??(['EMPLOYEE','OPERATION','PART','PRODUCTION_ORDER'].includes(String(type).toUpperCase())?`WF|${String(type).toUpperCase()==='PRODUCTION_ORDER'?'PO':String(type).toUpperCase()==='OPERATION'?'OP':String(type).toUpperCase()==='EMPLOYEE'?'EMP':'PART'}|${row.code??row.employee_no??row.operation_code??row.part_code??row.po_code??''}`:''))
    })).filter(x=>x.code||x.qr_payload);
  };
  const itemKey=x=>`${x.qr_type}:${x.id}`;
  const sync=()=>{$('qrSummary').textContent=`Hiển thị ${items.length.toLocaleString('vi-VN')} QR · Đã chọn ${selected.size} tem`;document.querySelectorAll('.qr-item-check').forEach(c=>c.checked=selected.has(c.dataset.key))};
  const draw=()=>{
    const host=$('qrList');
    if(!items.length){host.innerHTML='<div class="empty">Không có QR phù hợp.</div>';sync();return}
    host.innerHTML=`<div class="qr-catalog-grid">${items.map(x=>{const key=itemKey(x);return `<article class="qr-catalog-card ${selected.has(key)?'selected':''}" data-key="${esc(key)}"><label><input class="qr-item-check" type="checkbox" data-key="${esc(key)}"><span>Chọn</span></label><div class="qr-preview-box"><img loading="lazy" src="${img(x)}" alt="QR ${esc(x.code)}" onerror="this.hidden=true;this.nextElementSibling.hidden=false"><span class="qr-image-error" hidden>Không tải được ảnh QR</span></div><div class="qr-card-copy"><b>${esc(x.code||'—')}</b><strong>${esc(x.name||'')}</strong><small>${esc(x.group_name||'')}</small><small>${esc(x.detail||'')}</small><code>${esc(x.qr_payload||'Chưa có nội dung QR')}</code></div></article>`}).join('')}</div>`;
    document.querySelectorAll('.qr-item-check').forEach(c=>{c.checked=selected.has(c.dataset.key);c.onchange=()=>{const x=items.find(i=>itemKey(i)===c.dataset.key);if(c.checked&&x)selected.set(c.dataset.key,x);else selected.delete(c.dataset.key);c.closest('.qr-catalog-card')?.classList.toggle('selected',c.checked);sync()}});sync();
  };
  const load=async()=>{
    const host=$('qrList');host.innerHTML='<div class="empty">Đang tải danh sách QR...</div>';
    try{
      const type=$('qrType').value,po=$('qrPo').value,q=$('qrSearch').value.trim();
      const d=await api(`/api/qr-labels?type=${encodeURIComponent(type)}&production_order_id=${encodeURIComponent(po)}&q=${encodeURIComponent(q)}&limit=3000`);
      items=normalize(d,type);if(!Array.isArray(items))throw new Error('Dữ liệu QR không đúng định dạng');draw();
    }catch(e){items=[];host.innerHTML=`<div class="empty danger"><b>Không thể hiển thị danh sách QR</b><span>${esc(e.message||String(e))}</span><small>Mở Developer Tools → Console nếu lỗi vẫn lặp lại.</small></div>`;$('qrSummary').textContent='Không tải được dữ liệu QR';console.error('[QR PRINT] load failed',e)}
  };
  try{
    const pos=await api('/api/production-orders?limit=2000');
    const poItems=Array.isArray(pos)?pos:(pos.items||pos.data?.items||[]);
    $('qrPo').innerHTML='<option value="">Tất cả Production Order</option>'+poItems.map(x=>`<option value="${esc(x.id)}">${esc(x.code)} · ${esc(x.product||'')}</option>`).join('');
  }catch(e){console.warn('[QR PRINT] cannot load PO filter',e);$('qrPo').innerHTML='<option value="">Tất cả Production Order</option>'}
  const togglePo=()=>{$('qrPo').disabled=!['OPERATION','PART'].includes($('qrType').value)};
  $('qrType').onchange=()=>{selected.clear();togglePo();load()};$('qrPo').onchange=load;$('qrReload').onclick=load;let timer=null;$('qrSearch').oninput=()=>{clearTimeout(timer);timer=setTimeout(load,250)};
  $('qrSelectAll').onclick=()=>{items.forEach(x=>selected.set(itemKey(x),x));draw()};$('qrClear').onclick=()=>{selected.clear();draw()};
  $('qrPrint').onclick=()=>{if(!selected.size){toast('Chưa chọn tem QR để in');return}const size=$('qrSize').value;const sheet=$('qrPrintSheet');sheet.className=`qr-print-sheet size-${size}`;sheet.innerHTML=[...selected.values()].map(x=>`<article class="qr-print-label"><img src="${img(x)}"><div><b>${esc(x.code)}</b><strong>${esc(x.name||'')}</strong><small>${esc(x.group_name||'')}</small><small>${esc(x.detail||'')}</small><code>${esc(x.qr_payload)}</code></div></article>`).join('');sheet.setAttribute('aria-hidden','false');requestAnimationFrame(()=>window.print())};
  window.addEventListener('afterprint',()=>{const sheet=$('qrPrintSheet');if(sheet)sheet.setAttribute('aria-hidden','true')},{once:true});togglePo();await load();
}

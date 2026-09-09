async function renderQrPrintCenter(){
  title.textContent='In tem QR';subtitle.textContent='Lọc, chọn và in tem QR cho nhân viên, Production Order, Part và Operation.';
  content.innerHTML=`<div class="page-shell">
   <div class="page-header"><div class="page-header-actions"><button class="btn" id="qrSelectAll">Chọn tất cả đang hiển thị</button><button class="btn" id="qrClear">Bỏ chọn</button><button class="btn primary" id="qrPrint">In tem đã chọn</button></div></div>
   ${MFUI.filterBar({content:'<label><span>Loại mã QR</span><select id="qrType"><option value="EMPLOYEE">Nhân viên</option><option value="OPERATION">Operation</option><option value="PART">Part</option><option value="PRODUCTION_ORDER">Production Order</option></select></label><label><span>Production Order</span><select id="qrPo"><option value="">Tất cả Production Order</option></select></label><label class="qr-search-field"><span>Tìm nhanh</span><input id="qrSearch" placeholder="Mã, tên, PO hoặc bộ phận"></label><label><span>Kích thước in</span><select id="qrSize"><option value="50x30">Tem 50 × 30 mm</option><option value="70x40">Tem 70 × 40 mm</option><option value="90x55">Tem 90 × 55 mm</option><option value="a4-card">Thẻ A4 lớn</option></select></label>',actions:'<button class="btn" id="qrReload">Làm mới</button>'})}
   <div class="qr-selection-summary" id="qrSummary">Đang tải danh sách...</div>
   <section class="content-panel"><div class="content-panel-head"><div><h3>Danh sách QR Code</h3></div></div><div class="content-panel-body" id="qrList"><div class="empty">Đang tải...</div></div></section>
  </div><div class="qr-print-sheet" id="qrPrintSheet" aria-hidden="true"></div>`;
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
      part_code:String(row.part_code??''),
      part_name:String(row.part_name??''),
      part_sort:Number(row.part_sort??0),
      operation_sort:Number(row.operation_sort??0),
      operation_type:String(row.operation_type??'PRODUCTION').toUpperCase(),
      parent_name:String(row.parent_name??''),
      qr_payload:String(row.qr_payload??row.qr??row.payload??(['EMPLOYEE','OPERATION','PART','PRODUCTION_ORDER'].includes(String(type).toUpperCase())?`WF|${String(type).toUpperCase()==='PRODUCTION_ORDER'?'PO':String(type).toUpperCase()==='OPERATION'?'OP':String(type).toUpperCase()==='EMPLOYEE'?'EMP':'PART'}|${row.code??row.employee_no??row.operation_code??row.part_code??row.po_code??''}`:''))
    })).filter(x=>x.code||x.qr_payload);
  };
  const itemKey=x=>`${x.qr_type}:${x.id}`;
  const sync=()=>{
    $('qrSummary').textContent=`Hiển thị ${items.length.toLocaleString('vi-VN')} QR · Đã chọn ${selected.size} tem`;
    document.querySelectorAll('.qr-catalog-card').forEach(el=>{
      const on=selected.has(el.dataset.key);
      el.classList.toggle('selected',on);el.setAttribute('aria-pressed',String(on));
    });
  };

  // Người ở xưởng tìm một công đoạn bằng TÊN của nó ("Chấn mép"), không bằng
  // mã. Trước đây mã là dòng đầu tiên và to nhất trên mỗi thẻ, còn tên là
  // dòng phụ, nên muốn tìm đúng tem phải đọc mã của cả danh sách phẳng hàng
  // trăm dòng. Giờ tên là thông tin chính, mã tụt xuống dòng nhỏ để đối chiếu
  // khi cầm tem, và danh sách được gom theo PO -> Part để đúng cách người ta
  // nghĩ về công việc.
  const collator=new Intl.Collator('vi',{numeric:true,sensitivity:'base'});
  // Thứ tự công nghệ trước, rồi mới tới tên -- sắp thuần theo mã sẽ đảo lộn
  // trình tự chạy máy (OP10 đứng trước OP9).
  const bySequence=(a,b)=>(a.operation_sort-b.operation_sort)||collator.compare(a.name||'',b.name||'')||collator.compare(a.code||'',b.code||'');

  // Tem SETUP phải đọc ra ngay là setup của việc nào -- không bắt người dùng
  // nhận biết bằng hậu tố '-SU' ở cuối mã.
  const displayName=x=>x.operation_type==='SETUP'
    ? `Setup · ${x.parent_name||String(x.name||'').replace(/^Setup\s+/i,'')||x.code}`
    : (x.name||x.code||'—');
  const cardHtml=x=>{
    const key=itemKey(x),isSetup=x.operation_type==='SETUP';
    const context=x.qr_type==='OPERATION'
      ? [x.part_code,x.part_name].filter(Boolean).join(' · ')
      : [x.group_name,x.detail].filter(Boolean).join(' · ');
    return `<article class="qr-catalog-card ${selected.has(key)?'selected':''}" data-key="${esc(key)}"
      role="button" tabindex="0" aria-pressed="${selected.has(key)}"
      aria-label="Chọn tem ${esc(displayName(x))}">
      <span class="qr-pick-mark" aria-hidden="true"></span>
      <div class="qr-preview-box"><img loading="lazy" src="${img(x)}" alt="QR ${esc(x.name||x.code)}" onerror="this.hidden=true;this.nextElementSibling.hidden=false"><span class="qr-image-error" hidden>Không tải được ảnh QR</span></div>
      <div class="qr-card-copy">
        <b class="qr-item-name">${esc(displayName(x))}</b>
        ${isSetup?'<span class="qr-item-badge">Setup máy</span>':''}
        ${context?`<small class="qr-item-context">${esc(context)}</small>`:''}
        <code class="qr-item-code" title="${esc(x.code||'')}">${esc(x.code||'—')}</code>
      </div>
      <div class="qr-card-actions">
        <button class="btn mini" type="button" data-copy-code="${esc(x.code||'')}">Sao chép mã</button>
        <button class="btn mini" type="button" data-show-payload="${esc(key)}">Xem QR</button>
      </div>
    </article>`;
  };

  // Gom PO -> Part -> Operation. Nếu bộ lọc đã khóa vào một PO thì bỏ cấp PO
  // đi cho đỡ một tầng thừa. OP phụ (SETUP) không trộn ngang hàng với OP sản
  // xuất: chúng nằm trong mục riêng của đúng Part đó.
  const groupedHtml=()=>{
    const pos=new Map();
    for(const x of items){
      const poKey=x.group_name||'—';
      if(!pos.has(poKey))pos.set(poKey,new Map());
      const partKey=x.part_code||'—';
      const parts=pos.get(poKey);
      if(!parts.has(partKey))parts.set(partKey,{code:x.part_code,name:x.part_name,sort:x.part_sort,main:[],support:[]});
      (x.operation_type==='PRODUCTION'?parts.get(partKey).main:parts.get(partKey).support).push(x);
    }
    const singlePo=pos.size===1;
    return [...pos.entries()].map(([poCode,parts])=>{
      const body=[...parts.values()].sort((a,b)=>(a.sort-b.sort)||collator.compare(a.code||'',b.code||'')).map(part=>{
        part.main.sort(bySequence);part.support.sort(bySequence);
        const heading=[part.code,part.name].filter(Boolean).join(' · ')||'Chưa gán Part';
        return `<section class="qr-part-group">
          <h4 class="qr-part-head"><span>${esc(heading)}</span><small>${part.main.length+part.support.length} tem</small></h4>
          ${part.main.length?`<div class="qr-catalog-grid">${part.main.map(cardHtml).join('')}</div>`:''}
          ${part.support.length?`<details class="qr-support-group" open><summary>OP phụ · Setup (${part.support.length})</summary><div class="qr-catalog-grid">${part.support.map(cardHtml).join('')}</div></details>`:''}
        </section>`;
      }).join('');
      return singlePo?body:`<section class="qr-po-group"><h3 class="qr-po-head">Production Order ${esc(poCode)}</h3>${body}</section>`;
    }).join('');
  };

  const draw=()=>{
    const host=$('qrList');
    if(!items.length){host.innerHTML='<div class="empty">Không có QR phù hợp.</div>';sync();return}
    host.innerHTML=$('qrType').value==='OPERATION'
      ? groupedHtml()
      : `<div class="qr-catalog-grid">${items.map(cardHtml).join('')}</div>`;
    const toggle=el=>{
      const key=el.dataset.key,x=items.find(i=>itemKey(i)===key);
      if(selected.has(key))selected.delete(key);else if(x)selected.set(key,x);
      sync();
    };
    document.querySelectorAll('.qr-catalog-card').forEach(el=>{
      el.onclick=e=>{if(e.target.closest('button'))return;toggle(el)};
      el.onkeydown=e=>{if(e.key===' '||e.key==='Enter'){e.preventDefault();toggle(el)}};
    });
    document.querySelectorAll('[data-copy-code]').forEach(b=>b.onclick=async()=>{
      const code=b.dataset.copyCode;if(!code)return;
      try{await navigator.clipboard.writeText(code);toast(`Đã sao chép ${code}`)}catch(_){toast(code)}
    });
    // Chuỗi payload dài không chiếm chỗ trên thẻ; ai cần đối chiếu thì mở ra.
    document.querySelectorAll('[data-show-payload]').forEach(b=>b.onclick=()=>{
      const x=items.find(i=>itemKey(i)===b.dataset.showPayload);if(!x)return;
      MFUI.openModal({id:'qrDetail',title:x.name||x.code,size:'SM',
        content:`<div class="qr-detail"><img src="${img(x)}" alt="QR ${esc(x.name||x.code)}">
          <dl><dt>Mã</dt><dd>${esc(x.code||'—')}</dd>
          ${x.part_code?`<dt>Part</dt><dd>${esc([x.part_code,x.part_name].filter(Boolean).join(' · '))}</dd>`:''}
          <dt>Nội dung QR</dt><dd><code>${esc(x.qr_payload||'—')}</code></dd></dl></div>`,
        footer:'<button class="btn" data-ui-close type="button">Đóng</button>'});
    });
    sync();
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

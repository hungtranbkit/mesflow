
(() => {
  'use strict';
  // Approved public facts only. The server receives topic IDs, never raw text,
  // conversation history, cookies or business data. Gateway prose is not rendered.
  const topics = JSON.parse(document.getElementById("support-facts").textContent);
  const fallback = {text:'Mình chưa có thông tin đã kiểm tra để trả lời câu này. Bạn có thể chọn chủ đề bên dưới, xem Hỏi đáp hoặc thử demo. Giá và kênh liên hệ chưa được công bố ở đây; mình không cung cấp thông tin chưa xác minh.', href:'#hoi-dap'};
  const normalize = value => value.normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/đ/g,'d').replace(/Đ/g,'D').toLowerCase().replace(/[^a-z0-9]+/g,' ').trim();
  const includes = (text, key) => (' '+text+' ').includes(' '+key+' ');
  const answer = value => {
    const text = normalize(value);
    if (['gia','price','pricing','bao nhieu','lien he','contact','email','zalo','dien thoai','du lieu that','du lieu noi bo','api','token','secret'].some(key => includes(text,key))) return fallback;
    // Prefer the topic with the longest matching phrase; whole words avoid
    // accidental PO matches in unrelated words. No generative answers.
    let best = fallback, score = 0;
    for (const topic of topics) for (const key of topic.keys) {
      if (includes(text,key) && key.length > score) { best = topic; score = key.length; }
    }
    return best;
  };
  const panel = document.getElementById('support-panel');
  const launch = document.getElementById('support-launch');
  const input = document.getElementById('support-question');
  const log = document.getElementById('support-log');
  function close() { panel.hidden = true; launch.hidden = false; launch.setAttribute('aria-expanded','false'); launch.focus(); }
  launch.addEventListener('click', () => { panel.hidden = false; launch.hidden = true; launch.setAttribute('aria-expanded','true'); document.getElementById('support-close').focus(); });
  document.getElementById('support-close').addEventListener('click',close);
  panel.addEventListener('keydown', event => { if (event.key === 'Escape') { event.preventDefault(); close(); } });
  function message(text, user, href) {
    const item = document.createElement('p'); item.className = 'support-message'+(user?' user':'');
    item.textContent = (user?'Bạn: ':'MESFlow: ')+text;
    if (href) { const link = document.createElement('a'); link.href = href; link.textContent = href.startsWith('/demo')?'Mở demo':href.startsWith('/login')?'Mở trang đăng nhập':'Xem thông tin sản phẩm'; item.append(link); }
    log.append(item);
    while (log.children.length > 24) log.firstElementChild.remove();
    log.scrollTop = log.scrollHeight;
  }
  let busy = false;
  async function ask(question, reply) {
    if (busy) return;
    message(question,true);
    if (!reply.id) { message(reply.text,false,reply.href); return; }
    busy = true;
    const status = document.getElementById('support-status');
    const controls = panel.querySelectorAll('#support-topics button, #support-form button, #support-question');
    controls.forEach(control => control.disabled = true);
    status.textContent = 'Đang hỏi AI…';
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 26000);
    let selected = [reply], source = 'FAQ dự phòng — AI không khả dụng.';
    try {
      const response = await fetch('/support/chat', {
        method:'POST', credentials:'omit', headers:{'Content-Type':'application/json'},
        body:JSON.stringify({topics:[reply.id]}), signal:controller.signal
      });
      if (!response.ok) throw new Error('Support unavailable');
      const data = await response.json();
      if (['gateway','gateway_cached'].includes(data.mode) && Array.isArray(data.topic_ids) && data.topic_ids.length === 1 && data.topic_ids[0] === reply.id) {
        selected = data.topic_ids.map(id => topics.find(topic => topic.id === id));
        source = data.mode === 'gateway' ? 'AI Gateway · Nội dung đã kiểm tra' : 'AI Gateway · Kết quả đã lưu tạm';
      }
    } catch (_) { /* The curated answer remains available during any outage. */ }
    finally {
      clearTimeout(timeout); busy = false;
      controls.forEach(control => control.disabled = false);
    }
    for (const item of selected) message(source+'\n'+item.text,false,item.href);
    status.textContent = '';
  }
  for (const topic of topics) {
    const button = document.createElement('button'); button.type = 'button'; button.textContent = topic.label;
    button.addEventListener('click',() => ask(topic.label,topic)); document.getElementById('support-topics').append(button);
  }
  document.getElementById('support-form').addEventListener('submit',event => {
    event.preventDefault(); const question = input.value.trim(); if (!question) return;
    input.value = ''; ask(question,answer(question)).then(() => { if (!panel.hidden) input.focus(); });
  });
  panel.querySelectorAll('a[href^="#"]').forEach(link => link.addEventListener('click',close));
  log.addEventListener('click', event => { if (event.target.closest('a[href^="#"]')) close(); });
})();


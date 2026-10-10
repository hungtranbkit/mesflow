(() => {
  'use strict';
  const assistant=window.MESFlowSupport;
  const panel=document.getElementById('support-panel'), launch=document.getElementById('support-launch');
  const input=document.getElementById('support-question'), log=document.getElementById('support-log');
  const status=document.getElementById('support-status'), optin=document.getElementById('support-optin');
  const aiButton=document.getElementById('support-ai'), preview=document.getElementById('support-preview');
  let plan=null, generation=0, controller=null;
  function cancel() { generation++; if(controller) controller.abort(); controller=null;status.textContent='';aiButton.disabled=false; }
  function close() { cancel();panel.hidden=true;launch.hidden=false;launch.setAttribute('aria-expanded','false');launch.focus(); }
  launch.addEventListener('click',()=>{panel.hidden=false;launch.hidden=true;launch.setAttribute('aria-expanded','true');document.getElementById('support-close').focus();});
  document.getElementById('support-close').addEventListener('click',close);
  panel.addEventListener('keydown',event=>{if(event.key==='Escape'){event.preventDefault();close();}});
  function message(text,user,sources=[]) {
    const item=document.createElement('p');item.className='support-message'+(user?' user':'');item.textContent=(user?'Bạn: ':'MESFlow: ')+text;
    for(const source of sources) {
      // Links always come from the local approved KB, never model strings.
      const fact=assistant.topics.find(t=>t.id===source.id);if(!fact)continue;
      const link=document.createElement('a');link.href='/support/knowledge#'+fact.id;link.textContent='Nguồn: '+fact.label;item.append(link);
      if(fact.href.startsWith('/')){const action=document.createElement('a');action.href=fact.href;action.textContent=fact.href==='/reports'?'Tạo báo cáo':fact.href==='/demo'?'Mở demo':'Đăng nhập';item.append(action);}
    }
    log.append(item);while(log.children.length>24)log.firstElementChild.remove();log.scrollTop=log.scrollHeight;
  }
  function ask(question,reply) {
    cancel();message(question,true);message((reply.mode==='faq'?'FAQ · Thông tin sản phẩm\n':'')+reply.answer,false,reply.sources);
    plan=reply.ai||null;optin.hidden=!plan;panel.classList.toggle('is-complex',!!plan);preview.textContent=reply.public_question||'';
  }
  aiButton.addEventListener('click',async()=>{
    if(!plan||controller)return;
    const current=++generation;controller=new AbortController();const signal=controller.signal;
    aiButton.disabled=true;status.textContent='AI đang giải thích thêm; FAQ phía trên dùng được ngay. Tối đa 9 giây.';
    const timeout=setTimeout(()=>controller && controller.abort(),10000);
    try {
      const data=await assistant.deeper(plan,signal);if(current!==generation)return;
      if(['gateway','gateway_cached'].includes(data.mode) && typeof data.answer==='string' && data.answer.length<=1800 && Array.isArray(data.topic_ids) && data.topic_ids.length && data.topic_ids.every(id=>plan.topics.includes(id))) {
        message((data.mode==='gateway'?'AI · Giải thích từ nguồn công khai':'AI · Kết quả đã lưu tạm')+'\n'+data.answer,false,data.topic_ids.map(id=>({id})));
        status.textContent='Câu trả lời do AI tổng hợp; xem nguồn để đối chiếu.';
      } else status.textContent='AI chưa trả lời được lúc này. FAQ đã có sẵn phía trên; bạn có thể tiếp tục hỏi.';
    } catch(_) {if(current===generation)status.textContent='AI chưa trả lời trong thời gian cho phép. FAQ đã có sẵn phía trên.';}
    finally {clearTimeout(timeout);if(current===generation){controller=null;aiButton.disabled=false;}}
  });
  for(const id of ['faq','qr','excel','active','multi','slow','demo','login']) {
    const topic=assistant.topics.find(t=>t.id===id),button=document.createElement('button');button.type='button';button.textContent=topic.label;
    button.addEventListener('click',()=>ask(topic.label,assistant.faq(topic.id)));document.getElementById('support-topics').append(button);
  }
  document.getElementById('support-form').addEventListener('submit',event=>{event.preventDefault();const question=input.value.trim();if(!question)return;input.value='';ask(question,assistant.match(question));input.focus();});
})();

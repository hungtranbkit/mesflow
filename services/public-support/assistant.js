/* Shared public product knowledge and matching. Generated inline into welcome
 * for offline FAQ; also served at /support/assistant.js for the /app widget.
 * No visitor text, cookies, page context or conversation history leaves here. */
(function (root) {
  'use strict';
  const topics = /*PUBLIC_FACTS*/[];
  const normalize = value => value.normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/đ/g,'d').replace(/Đ/g,'D').toLowerCase().replace(/[^a-z0-9]+/g,' ').trim();
  const has = (text,key) => (' '+text+' ').includes(' '+key+' ');
  const intents = {
    guide:'Giải thích cách kết hợp các bước sau trong MESFlow, theo thứ tự thực hiện',
    compare:'So sánh mục đích và cách sử dụng các chức năng sau trong MESFlow',
    diagnose:'Hướng dẫn kiểm tra theo các chức năng sau, không kết luận nguyên nhân khi chưa có dữ liệu xưởng'
  };
  const generic = 'xin vui long a ah nhe oi on cam ban lam on mesflow mes flow la gi cach lam sao the nao toi muon biet hay cho minh ban co the khong va voi de thi neu mot hai nhieu tai sao khi can giup huong dan giai thich ket hop so sanh khac nhau giua tu den sau truoc tung theo trong hien thi xem su dung chay ai dang nhan vien cong nhan the quet qr op loi nhu nao nhu the nao cham vi sao nguyen nhan duoc hoac bao cao xuat in tim voi nhau lien quan tiep theo';
  const vocabulary = new Set(normalize(topics.map(t=>t.label+' '+t.text+' '+t.keys.join(' ')).join(' ')+' '+generic).split(' '));
  const clarify = 'Mình chưa có thông tin đã kiểm tra để trả lời câu này. Bạn muốn hỏi cách quét QR, xem người đang làm, tiến độ hay xuất báo cáo? Hãy chọn một chủ đề hoặc diễn đạt lại chỉ về cách dùng sản phẩm.';
  const privateReply = 'Mình chỉ hướng dẫn sản phẩm công khai, không xem hoặc gửi dữ liệu nội bộ. Không nhập tên người, mã đơn hàng, tài khoản, mật khẩu hay số liệu xưởng. Để xem báo cáo thật, dùng Tạo báo cáo và đăng nhập theo quyền.';
  function result(ids, intent) {
    const selected=ids.map(id=>topics.find(t=>t.id===id));
    return {mode:'faq',topic_ids:ids,answer:selected.map(t=>t.text).join('\n\n'),
      sources:selected.map(t=>({id:t.id,label:t.label,href:'/support/knowledge#'+t.id,action_href:t.href})),
      ...(intent ? {ai:{topics:ids,intent,consent:true},public_question:intents[intent]+': '+selected.map(t=>t.label).join('; ')+'.'} : {})};
  }
  function match(value) {
    const text=normalize(value);
    const riskText=text.replace(/\b(danh gia|gia cong|san luong)\b/g,'');
    if (['gia','price','pricing','bao nhieu tien','lien he','contact','email','zalo','dien thoai'].some(k=>has(riskText,k)))
      return {mode:'decline',answer:'Giá và kênh liên hệ chưa được công bố ở đây; mình không cung cấp thông tin chưa xác minh. Bạn có thể thử demo hoặc xem thông tin sản phẩm.',sources:[]};
    if (/[<>@{}\\/:=]|\d/.test(value) || ['du lieu that','du lieu noi bo','khach hang','don hang cua','xuong toi','xuong cua','ten nhan vien','luong','doanh thu','token','secret','api','password','mat khau la','ignore','instructions','system','bo qua','bi mat'].some(k=>has(riskText,k)))
      return {mode:'decline',answer:privateReply,sources:[]};
    // Unknown names, identifiers and unsupported features are never interpreted
    // as context for AI. The canonical opt-in question contains only KB labels.
    if (!text || text.split(' ').some(word=>!vocabulary.has(word))) return {mode:'clarify',answer:clarify,sources:[]};
    const ranked = clause => topics.map(t=>({id:t.id,score:Math.max(0,...t.keys.filter(k=>has(clause,k)).map(k=>k.split(' ').length*10+k.length/100))})).filter(t=>t.score>0).sort((a,b)=>b.score-a.score);
    const hits=ranked(text);
    if (!hits.length) return {mode:'clarify',answer:clarify,sources:[]};
    // Match each explicit clause independently. A specific export phrase must
    // not swallow a separately requested QR/productivity step.
    const clauses=text.split(/\b(?:va|voi|sau do|roi|ket hop|so sanh|khac nhau giua)\b/).map(s=>s.trim()).filter(Boolean);
    const clauseIds=clauses.map(clause=>ranked(clause)[0]?.id).filter(Boolean);
    const ids=clauses.length>1 && clauseIds.length>1 ? [...new Set(clauseIds)] : [hits[0].id];
    if(ids.length>3) return {mode:'clarify',answer:'Bạn muốn làm bước nào trước? Chọn tối đa ba chủ đề để mình giải thích rõ hơn.',sources:[]};
    const intent=ids.length>1 && !ids.includes('login') ? (/so sanh|khac nhau/.test(text)?'compare':/tai sao|nguyen nhan/.test(text)?'diagnose':'guide') : null;
    return result(ids,intent);
  }
  async function deeper(plan,signal) {
    const response=await fetch('/support/chat',{method:'POST',credentials:'omit',headers:{'Content-Type':'application/json'},body:JSON.stringify(plan),signal});
    if (!response.ok) throw new Error('AI unavailable');
    return response.json();
  }
  root.MESFlowSupport={topics,match,faq:id=>result([id]),deeper};
})(typeof window === 'undefined' ? globalThis : window);

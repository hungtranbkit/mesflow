// `api()` — cổng gọi API DUY NHẤT của admin app (≈114 call site).
//
// Toàn bộ phần khó (phân loại lỗi tạm thời, thử lại có backoff, timeout, huỷ
// request cũ, dịch lỗi sang tiếng Việt) nằm ở core/net.js. Ở đây chỉ còn hai
// việc riêng của app này: gắn Content-Type mặc định, và gắn NHÓM HUỶ theo màn
// đang mở để openPage() bỏ được mọi request của màn vừa rời.
//
// Hợp đồng với call site KHÔNG đổi: vẫn là `await api(url)` trả JSON, vẫn ném
// Error khi hỏng. Cái đổi là `err.message` — trước đây có thể là "Failed to
// fetch" của trình duyệt, giờ luôn là một câu tiếng Việt đọc được. Nhờ vậy
// ~40 chỗ đang viết `catch(e){hiện e.message}` được sửa mà không phải đụng
// vào, và không màn nào có cơ hội quên.
async function api(url,opt={}){
  const headers={...(opt.headers||{})};
  if(opt.body!==undefined&&!headers['Content-Type'])headers['Content-Type']='application/json';
  return MFNet.json(url,{
    // Màn đang mở làm nhóm mặc định. Đổi màn = mọi request đọc của màn cũ trở
    // nên vô nghĩa, và một phản hồi về muộn sau khi đã đổi màn chỉ có thể vẽ
    // nhầm hoặc báo lỗi nhầm.
    group:document.body.dataset.page||'app',
    ...opt,
    headers,
  });
}
function toast(msg){
  const t=document.getElementById('toast');
  if(!t)return;
  t.textContent=msg;t.classList.add('show');setTimeout(()=>t.classList.remove('show'),2200);
}

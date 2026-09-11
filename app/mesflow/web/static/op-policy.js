/* Loại Operation: một nơi duy nhất trả lời, phía trình duyệt.
 *
 * Bản đối chiếu của app/mesflow/domain/policy.py. Server đã hội tụ về policy
 * đó, nhưng trình duyệt không import được Python, nên trước đây tám chỗ trong
 * app.js / qr-print.js / kiosk.js tự gõ lại cùng một phép so sánh:
 *
 *     String(x.operation_type || 'PRODUCTION') === 'PRODUCTION'
 *
 * Phần dễ quên không phải tên loại mà là cái mặc-định-là-PRODUCTION cho dữ liệu
 * cũ (cột operation_type thêm vào sau, hàng cũ để trống). Quên nó một lần là
 * một màn hình coi OP cũ là OP phụ và giấu nó đi.
 *
 * Đây KHÔNG phải policy thứ hai: nó chỉ có phép phân loại, không có luật
 * nghiệp vụ nào. Mọi quyết định thật (đếm sản lượng, mở được session, in được
 * tem) vẫn do server quyết; phần này chỉ để hiển thị đúng nhóm.
 * tests/test_operation_type_policy_has_no_second_home.py khoá cho hai bên không
 * trôi ra xa nhau: nó kiểm hằng số hai phía khớp nhau, và kiểm không file .js
 * nào ngoài file này còn tự so operation_type với một chuỗi.
 */
(function (global) {
  'use strict';
  var PRODUCTION = 'PRODUCTION';
  var SETUP = 'SETUP';
  var REWORK = 'REWORK';

  function typeOf(op) {
    if (op === null || op === undefined) return PRODUCTION;
    var raw = (typeof op === 'object') ? op.operation_type : op;
    return String(raw === null || raw === undefined || raw === '' ? PRODUCTION : raw).toUpperCase();
  }

  var OpPolicy = {
    PRODUCTION: PRODUCTION,
    SETUP: SETUP,
    REWORK: REWORK,
    typeOf: typeOf,
    isProduction: function (op) { return typeOf(op) === PRODUCTION; },
    isSupport: function (op) { return typeOf(op) !== PRODUCTION; },
    isSetup: function (op) { return typeOf(op) === SETUP; },
    isRework: function (op) { return typeOf(op) === REWORK; },
    // Cùng tập với "in được tem": tem QR tồn tại để được quét.
    isStartable: function (op) { var t = typeOf(op); return t === PRODUCTION || t === SETUP; }
  };
  global.OpPolicy = OpPolicy;
})(typeof window !== 'undefined' ? window : this);

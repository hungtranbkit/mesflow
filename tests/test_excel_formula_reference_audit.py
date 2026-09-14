"""Detector công thức trỏ sai ô Setup: bắt đúng 4 ô, tha đúng phần còn lại.

Trên file khách thật (NEWARK ARM CHAIR) có 111 ô tổng, trong đó 14 ô viết tham
chiếu Setup KHOÁ DÒNG. 10 ô nằm ở block đầu -- ở đó L11 chính là ô Setup của
nó, hoàn toàn hợp lệ. 4 ô còn lại là công thức bị copy xuống block dưới mà quên
bỏ khoá. Ranh giới giữa hai nhóm là thứ duy nhất đáng test: một detector bắt
theo hình dạng chuỗi '$L$11' sẽ báo cả 14, tức 10 báo động giả.
"""
from mesflow.domain import formula_audit as fa

SETUP_MINUTES = {'L11': 15.0, 'L23': 0.0, 'L83': 30.0, 'L59': 0.0, 'L107': 0.0, 'L71': 30.0}
def value_at(cell):
    return SETUP_MINUTES.get(cell)


def audit(**kw):
    base = dict(sheet='S', block_start=8, block_end=19, total_cell='M14',
                setup_cell='L11', value_at=value_at)
    base.update(kw)
    return fa.audit_total_formula(**base)


def test_block_dau_dung_L11_khoa_dong_van_pass():
    """10 ô hợp lệ của file thật: khoá `$` nhưng trỏ đúng ô Setup của mình."""
    assert audit(formula='=$I$4*L14/3600+$L$11/60') is None
    assert audit(formula='=$I$4*L14/3600+L$11/60') is None


def test_tham_chieu_tuong_doi_dung_thi_pass():
    assert audit(block_start=68, block_end=79, total_cell='M74', setup_cell='L71',
                 formula='=$I$4*L74/3600+L71/60') is None


def test_copy_xuong_block_duoi_ma_gia_tri_khac_nhau_la_ERROR():
    """'Thanh khung ngồi - Trái'!M86 -- Excel cộng 15 phút thay vì 30."""
    issue = audit(block_start=80, block_end=95, total_cell='M86', setup_cell='L83',
                  formula='=$I$4*L86/3600+L$11/60')
    assert issue is not None
    assert issue['severity'] == fa.SEVERITY_ERROR
    assert issue['suspect_cell'] == 'L11' and issue['expected_cell'] == 'L83'
    assert issue['delta_seconds'] == 900.0          # (30-15) phút, tính ra giây
    assert issue['ref_outside_block'] is True
    assert 'L83' in fa.message_vi(issue) and 'Sửa công thức trong file Excel' in fa.message_vi(issue)


def test_copy_xuong_block_duoi_nhung_gia_tri_bang_nhau_la_canh_bao():
    """'Lắp ráp sau khi sơn'!M62 -- sai cấu trúc, chưa lệch vì cả hai ô là 0.

    Không được im lặng bỏ qua: sửa một trong hai ô Setup là số sai ngay, và khi
    đó không còn dấu vết nào để lần ra.
    """
    # Trên sheet đó L11 cũng bằng 0 -- SETUP_MINUTES ở trên mô tả sheet khác,
    # nên bảng giá trị của chính sheet này được đưa vào tại chỗ.
    issue = audit(block_start=56, block_end=70, total_cell='M62', setup_cell='L59',
                  formula='=$I$4*L62/3600+$L$11/60',
                  value_at={'L11': 0.0, 'L59': 0.0}.get)
    assert issue is not None
    assert issue['severity'] == fa.SEVERITY_WARNING
    assert issue['delta_seconds'] == 0.0
    assert 'tình cờ bằng nhau' in fa.message_vi(issue)


def test_khong_doc_duoc_gia_tri_thi_van_bao_nhung_ha_muc():
    issue = audit(block_start=80, block_end=95, total_cell='M86', setup_cell='L83',
                  formula='=$I$4*L86/3600+L$11/60', value_at=lambda cell: None)
    assert issue['severity'] == fa.SEVERITY_WARNING
    assert issue['delta_seconds'] is None


def test_khong_dung_toi_cong_thuc_khong_lien_quan():
    assert audit(formula='') is None
    assert audit(formula='=SUM(A1:A9)') is None
    assert audit(formula=None) is None
    # Trỏ sang sheet khác: có thể cố ý, ngoài phạm vi -- không đoán.
    assert audit(block_start=80, block_end=95, total_cell='M86', setup_cell='L83',
                 formula="=$I$4*L86/3600+'Chân ghế A'!$L$11/60") is None

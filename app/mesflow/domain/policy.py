"""Một nơi duy nhất trả lời: Operation nào tính vào sản xuất, PO nào đang chạy.

LÝ DO TỒN TẠI. Hai câu hỏi này được hỏi ở khắp nơi -- rollup sản lượng, tiến
độ, WIP, dashboard/KPI, lập lịch, import/export Excel, guard chuyển session,
tóm tắt PO, gom nhóm QR. Mỗi chỗ tự trả lời một kiểu, và sai lệch chỉ lộ ra khi
số không khớp.

Hai lỗi thật đã tìm được, cùng một họ:

  * 'ACTIVE' KHÔNG PHẢI trạng thái PO. Tập hợp lệ do
    master_data.OperationRepository quy định là DRAFT / PLANNED / RELEASED /
    IN_PROGRESS / PAUSED / COMPLETED / CANCELLED. Nhưng bảy câu truy vấn ở
    analytics.py lọc theo ('IN_PROGRESS','ACTIVE','PAUSED') -- vừa khớp một
    trạng thái không tồn tại, vừa BỎ SÓT RELEASED. Hậu quả không phải lỗi thấy
    ngay: một PO đã RELEASED đơn giản là không xuất hiện trên dashboard, và
    không có gì báo.

  * SETUP và SỬA HÀNG bị lọc mỗi module một kiểu -- chỗ thì
    COALESCE(operation_type,'PRODUCTION')='PRODUCTION', chỗ thì
    NOT is_rework_op, chỗ thì quên hẳn. Mỗi lần quên là một lần sản lượng của
    OP phụ lọt vào tiến độ PO, hoặc PO không bao giờ COMPLETED.

Module này KHÔNG cố viết lại mọi truy vấn. Nó đặt tên cho các tập hợp và cung
cấp mảnh SQL dùng lại, để chỗ nào sửa thì sửa về đây thay vì chép thêm một
biến thể nữa.
"""
from __future__ import annotations

# --- Trạng thái Production Order -----------------------------------------

#: Tất cả trạng thái PO hợp lệ. Nguồn sự thật; mọi tập bên dưới là tập con.
#: Giữ đồng bộ với OperationRepository.allowed_statuses.
ALL_PO_STATUSES: frozenset[str] = frozenset({
    'DRAFT', 'PLANNED', 'RELEASED', 'IN_PROGRESS', 'PAUSED', 'COMPLETED', 'CANCELLED',
})

#: PO cho phép BẮT ĐẦU session mới. PAUSED cố ý không nằm trong đây: tạm dừng
#: nghĩa là không nhận việc mới, dù việc đang chạy vẫn kết thúc được.
RUNNABLE_PO_STATUSES: frozenset[str] = frozenset({'RELEASED', 'IN_PROGRESS'})

#: PO đang ở trên sàn -- thứ dashboard, tháp điều khiển và báo cáo tiến độ phải
#: nhìn thấy. Rộng hơn RUNNABLE vì một PO tạm dừng vẫn là việc dở dang cần thấy.
OPEN_PO_STATUSES: frozenset[str] = frozenset({'RELEASED', 'IN_PROGRESS', 'PAUSED'})

#: PO đã đóng sổ, không còn thay đổi sản lượng.
TERMINAL_PO_STATUSES: frozenset[str] = frozenset({'COMPLETED', 'CANCELLED'})


def po_status_sql(statuses: frozenset[str]) -> str:
    """Mảnh SQL ``IN ('A','B')`` cho một tập trạng thái.

    Trả về literal chứ không phải placeholder một cách có chủ ý: các tập này là
    hằng số của miền nghiệp vụ, không phải dữ liệu người dùng, và nhúng thẳng
    giữ cho câu truy vấn đọc được ở chỗ dùng. Mọi giá trị đều được kiểm nằm
    trong ALL_PO_STATUSES nên không có đường cho chuỗi lạ lọt vào.
    """
    unknown = set(statuses) - set(ALL_PO_STATUSES)
    if unknown:
        raise ValueError(f'trạng thái PO không tồn tại: {sorted(unknown)}')
    return '(' + ','.join(f"'{s}'" for s in sorted(statuses)) + ')'


# --- Loại Operation -------------------------------------------------------

#: Operation làm ra sản phẩm. Chỉ loại này được tính vào sản lượng, tiến độ,
#: WIP và điều kiện hoàn thành PO.
PRODUCTION_TYPE = 'PRODUCTION'

#: Chuẩn bị máy. Gắn với một OP sản xuất qua parent_operation_id.
SETUP_TYPE = 'SETUP'

#: Bàn sửa hàng. Ghi nhận CÔNG của người sửa; số lượng thuộc về session nguồn.
REWORK_TYPE = 'REWORK'

#: Operation hỗ trợ. Cả hai đều ghi nhận CÔNG (thời gian lao động vẫn tính)
#: nhưng KHÔNG ghi nhận sản lượng.
SUPPORT_TYPES: frozenset[str] = frozenset({SETUP_TYPE, REWORK_TYPE})

#: Loại Operation ĐƯỢC in tem QR.
#:
#: REWORK bị loại ra vì lock_startable_operation() từ chối mở session trên bàn
#: sửa hàng -- in tem cho nó là đưa cho xưởng một mã QR mà kiosk không nhận,
#: và người quét sẽ tưởng máy hỏng. SETUP thì ngược lại, BẮT BUỘC phải có tem:
#: quét tem đó là cách duy nhất để ghi nhận việc chuẩn bị máy.
LABELLED_TYPES: frozenset[str] = frozenset({PRODUCTION_TYPE, SETUP_TYPE})

ALL_OPERATION_TYPES: frozenset[str] = frozenset({PRODUCTION_TYPE}) | SUPPORT_TYPES


def is_production(operation_type: str | None) -> bool:
    """Operation này có được tính vào sản lượng không?

    None và chuỗi rỗng đều là PRODUCTION: cột operation_type thêm vào sau, dữ
    liệu cũ để trống và tất cả đều là OP sản xuất.
    """
    return str(operation_type or PRODUCTION_TYPE).upper() == PRODUCTION_TYPE


def is_support(operation_type: str | None) -> bool:
    return not is_production(operation_type)


#: Điều kiện SQL "đây là OP sản xuất", dùng lại thay vì chép COALESCE ở mỗi
#: truy vấn. Truyền alias bảng operations vào.
def production_only_sql(alias: str = 'o') -> str:
    return f"COALESCE({alias}.operation_type,'{PRODUCTION_TYPE}')='{PRODUCTION_TYPE}'"


def support_only_sql(alias: str = 'o') -> str:
    return f"COALESCE({alias}.operation_type,'{PRODUCTION_TYPE}')<>'{PRODUCTION_TYPE}'"


def type_in_sql(types: frozenset[str], alias: str = 'o') -> str:
    """Điều kiện SQL "loại Operation nằm trong tập này".

    Dùng cho các tập không phải nhị phân sản-xuất/hỗ-trợ -- ví dụ LABELLED_TYPES
    của danh mục QR. Kiểm tên loại trước khi nhúng, cùng lý do với
    po_status_sql(): đây là hằng số của miền nghiệp vụ, không phải dữ liệu
    người dùng, nhưng vẫn không có đường cho chuỗi lạ lọt vào.
    """
    unknown = set(types) - set(ALL_OPERATION_TYPES)
    if unknown:
        raise ValueError(f'loại Operation không tồn tại: {sorted(unknown)}')
    listed = ','.join(f"'{t}'" for t in sorted(types))
    return f"COALESCE({alias}.operation_type,'{PRODUCTION_TYPE}') IN ({listed})"


def type_is_sql(operation_type: str, alias: str = 'o') -> str:
    """Điều kiện SQL "Operation này thuộc đúng loại X".

    Khác type_in_sql ở chỗ nó cho một loại duy nhất, dùng trong CASE WHEN chứ
    không phải WHERE. Có mặt để không ai phải tự gõ lại phần
    COALESCE(...,'PRODUCTION') -- phần mặc-định-là-sản-xuất mới là chỗ dễ quên,
    không phải tên loại.
    """
    if operation_type not in ALL_OPERATION_TYPES:
        raise ValueError(f'loại Operation không tồn tại: {operation_type}')
    return f"COALESCE({alias}.operation_type,'{PRODUCTION_TYPE}')='{operation_type}'"


def is_setup(operation_type: str | None) -> bool:
    return str(operation_type or PRODUCTION_TYPE).upper() == SETUP_TYPE


def is_rework(operation_type: str | None) -> bool:
    return str(operation_type or PRODUCTION_TYPE).upper() == REWORK_TYPE


def is_labelled(operation_type: str | None) -> bool:
    """Operation này có được in tem QR không?"""
    return str(operation_type or PRODUCTION_TYPE).upper() in LABELLED_TYPES

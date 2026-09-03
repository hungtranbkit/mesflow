#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="${1:-$HOME/mesflow-user-guide/final}"
[[ -d "$SRC" ]] || SRC="${1:-$HOME/mesflow-user-guide}"
DEST="${MESFLOW_TUTORIAL_PUBLISH_DIR:-$ROOT/runtime/tutorials}"

ensure_dest_writable() {
  if mkdir -p "$DEST" 2>/dev/null && [[ -w "$DEST" ]]; then return 0; fi
  echo "[ERROR] Không ghi được $DEST"
  echo "Chạy một lần:"
  echo "  sudo install -d -o $USER -g $(id -gn) -m 2775 $DEST"
  echo "hoặc: bash scripts/repair-tutorial-publish-permissions.sh"
  return 2
}
ensure_dest_writable

declare -A TITLES CATS DESCS
TITLES[00_overview]="Tổng quan MESFlow"; CATS[00_overview]="Bắt đầu"; DESCS[00_overview]="Hiểu luồng mẫu quy trình → lệnh sản xuất → công đoạn → phiên làm việc → sản lượng."
TITLES[01_dashboard]="Tổng quan sản xuất theo ngày"; CATS[01_dashboard]="Theo dõi"; DESCS[01_dashboard]="KPI, ca làm, tiến độ thời gian và tiến độ sản phẩm."
TITLES[02_production_order]="Lệnh sản xuất"; CATS[02_production_order]="Kế hoạch"; DESCS[02_production_order]="Tạo, kiểm tra, Start và theo dõi một lệnh sản xuất."
TITLES[03_template]="Mẫu quy trình"; CATS[03_template]="Kế hoạch"; DESCS[03_template]="Part, Operation, cycle time và cấu trúc quy trình mẫu."
TITLES[04_material_flow]="Dòng vật tư"; CATS[04_material_flow]="Theo dõi"; DESCS[04_material_flow]="Theo dõi dòng công đoạn và phát hiện nút thắt."
TITLES[05_session]="Phiên làm việc"; CATS[05_session]="Điều hành"; DESCS[05_session]="Thời gian làm việc, đạt, lỗi, sửa được và truy vết."
TITLES[06_session_exceptions]="Phiên làm việc bất thường"; CATS[06_session_exceptions]="Điều hành"; DESCS[06_session_exceptions]="Điều tra session bất thường và dữ liệu cần xử lý."
TITLES[07_employees_qr]="Nhân viên & QR"; CATS[07_employees_qr]="Danh mục"; DESCS[07_employees_qr]="Quản lý nhân viên, mã QR và in tem."
TITLES[08_kiosk_admin]="Quản lý trạm thao tác"; CATS[08_kiosk_admin]="Kiosk"; DESCS[08_kiosk_admin]="Heartbeat, firmware, offline queue và timeline thiết bị."
TITLES[09_kiosk_operator]="Trạm thao tác cho công nhân"; CATS[09_kiosk_operator]="Kiosk"; DESCS[09_kiosk_operator]="Quét thẻ, Operation, nhập đạt/lỗi/sửa được và xác nhận."
TITLES[10_employee_productivity]="Năng suất nhân viên"; CATS[10_employee_productivity]="Theo dõi"; DESCS[10_employee_productivity]="Năng suất trung bình, sản lượng, thời gian làm việc theo từng nhân viên và trình chiếu tại xưởng."
TITLES[11_working_calendar]="Lịch làm việc"; CATS[11_working_calendar]="Hệ thống"; DESCS[11_working_calendar]="Ca làm, khoảng nghỉ và ảnh hưởng tới thời gian."
TITLES[12_users_permissions]="Người dùng & phân quyền"; CATS[12_users_permissions]="Hệ thống"; DESCS[12_users_permissions]="Role, quyền xem tab và quyền thao tác API."
TITLES[13_system_logs]="Nhật ký hệ thống"; CATS[13_system_logs]="Hệ thống"; DESCS[13_system_logs]="Action Log, Error Trace và cách truy vết sự cố."
TITLES[14_common_cases]="Tình huống & lưu ý"; CATS[14_common_cases]="Xử lý sự cố"; DESCS[14_common_cases]="Session bất thường, lỗi chất lượng, kiosk offline và cách xử lý."

items_json=""
first=1
for key in 00_overview 01_dashboard 02_production_order 03_template 04_material_flow 05_session 06_session_exceptions 07_employees_qr 08_kiosk_admin 09_kiosk_operator 10_employee_productivity 11_working_calendar 12_users_permissions 13_system_logs 14_common_cases; do
  src=""
  for candidate in "$SRC/${key}_voice.mp4" "$SRC/${key}.mp4" "$SRC/${key}.webm"; do
    [[ -f "$candidate" ]] && { src="$candidate"; break; }
  done
  [[ -n "$src" ]] || { echo "[SKIP] $key: chưa có video"; continue; }
  ext="${src##*.}"; filename="${key}.${ext}"
  cp -f "$src" "$DEST/$filename"
  duration=""
  if command -v ffprobe >/dev/null 2>&1; then
    sec="$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$DEST/$filename" 2>/dev/null | cut -d. -f1 || true)"
    if [[ "$sec" =~ ^[0-9]+$ ]]; then duration="$((sec/60))m $((sec%60))s"; fi
  fi
  obj="$(python3 - "$key" "$filename" "${TITLES[$key]}" "${CATS[$key]}" "${DESCS[$key]}" "$duration" <<'PY'
import json,sys
key,file,title,category,desc,duration=sys.argv[1:]
print(json.dumps({"order":key[:2],"id":key,"file":file,"title":title,"category":category,"description":desc,"duration":duration},ensure_ascii=False))
PY
)"
  if [[ "$first" == 1 ]]; then items_json="$obj"; first=0; else items_json="$items_json,$obj"; fi
done

tmp_manifest="$DEST/.manifest.json.tmp.$$"
python3 - "$tmp_manifest" "$items_json" <<'PY'
import json,sys
path,raw=sys.argv[1:]
items=json.loads("["+raw+"]") if raw else []
if not items:
    raise SystemExit("Không có video nào để publish; giữ manifest cũ.")
data={"version":1,"title":"Hướng dẫn sử dụng MESFlow","updated_at":__import__("datetime").datetime.now().astimezone().isoformat(),"items":items}
open(path,"w",encoding="utf-8").write(json.dumps(data,ensure_ascii=False,indent=2)+"\n")
PY
mv -f "$tmp_manifest" "$DEST/manifest.json"
echo "Đã publish ${DEST}/manifest.json"
ls -lh "$DEST"

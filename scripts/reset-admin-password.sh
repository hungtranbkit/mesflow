#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
  echo "Không tìm thấy .env"
  exit 1
fi

USERNAME="${1:-admin}"
PASSWORD="${2:-}"

# MẬT KHẨU PHẢI ĐƯỢC TRUYỀN VÀO, không có mặc định.
#
# Trước đây dòng này là `PASSWORD="${2:-Admin@123456}"`. Chạy script cứu hộ mà
# quên tham số thứ hai là đặt đúng chuỗi đó lên máy đích -- và chuỗi đó nằm
# công khai trong repo (compose.test.yml, compose.sandbox.yml, USER_GUIDE_
# VIDEO.md, và một report còn ghi kèm địa chỉ https://mesflow.net ngay cạnh).
# Nghĩa là sau mỗi lần đổi mật khẩu, một cú chạy script vô ý sẽ lặng lẽ khôi
# phục lại đúng mật khẩu vừa bị loại bỏ. (audit 2026-09-14, SEC-15)
if [ -z "$PASSWORD" ]; then
  echo "Thiếu mật khẩu."
  echo "Dùng: $0 <tên đăng nhập> '<mật khẩu mới>'"
  echo "Không có mặc định -- mọi mặc định đều nằm công khai trong repo này."
  exit 2
fi

# Từ chối những chuỗi đã bị công khai hoặc quá yếu. Danh sách này là các giá trị
# thật sự xuất hiện trong repo/tài liệu, cộng vài mẫu kinh điển.
case "$PASSWORD" in
  Admin@123456|admin|Admin@123|password|Password1|123456|changeme|CHANGE_ME|dev-only)
    echo "Mật khẩu '$PASSWORD' nằm trong danh sách đã bị công khai hoặc quá yếu -- từ chối."
    exit 2 ;;
esac

if [ "${#PASSWORD}" -lt 12 ]; then
  echo "Mật khẩu phải dài ít nhất 12 ký tự (đang ${#PASSWORD})."
  exit 2
fi

if grep -q '^MESFLOW_ADMIN_USERNAME=' .env; then
  sed -i "s/^MESFLOW_ADMIN_USERNAME=.*/MESFLOW_ADMIN_USERNAME=${USERNAME}/" .env
else
  printf '\nMESFLOW_ADMIN_USERNAME=%s\n' "$USERNAME" >> .env
fi

if grep -q '^MESFLOW_ADMIN_PASSWORD=' .env; then
  sed -i "s/^MESFLOW_ADMIN_PASSWORD=.*/MESFLOW_ADMIN_PASSWORD=${PASSWORD}/" .env
else
  printf 'MESFLOW_ADMIN_PASSWORD=%s\n' "$PASSWORD" >> .env
fi

docker compose up -d postgres
docker compose run --rm mesflow python -m mesflow.cli reset-admin
docker compose up -d --force-recreate mesflow

echo "Đã reset tài khoản: ${USERNAME}"
echo "Hãy đăng nhập bằng mật khẩu vừa đặt."

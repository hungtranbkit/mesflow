# MESFlow v65.5.0 — Web Agent Production Deploy

Gói này được thiết kế để upload trực tiếp bằng MESFlow Web Deploy Agent vào `/opt/mesflow`.

Agent cần giữ nguyên:

- `/opt/mesflow/.env`
- `/opt/mesflow/certs`
- `/opt/mesflow/runtime`

## Cơ sở dữ liệu

v65 dùng volume mới:

```text
runtime/postgres-v65
```

Dữ liệu PostgreSQL/SQLite của v64 trong các thư mục cũ không bị xóa. v65 khởi tạo database PostgreSQL native mới.

## HTTPS

Yêu cầu có sẵn:

```text
certs/mesflow.net.pem
certs/mesflow.net.key
```

Nginx mở port 80 và 443. `/nginx-health` trên HTTP vẫn trả 200 cho Agent; các URL khác redirect HTTPS.

## Sau deploy

```bash
cd /opt/mesflow
docker compose ps
curl -k -H 'Host: mesflow.net' https://127.0.0.1/api/system/ready
```

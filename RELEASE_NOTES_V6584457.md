# MESFlow 65.8.44.57

- Chuẩn hóa Compose contract để cùng file release có thể được kiểm tra với env profile khác nhau.
- `.env` vẫn là contract runtime được bảo vệ; các biến bí mật bắt buộc tiếp tục fail khi thiếu.
- Không thay đổi schema hoặc business logic.

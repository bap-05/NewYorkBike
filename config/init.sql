-- Thiết lập phiên MySQL; không tạo lại hoặc xóa database.
-- Cấu trúc bảng do Alembic quản lý: python -m alembic upgrade head
-- Từ 0007: bảng/cột tiếng Việt không dấu; tên cũ là VIEW tương thích.
SET NAMES utf8mb4;
SET time_zone = '+00:00';

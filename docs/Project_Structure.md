# Cấu trúc dự án NewYorkBike

```text
NewYorkBike/
├── backend/
│   └── app/
│       ├── main.py             # App factory, lifespan, CORS, xử lý lỗi
│       ├── config.py           # Cấu hình riêng của API
│       ├── dependencies.py     # Session chỉ đọc, kiểm tra schema
│       ├── schemas.py          # Hợp đồng JSON/OpenAPI
│       ├── repositories.py     # Truy vấn có giới hạn và điều kiện công bố
│       ├── presenters.py       # UTC/NY, freshness, trường công khai
│       └── routers/            # Health, overview, stations, analytics
├── frontend/                   # Dành cho React; hiện mới có README
├── ingestion/                  # Thu dữ liệu/API client/Bronze
├── analysis/                   # Thống kê Gold
├── clustering/                 # Phân nhóm trạm hằng ngày
├── prediction/                 # Suy luận; lệnh huấn luyện độc lập
├── shared/
│   ├── models/
│   │   ├── base.py             # Base và kiểu thời gian UTC
│   │   ├── stations.py
│   │   ├── observations.py
│   │   ├── runs.py
│   │   ├── analysis.py
│   │   ├── clustering.py
│   │   ├── prediction.py
│   │   └── __init__.py         # Giữ API import cũ
│   ├── repositories/           # Hợp đồng đọc Silver/Gold dùng chung
│   ├── database.py
│   ├── config.py
│   └── time.py
├── database/migrations/        # Giữ nguyên chuỗi migration hiện có
├── config/                     # Danh sách ID trạm, không chứa secret
├── scripts/                    # Lệnh vận hành, runner GitHub, sao lưu
├── deploy/                     # Đóng gói và cấu hình triển khai
├── .github/workflows/          # Job riêng cho từng service
├── tests/                      # Kiểm thử cô lập
├── docs/                       # Tài liệu chuẩn và bằng chứng kiểm tra
├── requirements.txt            # Phụ thuộc lõi nhẹ cho các worker
├── requirements-api.txt        # FastAPI/Uvicorn
├── requirements-clustering.txt
├── requirements-prediction.txt
├── requirements-dev.txt
├── .env.example
└── README.md
```

Các lệnh `python -m ingestion.main`, `analysis.main`, `clustering.main` và
`prediction.main` vẫn chạy từ thư mục gốc. Không chuyển chúng vào FastAPI hoặc
đổi đường dẫn workflow đang hoạt động. FastAPI không có lịch nền, không gọi API
nguồn, không train hoặc ghi dữ liệu khi người dùng mở trang.

Model được tách thành file nhỏ nhưng vẫn import bằng `from shared.models import
Station, Prediction, ...`. Chỉ thay tổ chức file Python, không thay bảng/khóa/cột,
không cần migration mới vì việc tách file.

`docs/Yeu_Cau_Web_Seoul_Bike.md` là bản yêu cầu chuẩn; tên file giữ để các liên kết
cũ còn dùng được. File cùng tên ở thư mục gốc chỉ trỏ đến bản chuẩn, tránh hai bản
sao lệch nội dung. Thêm tài liệu mới vào docs, không nhân bản ở thư mục gốc.

`.env`, `certs/`, `.venv/`, `data/`, `artifacts/`, `backups/` là dữ liệu/cấu hình
local bị Git bỏ qua. Không di chuyển chúng để phục vụ đổi bố cục. Các script
đóng gói đã bao gồm backend, frontend, clustering, prediction và requirements
tương ứng; vẫn loại secret, Bronze và môi trường Python.

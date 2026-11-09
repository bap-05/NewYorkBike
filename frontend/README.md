# Frontend React

Thư mục dành cho React, chưa có giao diện hoặc số liệu demo.

FastAPI chạy độc lập từ thư mục gốc dự án:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

React sẽ gọi `/api/*` qua API base URL, không kết nối trực tiếp MySQL và không
khởi chạy collector/Analysis/Clustering/Prediction. Development origin mặc định
được cho phép: `http://localhost:5173` và `http://127.0.0.1:5173`.

Xem [hợp đồng API và cách chạy](../docs/FastAPI.md); Swagger tại
`http://127.0.0.1:8000/docs`. Khi triển khai React, giữ nhãn stale/inactive,
baseline/ML, thời điểm dữ liệu, phát hành và mục tiêu; dùng timestamp có offset
America/New_York từ API. Không tự thay NULL thành 0.

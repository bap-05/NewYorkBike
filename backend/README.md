# Backend FastAPI

API công khai chỉ đọc, độc lập với bốn service dữ liệu. Chạy từ thư mục gốc dự án:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-api.txt
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

Swagger: `http://127.0.0.1:8000/docs`. Xem [hướng dẫn chi tiết](../docs/FastAPI.md)
và [cấu trúc dự án](../docs/Project_Structure.md).

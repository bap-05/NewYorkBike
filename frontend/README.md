# Giao diện React — NewYorkBike

React + Vite, React Router, Leaflet/Esri World Street Map. Menu phía trên với 5 trang:
Tổng quan, Bản đồ trạm, Chi tiết trạm, Phân tích & phân nhóm, Dự đoán +30 phút.
Đọc dữ liệu thật qua FastAPI, không kết nối trực tiếp MySQL hay chạy worker từ UI.

Bản đồ giữ khung nhìn các trạm New York, không tự chèn nhãn địa danh hoặc nút
chuyển sang Việt Nam. Xem [nguồn bản đồ](../docs/Map_Display.md).

## Chạy trên Windows

Cần Node.js 22.12 trở lên. Mở **hai terminal**.

Terminal 1 từ thư mục gốc:

```powershell
cd F:\126\NewYorkBike
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --log-level error --no-access-log
```

Giữ `.env`/CA hiện có ở thư mục gốc. Không cần migration mới.

Terminal 2:

```powershell
cd F:\126\NewYorkBike\frontend
npm ci
npm run dev
```

Mở **http://127.0.0.1:5173**. Vite chuyển `/api` tới FastAPI cổng 8000. Giữ hai
terminal mở, Ctrl+C để dừng. Lịch chạy cloud của các service vẫn độc lập.

## Cấu hình và dữ liệu

- Local không cần `.env` frontend. Backend ở host khác: sao chép `.env.example`
  thành `.env`, điền `VITE_API_BASE_URL=https://host-api-thuc-te` rồi chạy/build lại.
  URL này không có `/api` ở cuối. Backend phải cho phép origin frontend qua CORS.
- Mọi `VITE_*` công khai trong trình duyệt; không đặt password, token hay MySQL
  trong frontend. `.env`/CA của Python tiếp tục nằm riêng ở gốc dự án.
- Chỉ đọc nguồn Citi Bike, không trộn Seoul. NULL hiển thị `—`; số 0 vẫn là `0`.
  Có nhãn dữ liệu cũ, inactive; tổng xe chỉ tính các mẫu mới theo API.
- Giờ hiển thị America/New_York với DST, không theo múi giờ máy Windows. Mốc
  mẫu, nguồn, phát hành, mục tiêu và đối chiếu không bị gộp thành một thời điểm.
- Biểu đồ không nối bù qua khoảng thiếu trên 45 phút. Trạm inactive/nguồn không
  hợp lệ không được vẽ thành số xe có thể thuê. Thời tiết giữ đơn vị và interval.
- Analysis có bộ lọc trạm/giờ/ngày/chỉ số và bảng chất lượng; biểu đồ chỉ nối
  metric đạt chất lượng. Clustering hiển thị snapshot thành công trước đó nếu có,
  báo thật khi chưa đủ dữ liệu; không tạo nhóm giả.
- Trang Phân tích có **Khám phá dữ liệu (EDA)**: 12 biểu đồ theo yêu cầu và bảng trung vị/giá trị phổ biến
  từ report hoàn tất tại máy chủ FastAPI. Chọn biểu đồ/trạm và mở ảnh lớn.
  Nút Làm mới tải report đã có, không tạo lại report; xem thời điểm/phạm vi snapshot.
  Nếu thiếu báo cáo, chạy `python -m eda.main --days 28` tại máy chạy API.
- Prediction ghi baseline/ML, tính hợp lệ, mẫu, mục tiêu, phát hành, thực tế và sai
  số. Kết quả cũ không được hiển thị như một dự đoán còn hiệu lực.
  Sai số hiển thị so sánh số xe dự đoán đã công bố với thực tế; chi tiết vẫn giữ
  sai số giá trị mô hình trước giới hạn từ API để phân biệt hai cách đánh giá.
- Tự đọc lại API mỗi 60 giây và có nút Làm mới. Đây không phải lịch chạy worker.
- Trang Dự đoán có **Dự báo và phân loại ngày mai** từ báo cáo EDA: trung
  bình số xe từng giờ và mức xe ít/trung bình/nhiều theo sức chứa, tách khỏi +30
  phút. Có nhãn mô hình cơ sở, điều kiện dữ liệu, ngày mục tiêu và đánh giá tiến
  dần. Có chọn trạm, lọc giờ ít xe, đánh dấu giờ nguy cơ và giờ thiếu dữ liệu.
  Đây là ảnh chụp báo cáo, cần chạy lại EDA để cập nhật; báo cáo cũ có cảnh báo.
- OpenStreetMap cần internet. Font web có font hệ thống dự phòng. Nếu tile lỗi,
  danh sách và link chi tiết trạm vẫn hoạt động.

## Kiểm tra và build

```powershell
npm test
npm run build
```

Build ở `dist/`. Khi deploy static, cấu hình fallback các route như `/map` về
`index.html` và reverse proxy `/api` tới backend, hoặc build với API base URL thật.
`npm run preview` chỉ thử bản build tại máy, không phải triển khai API lên server.
Nếu dùng base URL riêng khi preview, cho phép origin preview trong CORS. Chưa deploy website.

Browser smoke test dùng API thật đang chạy ở cổng 8000, không tạo dữ liệu giả:

```powershell
npx playwright install chromium
npx playwright test
```

Test tự chạy Vite; ảnh chụp ở `artifacts/frontend/` tại gốc (Git bỏ qua).
Test EDA yêu cầu report thật đã tạo ở máy chủ API. Khi cổng đang dùng, có thể đặt
`E2E_PORT` cho Vite test và `API_PROXY_TARGET` cho proxy development, giữ nguyên
tiến trình người dùng. Mặc định vẫn cổng 5173 và backend 8000.

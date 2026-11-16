# NewYorkBike

Hệ thống theo dõi và dự báo số xe có thể thuê tại các trạm Citi Bike ở New York, kết hợp dữ liệu xe, thời tiết và thời gian.

Dự án theo dõi 10 trạm nghiên cứu, có bản đồ, lịch sử số xe, phân tích dữ liệu, phân nhóm hành vi trạm và hai loại dự báo: **30 phút tiếp theo** và **từng giờ ngày mai**. Giao diện sử dụng tiếng Việt; tên trạm giữ nguyên để tra cứu vị trí.

## Chức năng

- Thu thập trạng thái trạm từ Citi Bike GBFS và thời tiết từ Open-Meteo.
- Lưu phản hồi nguồn, dữ liệu chuẩn hóa và kết quả xử lý để truy vết.
- Hiển thị tổng quan, bản đồ, chi tiết trạm và lịch sử số xe.
- Phân tích theo thời gian; tạo và tự cập nhật báo cáo EDA.
- Phân nhóm hành vi trạm bằng K-means, hiển thị trên bản đồ và thẻ nhóm.
- Dự báo số xe sau 30 phút; nhấn vào thẻ dự báo để xem lịch sử và kết quả đối chiếu của trạm.
- Phát hành dự báo từng giờ ngày mai, lưu vào database và tự chấm khi có dữ liệu thực tế. Giao diện hiển thị chênh lệch theo giờ của ngày hôm qua.

Số xe có thể thuê là lượng xe sẵn có tại trạm, không phải số lượt thuê. Dữ liệu thiếu không được thay bằng 0. Thời gian lưu theo UTC và hiển thị theo `America/New_York`, có xử lý EST/EDT.

## Kiến trúc và công nghệ

```text
Citi Bike GBFS + Open-Meteo
            |
       Data Ingestion ----> Bronze: phản hồi gốc và manifest
            |
       MySQL: Silver
            |
    +-------+----------+
    |       |          |
 Analysis Clustering Prediction
    |       |          |
    +-------+----------+
            |
       MySQL: Gold
            |
         FastAPI ----> React

Database ----> EDA worker ----> artifacts/eda ----> FastAPI
```

| Thành phần | Công nghệ |
| --- | --- |
| Giao diện | React 19, Vite, React Router, Leaflet |
| API | FastAPI, Uvicorn |
| Cơ sở dữ liệu | MySQL, SQLAlchemy, Alembic; hỗ trợ Aiven qua TLS |
| Phân tích và EDA | pandas, NumPy, Matplotlib, seaborn |
| Học máy | scikit-learn: Random Forest và K-means |
| Kiểm thử | pytest, Node.js test runner, Playwright |
| Vận hành | CLI độc lập, GitHub Actions, Docker Compose |

Các dịch vụ dữ liệu chạy độc lập. API đọc kết quả đã công bố; việc mở trang web không khởi chạy thu thập hoặc huấn luyện. Riêng báo cáo EDA được API kiểm tra và tạo lại trong tiến trình nền khi tính năng tự cập nhật được bật.

## Cấu trúc thư mục

```text
NewYorkBike/
├── frontend/                 # Giao diện React
├── services/
│   ├── data-ingestion/       # Thu thập xe và thời tiết
│   ├── data-analysis/        # Phân tích và eda/
│   ├── clustering/           # Phân nhóm trạm
│   ├── prediction/           # Huấn luyện, phát hành và chấm dự báo
│   └── database-api/         # FastAPI
├── shared/                   # Cấu hình, models và truy vấn dùng chung
├── database/migrations/      # Migration Alembic
├── config/                   # Cấu hình trạm và lịch lấy mẫu
├── scripts/                  # Nhập lịch sử, đánh giá, sao lưu và chạy cloud
├── tests/                    # Kiểm thử Python
├── docs/                     # Tài liệu chuyên đề
├── .github/workflows/        # Tác vụ GitHub Actions
├── .env.example              # Cấu hình mẫu
├── requirements.txt          # Phụ thuộc Python và cài đặt editable
├── pyproject.toml            # Ánh xạ module tới thư mục dịch vụ
├── docker-compose.yml
└── PROJECT_REPORT.md         # Báo cáo tổng hợp đề tài
```

Các thư mục `data/`, `artifacts/`, `backups/` lưu dữ liệu và kết quả cục bộ; không đi kèm đầy đủ khi clone mã nguồn.

## Cài đặt trên Windows

Yêu cầu: **Python 3.11 trở lên** (khuyến nghị 3.12), **Node.js 22.12 trở lên**, npm và **MySQL 8.0.16 trở lên** hoặc database Aiven tương thích. Tạo sẵn database và tài khoản có quyền phù hợp.

Các lệnh dưới đây dành cho **CMD**, chạy từ thư mục gốc dự án. Thay đường dẫn nếu bạn lưu dự án ở vị trí khác.

```bat
cd /d F:\126\NewYorkBike
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
if not exist .env copy .env.example .env
```

Nếu đã có `.venv`, bỏ qua lệnh tạo môi trường. Lệnh cài đặt cũng đăng ký các module trong `services/`, nên cần chạy trước khi dùng `python -m ingestion.main`, `python -m eda.main` hoặc các dịch vụ khác.

Điền cấu hình trong `.env`:

| Biến | Nội dung |
| --- | --- |
| `MYSQL_HOST`, `MYSQL_PORT` | Máy chủ và cổng MySQL |
| `MYSQL_DATABASE` | Tên database thực tế; không cần đổi tên database cũ |
| `MYSQL_USER`, `MYSQL_PASSWORD` | Thông tin đăng nhập |
| `MYSQL_SSL_CA` | Đường dẫn CA khi dùng TLS, ví dụ `certs/aiven-ca.pem`; để trống nếu MySQL local không dùng TLS |
| `DATABASE_SCHEMA_LANGUAGE` | `vietnamese` với schema sau migration `0007` |
| `BIKE_SOURCE` | `citibike` |
| `STATION_IDS` | Mã trạm dạng chuỗi, phân cách bằng dấu phẩy |
| `DISPLAY_TIMEZONE` | `America/New_York` |
| `OUTBOUND_PROXY_ENABLED` | `false` để kết nối trực tiếp; `true` nếu dùng proxy |
| `OUTBOUND_PROXY_URLS` | Mảng JSON các URL proxy khi bật proxy |
| `EDA_AUTO_UPDATE` | `true` để tự cập nhật báo cáo khi API chạy |

Các biến còn lại nằm trong [.env.example](.env.example). Không đưa `.env`, mật khẩu hoặc token lên Git. Các biến `VITE_*` hiển thị trong trình duyệt, chỉ dùng cho cấu hình công khai.

Liệt kê mã trạm thật để điền `STATION_IDS`:

```bat
.venv\Scripts\python.exe -m ingestion.main --list-stations --limit 10
```

Kiểm tra kết nối và nâng schema:

```bat
.venv\Scripts\python.exe -m scripts.check_database
.venv\Scripts\python.exe -m alembic upgrade head
.venv\Scripts\python.exe -m alembic current
```

Migration hiện tại là `0007_vietnamese_names`, sử dụng tên bảng nghiệp vụ tiếng Việt không dấu. Với database đã có dữ liệu, sao lưu và kiểm tra trạng thái migration trước khi nâng cấp; không tự `stamp head` để bỏ qua lỗi. Xem [hướng dẫn tên bảng](docs/Ten_Bang_Tieng_Viet.md).

## Chạy website

Mở hai terminal riêng.

**Terminal 1 — API:**

```bat
cd /d F:\126\NewYorkBike
.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload --reload-dir services/database-api --reload-dir shared --log-level error --no-access-log
```

**Terminal 2 — giao diện:**

```bat
cd /d F:\126\NewYorkBike\frontend
npm ci
npm run dev
```

- Website: http://127.0.0.1:5173
- Tài liệu API: http://127.0.0.1:8000/docs
- Vite chuyển tiếp `/api` sang API tại cổng `8000`. Khi đặt API ở máy khác, xem [cấu hình frontend](frontend/.env.example).

Nhấn `Ctrl+C` trong terminal để dừng tiến trình tương ứng. Nếu cổng `5173` đã được dùng, dừng phiên Vite cũ hoặc chạy `npm run dev -- --port 5174`; khi đổi cổng, bổ sung địa chỉ frontend vào `API_CORS_ORIGINS` nếu truy cập API trực tiếp.

Website cần database và các kết quả đã được dịch vụ tạo ra. Mở giao diện riêng không tạo thêm dữ liệu.

## Chạy các dịch vụ dữ liệu

Chạy từ thư mục gốc. Mỗi lệnh `--schedule` chạy liên tục trong một terminal riêng; chỉ chọn một nơi chạy lịch cho cùng dịch vụ.

| Công việc | Chạy một lần | Chạy theo lịch |
| --- | --- | --- |
| Thu thập | `.venv\Scripts\python.exe -m ingestion.main --once` | `.venv\Scripts\python.exe -m ingestion.main --schedule --interval-minutes 5` |
| Phân tích | `.venv\Scripts\python.exe -m analysis.main --once` | `.venv\Scripts\python.exe -m analysis.main --schedule` |
| Phân nhóm | `.venv\Scripts\python.exe -m clustering.main --once` | `.venv\Scripts\python.exe -m clustering.main --schedule` |
| Dự báo và đối chiếu | `.venv\Scripts\python.exe -m prediction.main --once` | `.venv\Scripts\python.exe -m prediction.main --schedule` |

Thu thập trong lệnh trên, phân tích và dự báo chạy mỗi 5 phút. Phân nhóm chạy hằng ngày lúc 02:00 theo New York. Lịch dừng khi đóng tiến trình hoặc tắt máy. Mốc thu thập trong quá khứ được mô tả riêng trong [config/sampling_schedule.json](config/sampling_schedule.json) để tính độ phủ đúng với từng giai đoạn.

Phân tích, phân nhóm và dự báo có chế độ `--preview` để tính thử, xuất kết quả cục bộ mà không công bố vào database. Huấn luyện mô hình là tác vụ riêng:

```bat
.venv\Scripts\python.exe -m prediction.main --train
```

## Hai loại dự báo

| Nội dung | Sau 30 phút | Ngày mai |
| --- | --- | --- |
| Mục tiêu | Thời điểm mẫu xe đầu vào + 30 phút | Từng giờ của ngày kế tiếp theo New York |
| Phương pháp | Random Forest với đặc trưng xe, biến động gần đây, thời gian và thời tiết; có mô hình cơ sở đối chứng | Chọn theo trạm giữa các phương pháp theo lịch và phương pháp kết hợp mức xe, xu hướng gần đây |
| Đối chiếu | Ghép dự báo với mẫu thực tế ở thời điểm mục tiêu | Chấm sau khi giờ mục tiêu kết thúc và đủ độ phủ mẫu thực tế |
| Giao diện | Thẻ dự báo và trang lịch sử riêng của trạm | Biểu đồ từng giờ và bảng chênh lệch của hôm qua |

Số xe dự báo hiển thị được làm tròn. Việc đánh giá mô hình dùng giá trị gốc để tránh mất thông tin sai số.

Mô hình thời tiết đã được kích hoạt theo chế độ thử nghiệm. Lần đánh giá lưu ngày **16/11/2026**, trên cùng 3.110 mẫu kiểm thử, ghi nhận MAE khoảng **1,88 xe** cho Random Forest có thời tiết và **1,52 xe** cho mô hình cơ sở giữ nguyên số xe. Đây là kết quả kiểm thử đã lưu, không phải chỉ số trực tiếp và chưa chứng minh mô hình thời tiết tốt hơn. Xem [báo cáo tổng hợp](PROJECT_REPORT.md).

Dự báo ngày mai kết hợp thứ và giờ cần dự báo, mức xe hiện tại, xu hướng gần đây và thay đổi so với tuần trước. Phương pháp được chọn bằng dữ liệu xác thực theo từng trạm, chỉ sử dụng thông tin có trước thời điểm phát hành.

Bản dự báo được lưu một lần mỗi ngày New York, giữ nguyên bản đã phát hành và lưu kết quả đối chiếu riêng. Chỉ chấm giờ đã kết thúc, qua thời gian chờ thu thập và có ít nhất 80% mẫu thực tế hợp lệ. Giờ chưa đủ dữ liệu sẽ tiếp tục chờ.

Lịch Prediction thông thường đã tích hợp phát hành và chấm dự báo ngày mai. Nếu chỉ muốn chạy riêng phần này, chọn chạy một lần hoặc kiểm tra mỗi 5 phút:

```bat
.venv\Scripts\python.exe -m prediction.main --day-ahead
.venv\Scripts\python.exe -m prediction.main --day-ahead-schedule
```

Dự báo ngày mai không sử dụng trực tiếp mô hình thời tiết của mục tiêu 30 phút.

## Báo cáo EDA

Khi `EDA_AUTO_UPDATE=true`, API kiểm tra thay đổi dữ liệu khi khởi động và mỗi 15 phút. Nếu có thay đổi, tiến trình nền tạo báo cáo mới từ 28 ngày gần nhất, tối đa 200.000 mẫu. Giao diện kiểm tra báo cáo hoàn tất mỗi phút; báo cáo cũ vẫn được giữ nếu lần tạo mới thất bại.

Để tạo thủ công:

```bat
.venv\Scripts\python.exe -m eda.main --days 28 --max-rows 200000
```

Kết quả gồm HTML, JSON, CSV và ảnh biểu đồ trong `artifacts/eda/`. API đọc báo cáo hoàn tất gần nhất tại `API_EDA_REPORT_DIR`. Tự cập nhật chỉ hoạt động khi API đang chạy.

## Kiểm thử

Từ thư mục gốc:

```bat
.venv\Scripts\python.exe -m pytest
```

Từ thư mục `frontend`:

```bat
npm test
npm run build
```

Kiểm thử trình duyệt dùng Playwright. Xem cấu hình trong `frontend/playwright.config.js` để chuẩn bị môi trường:

```bat
npx playwright install chromium
npm run test:browser
```

## Docker và GitHub Actions

Docker Compose sử dụng MySQL/Aiven hiện có qua `.env`, không tạo một MySQL mới:

```bat
docker compose up --build database-api frontend
```

Website Docker chạy tại http://127.0.0.1:8080. Có thể gọi riêng một tác vụ, ví dụ:

```bat
docker compose --profile jobs run --rm data-ingestion
```

Các workflow trong `.github/workflows/` hỗ trợ chạy thủ công và theo lịch, dùng secrets/variables của repository thay cho `.env` trên máy cá nhân. Lịch cloud được cấu hình riêng với lịch CLI; xem [hướng dẫn GitHub Actions và Aiven](docs/Deploy_GitHub_Actions_Aiven.md).

Bronze trên GitHub Actions được lưu bằng artifact với thời hạn 7 ngày. Cần sao lưu riêng nếu muốn giữ lâu hơn; dữ liệu MySQL và mô hình/báo cáo cục bộ không tự đi kèm repository.

## Tài liệu

- [Báo cáo tổng hợp đề tài](PROJECT_REPORT.md)
- [Kết nối Aiven trên Windows](docs/Ket_Noi_Aiven_Windows.md)
- [API](docs/FastAPI.md)
- [Giao diện](frontend/README.md)
- [Phân tích dữ liệu](docs/Data_Analysis.md)
- [Báo cáo EDA](docs/EDA.md)
- [Dự báo và đánh giá](docs/Prediction.md)
- [Đánh giá dự báo ngày mai](docs/Day_Ahead_Evaluation.md)

# NewYorkBike — Dự đoán số xe Citi Bike sau 30 phút

**Tên đề tài:** Dự đoán số xe đạp công cộng có thể thuê tại các trạm Citi Bike ở New York trong 30 phút tới dựa trên thời tiết và thời gian.

Dự án theo dõi 10 trạm nghiên cứu, thu thập dữ liệu xe và thời tiết, phân tích, phân nhóm trạm và dự đoán số xe có thể thuê sau 30 phút. Giao diện và biểu đồ dùng tiếng Việt; tên riêng trạm, đường phố giữ nguyên để tra cứu địa điểm.

## 1. Kiến trúc

```text
Citi Bike GBFS + Open-Meteo
             │
      Thu thập dữ liệu ──────► Bronze: phản hồi gốc + manifest
             │
             ▼
      MySQL / Aiven: Silver
             │
     ┌───────┼───────────┐
     ▼       ▼           ▼
 Phân tích  Phân nhóm   Dự đoán +30 phút
     └───────┴───────────┘
             │
             ▼
      MySQL / Aiven: Gold
             │
             ▼
      FastAPI ──────► React
```

| Thành phần | Công nghệ / nhiệm vụ |
|---|---|
| Giao diện | React, Vite, React Router, Leaflet; [nguồn bản đồ](docs/Map_Display.md) |
| API | Python + FastAPI, đọc dữ liệu và kết quả đã công bố |
| Database | MySQL; môi trường hiện tại dùng Aiven |
| Thu thập — Ingestion | Đọc API nguồn, lưu phản hồi gốc và dữ liệu chuẩn hóa |
| Phân tích — Analysis | Thống kê theo trạm, giờ/ngày và chất lượng dữ liệu |
| Phân nhóm — Clustering | Chuẩn hóa đặc trưng hành vi và phân nhóm K-means |
| Dự đoán — Prediction | Mô hình cơ sở và pipeline học máy rừng ngẫu nhiên |
| Khám phá dữ liệu — EDA | Báo cáo HTML, CSV và 12 biểu đồ theo yêu cầu |

Bốn dịch vụ dữ liệu chạy độc lập, có thể mở mỗi dịch vụ ở một terminal riêng. Mở website không khởi chạy thu thập, phân nhóm hoặc huấn luyện. Huấn luyện học máy là lệnh riêng, tách khỏi lịch phát hành dự đoán.

## 2. Trạng thái đã kiểm tra

**Cập nhật Clustering ngày 10/11/2026:** đã chạy và công bố thành công
`clustering_run=5`, phiên bản `clustering-v2-cadence`, cửa sổ 03–09/11 theo
New York. Cả 10 trạm đạt điều kiện, chia thành 3 nhóm (2, 5, 3 trạm), điểm
tách nhóm 0,428. Đã kiểm tra Aiven, API và giao diện. Bằng chứng:
[kết quả phân nhóm](docs/clustering_behavior_verification_20261110.json).
Đây là phân nhóm hành vi trạm, không phải phân loại ít/nhiều xe ngày mai.

**Mốc xác minh gần nhất trong tài liệu này: ngày 09/11/2026.** Đây là kết quả tại thời điểm kiểm tra, không phải trạng thái trực tiếp mỗi lần đọc README.

- Thu thập, Analysis và Prediction đã chạy trên Aiven/GitHub; khoảng cách giữa các lượt gần nhất là 5 phút.
- Đã có FastAPI chỉ đọc và React với 5 trang: Tổng quan, Bản đồ trạm, Chi tiết trạm, Phân tích & phân nhóm, Dự đoán +30 phút. Website đang chạy cục bộ.
- 10/10 trạm có dữ liệu mới hợp lệ tại lần kiểm tra.
- Clustering đã chạy lại nhưng chưa có nhóm: ngày 02/11 trong cửa sổ 7 ngày có độ phủ dưới ngưỡng 80% mỗi ngày. Chưa xác nhận lịch Clustering ổn định hằng ngày.
- Có 8 ngày và 3.388 cặp mẫu đủ đặc trưng học máy, chưa đạt ngưỡng 14 ngày. Dự đoán hiện dùng mô hình cơ sở: giữ nguyên số xe ở mẫu đầu vào.
- Kiểm thử lịch sử mô hình cơ sở trên 530 mẫu: MAE **2,31 xe**, RMSE **3,59 xe**. Chưa có kết quả so sánh với mô hình học máy được huấn luyện hợp lệ.
- Bản sửa độ phủ theo lịch 30 → 5 phút đã có ở máy phát triển; Analysis trên GitHub tại lần kiểm tra vẫn chạy `analysis-v1`, chưa có bản sửa này.

Chi tiết: [Tài liệu tổng hợp](PROJECT_REPORT.md).

## 3. Nguồn và quy tắc dữ liệu

**Citi Bike:** đọc [GBFS discovery](https://gbfs.citibikenyc.com/gbfs/gbfs.json) để tìm `station_information` và `station_status`, kiểm tra phiên bản rồi ghép bằng `station_id` dạng chuỗi. Không cần `SEOUL_API_KEY`.

**Thời tiết:** gọi `https://api.open-meteo.com/v1/forecast` theo tọa độ từng trạm, lấy nhiệt độ, độ ẩm, mưa và tốc độ gió. Thời tiết đủ mới có thể được dùng lại; giữ đơn vị, kỳ đo, thời điểm và tọa độ yêu cầu.

- **Bronze:** phản hồi API gốc và manifest từng lần thu, kèm thông tin kiểm tra toàn vẹn.
- **Silver:** dữ liệu trạm, quan sát xe, thời tiết và liên kết trong MySQL.
- **Gold:** kết quả phân tích, phân nhóm và dự đoán để API/giao diện đọc.
- Lưu thời gian **UTC**, hiển thị theo **America/New_York**, xử lý đổi giờ theo mùa. Thời điểm nguồn, thu thập, phát hành và mục tiêu dự đoán được lưu riêng.
- Không thay dữ liệu thiếu bằng 0; phân biệt dữ liệu cũ và trạm ngừng cho thuê.
- Chống ghi trùng bằng khóa dữ liệu và khóa dịch vụ. Không tự bù dữ liệu thời gian thực đã bỏ lỡ hoặc tạo kết quả giả.
- Sức chứa dùng `capacity`, giữ `rack_count` cũ. Dữ liệu Seoul cũ có định danh nguồn riêng, không trộn với Citi Bike.

Xem [Bronze/Silver/Gold](docs/Bronze_Silver_Gold.md) và [yêu cầu đề tài](docs/Yeu_Cau_Web_Seoul_Bike.md). Tên tệp đặc tả cũ được giữ để các liên kết còn hoạt động.

## 4. Cài đặt trên Windows

Cần Python 3.12 hoặc 3.13, Node.js 22.12 trở lên và MySQL 8.0.16 trở lên hoặc thông tin kết nối Aiven. Các lệnh Python chạy từ thư mục gốc dự án.

```powershell
cd F:\126\NewYorkBike
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Nếu đã có `.venv`, dùng môi trường đó và cài phụ thuộc còn thiếu. `requirements.txt` gồm phụ thuộc cho API, các dịch vụ, EDA và kiểm thử. Gọi trực tiếp Python trong `.venv` giúp tránh dùng nhầm Python hệ thống.

**Chỉ tạo `.env` nếu chưa có**, sau đó điền thông tin thật:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

| Cấu hình | Cách điền |
|---|---|
| `MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_DATABASE` | Máy chủ, cổng và tên database thực tế |
| `MYSQL_USER`, `MYSQL_PASSWORD` | Tài khoản MySQL của bạn |
| `MYSQL_SSL_CA` | Với Aiven: đường dẫn CA, ví dụ `certs/aiven-ca.pem` |
| `STATION_IDS` | Mã trạm thật dạng chuỗi, phân cách bằng dấu phẩy |
| `BIKE_SOURCE` | `citibike` |
| `DISPLAY_TIMEZONE` | `America/New_York` |
| `OUTBOUND_PROXY_ENABLED` | `true` nếu muốn các yêu cầu nguồn đi qua proxy |
| `OUTBOUND_PROXY_URLS` | Mảng JSON chứa URL proxy thật |
| `SAMPLING_SCHEDULE_FILE` | `config/sampling_schedule.json`, để tính độ phủ theo lịch lịch sử |

Các mặc định khác nằm trong [.env.example](.env.example). Giữ tên database thực tế kể cả khi tên còn là `seoul_bike`; không cần đổi tên hoặc xóa dữ liệu. Không đưa `.env`, mật khẩu, token hoặc chứng chỉ riêng lên Git. Không đặt bí mật trong `VITE_*` vì trình duyệt đọc được chúng.

Kiểm tra kết nối:

```powershell
.\.venv\Scripts\python.exe -m scripts.check_database
```

Hướng dẫn: [kết nối Aiven trên Windows](docs/Ket_Noi_Aiven_Windows.md).

## 5. Migration database

Với database mới hoặc đã được Alembic quản lý:

```powershell
.\.venv\Scripts\python.exe -m alembic current
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic current
```

Đầu chuỗi migration hiện tại là `0006_prediction`. Migration tạo/cập nhật schema, không cần tạo từng bảng bằng tay. Sao lưu database có dữ liệu trước khi nâng schema. Nếu có collector cloud đang chạy, bảo đảm mã trên nhánh triển khai tương thích trước khi nâng.

Database có bảng tạo tay nhưng chưa có Alembic cần được kiểm tra bằng `scripts.adopt_legacy_schema` trước; không tự `stamp head` để bỏ qua lỗi. Các báo cáo migration cũ trong `docs/` chỉ ghi trạng thái tại ngày kiểm tra tương ứng.

## 6. Chạy từng dịch vụ một lần

Sau khi có cấu hình và schema phù hợp, chọn lệnh cần dùng, không cần chạy tất cả mỗi lần mở website:

| Công việc | Lệnh từ thư mục gốc |
|---|---|
| Liệt kê 10 trạm thật, không ghi database | `.\.venv\Scripts\python.exe -m ingestion.main --list-stations --limit 10` |
| Thu thập một lần, ghi Bronze và Silver | `.\.venv\Scripts\python.exe -m ingestion.main --once` |
| Xem trước Analysis, không ghi database | `.\.venv\Scripts\python.exe -m analysis.main --preview` |
| Phân tích một lần, lưu Gold | `.\.venv\Scripts\python.exe -m analysis.main --once` |
| Xem trước phân nhóm | `.\.venv\Scripts\python.exe -m clustering.main --preview` |
| Phân nhóm một lần, lưu trạng thái/kết quả | `.\.venv\Scripts\python.exe -m clustering.main --once` |
| Xem trước dự đoán và điều kiện huấn luyện | `.\.venv\Scripts\python.exe -m prediction.main --preview` |
| Phát hành dự đoán và đối chiếu dự đoán đã đến hạn | `.\.venv\Scripts\python.exe -m prediction.main --once` |
| Huấn luyện riêng khi đủ điều kiện | `.\.venv\Scripts\python.exe -m prediction.main --train` |

Các lệnh xem trước lưu báo cáo trong `artifacts/`. Mặc định Clustering yêu cầu 7 ngày đã hoàn tất, ít nhất 6 trạm đủ điều kiện và độ phủ tối thiểu 80% mỗi ngày. Huấn luyện yêu cầu tối thiểu 14 ngày cùng các ngưỡng số mẫu; đủ ngày không bảo đảm mô hình học máy tốt hơn mô hình cơ sở.

Mục tiêu luôn là **thời điểm mẫu đầu vào +30 phút**, không phải thời điểm mở web +30 phút. Huấn luyện chia dữ liệu theo thời gian, chọn mô hình bằng tập xác thực và đánh giá trên tập kiểm thử riêng. Chi tiết: [Prediction](docs/Prediction.md).

## 7. Lịch tự động và cách dừng

| Dịch vụ | Lịch đám mây ghi nhận ngày 09/11/2026 | Lịch CLI cục bộ `--schedule` |
|---|---|---|
| Thu thập | Kích hoạt bên ngoài mỗi 5 phút | Lấy ngay, sau đó phút **00 và 30** |
| Analysis | Kích hoạt bên ngoài mỗi 5 phút | Chạy ngay, sau đó mỗi 5 phút |
| Prediction | Kích hoạt bên ngoài mỗi 5 phút, lệch khoảng 2 phút sau mốc thu | Chạy ngay, sau đó mỗi 5 phút |
| Clustering | GitHub khai báo mỗi ngày 07:00 UTC; chưa xác nhận ổn định hằng ngày | Chạy ngay, sau đó 02:00 New York mỗi ngày |

Lịch kích hoạt và lịch kỳ vọng để tính độ phủ là hai cấu hình riêng. `config/sampling_schedule.json` ghi mốc chuyển thu thập từ 30 sang 5 phút: **09/11/2026 06:25 New York = 11:25 UTC = 18:25 Việt Nam**. Không áp chu kỳ 5 phút ngược lên dữ liệu cũ.

Ở máy cá nhân, thêm `--schedule` thay cho `--once`, giữ terminal mở và nhấn **Ctrl+C** để dừng. Không chạy thêm lịch cục bộ cho cùng dịch vụ nếu lịch cloud đang ghi vào cùng database. Tắt laptop sẽ dừng tiến trình cục bộ; GitHub Actions và Aiven hoạt động độc lập.

GitHub có thể kích hoạt trễ. Nếu dùng cron-job.org, chỉ bật một nguồn lịch cho mỗi dịch vụ và đối chiếu lượt chạy với dữ liệu thực tế. Xem [GitHub Actions/Aiven](docs/Deploy_GitHub_Actions_Aiven.md) và [độ phủ khi đổi chu kỳ](docs/Do_Phu_Lich_Thu_Thap.md).

## 8. Mở website

**Terminal 1 — FastAPI**, từ thư mục gốc:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --log-level error --no-access-log
```

**Terminal 2 — React:**

```powershell
cd F:\126\NewYorkBike\frontend
npm ci
npm run dev
```

- Giao diện: **http://127.0.0.1:5173**.
- Tài liệu thử API: **http://127.0.0.1:8000/docs**.
- Giao diện tự tải lại dữ liệu mỗi phút; nút **Làm mới** không chạy lại dịch vụ.
- Dấu `—` thể hiện thiếu kết quả phù hợp; số 0 vẫn là 0.
- Dự đoán hết hạn, trạm ngừng cho thuê và mẫu quá cũ có nhãn riêng.

Cấu hình API ở máy khác, CORS và bản dựng: [FastAPI](docs/FastAPI.md) · [React](frontend/README.md).

## 9. Tạo biểu đồ khám phá dữ liệu

Trên web, các biểu đồ đường/phân tán/phân phối có ô chọn **ngày, tuần hoặc
tháng cụ thể** và chọn trạm; dữ liệu của kỳ được đọc trực tiếp từ Aiven theo
lịch New York. Kỳ chưa có dữ liệu hiển thị trống. Các ảnh xu hướng, mùa vụ,
tương quan và bảng thống kê vẫn thuộc báo cáo EDA đã tạo.

Đã bổ sung biểu đồ đường/phân tán/phân phối theo ngày, tuần, tháng; xu hướng và
mùa vụ theo tuần khi dữ liệu ngắn. Trang Dự đoán có dự báo từng giờ ngày mai,
phân loại mức xe sẵn có và làm nổi bật giờ ít xe bằng mô hình cơ sở, tách riêng mục tiêu +30 phút.
Chi tiết điều kiện, phương pháp và giới hạn: [yêu cầu chuỗi thời gian](docs/Time_Series_Requirements.md).

```powershell
.\.venv\Scripts\python.exe -m eda.main --days 28
```

Lệnh chỉ đọc database, xuất báo cáo vào `artifacts/eda/`. Mở `report.html` ở đường dẫn log hoặc vào **Phân tích & phân nhóm → Khám phá dữ liệu (EDA)** trên web. API đọc báo cáo hoàn tất gần nhất đúng nguồn tại máy chạy API.

Báo cáo có trung bình, trung vị, độ lệch chuẩn, giá trị phổ biến, độ phủ, dữ liệu thiếu, ngoại lệ, phân phối, tương quan và so sánh chuẩn hóa. Cờ ngoại lệ chỉ để xem xét, không tự xóa mẫu. Tham số chuẩn hóa chỉ tính từ tập huấn luyện. Biểu đồ xuất mới có tiêu đề, nhãn trục, chú giải và thứ trong tuần bằng tiếng Việt.

API tự kiểm tra dữ liệu mới khi khởi động và mỗi 15 phút, tạo báo cáo EDA trong tiến trình nền riêng (28 ngày, tối đa 200.000 mẫu). Web tải báo cáo hoàn tất mỗi phút. Nếu dữ liệu không đổi thì bỏ qua; thêm lịch sử hoặc thời tiết sẽ làm báo cáo được tạo lại. Báo cáo cũ vẫn dùng được nếu lần tạo mới lỗi. Đặt `EDA_AUTO_UPDATE=false` để tắt; `API_EDA_REPORT_DIR` xác định nơi lưu. Chỉ hoạt động khi API đang chạy; không tự triển khai lên GitHub.

Riêng dự báo ngày mai được Prediction phát hành một lần mỗi ngày New York và lưu trong `luot_chay_dich_vu` với loại `day_ahead`. Worker tự chấm các giờ đã kết thúc khi đủ 80% mẫu thật; web chỉ đọc qua `/api/eda/day-ahead`, tách sai số thực tế khỏi kiểm thử lịch sử. Có thể chạy riêng bằng `python -m prediction.main --day-ahead`, hoặc bật `--day-ahead-schedule` để kiểm tra mỗi năm phút; lịch Prediction thường cũng đã tích hợp bước này. Khi chuyển máy, sao chép cả thư mục EDA gồm HTML, JSON, CSV và ảnh để giữ các báo cáo cũ. Xem [EDA](docs/EDA.md).

## 10. Kiểm tra và sao lưu

Kiểm tra dịch vụ trên Aiven bằng lệnh chỉ đọc:

```powershell
.\.venv\Scripts\python.exe -m scripts.audit_services
```

Kết quả tại `artifacts/service_audit/database.json`: thời điểm chạy, độ mới từng trạm, mô hình và sai số dự đoán đã đối chiếu. Lệnh không kiểm tra lịch cron-job.org hoặc GitHub; cần xem riêng tab Actions và lịch bên ngoài.

Bronze trên GitHub được lưu thành artifact từng lượt, hiện giữ **7 ngày**. Silver trong Aiven không tự mất sau 7 ngày, nhưng không thay thế phản hồi gốc. Tải Bronze trước khi hết hạn và sao lưu MySQL riêng. Sau khi cài GitHub CLI và đăng nhập, tải hàng loạt từ thư mục gốc:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\backup_github_bronze.ps1 -Repository bap-05/NewYorkBike
```

Nếu dùng repository khác, thay `bap-05/NewYorkBike`. Tệp được lưu dưới `backups/bronze/`; manifest liên kết dữ liệu gốc với lượt thu trong database. Xem [cách lưu và đọc Bronze](docs/Bronze_Silver_Gold.md).

## 11. Kiểm thử mã

Từ thư mục gốc:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Từ thư mục `frontend`:

```powershell
npm test
npm run build
```

Kiểm tra trình duyệt với API/database thật và báo cáo EDA đã tạo:

```powershell
npx playwright install chromium
npm run test:browser
```

Giữ FastAPI cổng 8000 hoạt động trước kiểm tra trình duyệt. Kiểm thử cô lập có thể dùng dữ liệu kiểm thử riêng; không tạo dữ liệu giả vào database vận hành.

## 12. Thư mục chính và việc còn lại

```text
NewYorkBike/
├── frontend/              # React và kiểm thử trình duyệt
├── services/
│   ├── database-api/app/  # FastAPI chỉ đọc
│   ├── data-ingestion/   # Thu thập, client API và lưu Bronze
│   ├── data-analysis/    # Thống kê Gold; EDA trong eda/
│   ├── clustering/       # Đặc trưng và phân nhóm trạm
│   └── prediction/       # Dự đoán, đánh giá và huấn luyện riêng
├── shared/                # Model, kết nối, thời gian và lịch dữ liệu dùng chung
├── database/migrations/   # Migration Alembic
├── config/                # Danh sách trạm và lịch thu thập lịch sử
├── scripts/               # Kiểm tra, sao lưu và runner GitHub
├── .github/workflows/     # Workflow độc lập cho bốn dịch vụ
├── docs/                  # Yêu cầu, hướng dẫn và bằng chứng kiểm tra
└── .env.example           # Mẫu cấu hình, không chứa bí mật thật
```

**Sau khi đổi bố cục**, cài lại ánh xạ package bằng
`.\.venv\Scripts\python.exe -m pip install -r requirements.txt`.
Tên import và các lệnh `python -m ...` giữ nguyên. Khi dùng API tự nạp lại mã,
chọn `--reload-dir services/database-api --reload-dir shared`.
Docker, file cấu hình theo môi trường và các báo cáo gốc được giải thích trong
[Tài liệu tổng hợp](PROJECT_REPORT.md).

Các việc ưu tiên sau mốc kiểm tra 09/11/2026:

1. Đưa bản sửa độ phủ vào nhánh thực sự chạy workflow và xác minh kết quả cloud.
2. Xác minh lịch Clustering hằng ngày và điều kiện các trạm khi cửa sổ dịch sang ngày mới.
3. Tiếp tục thu đủ dữ liệu, huấn luyện riêng khi đạt điều kiện, so sánh mô hình cơ sở với mô hình học máy có/không có thời tiết trên cùng tập đánh giá.
4. Hoàn thiện sao lưu dài hạn, triển khai API và giao diện nếu cần đường dẫn trình diễn công khai.

Tài liệu chi tiết: [Tài liệu tổng hợp](PROJECT_REPORT.md) · [Analysis](docs/Data_Analysis.md) · [Clustering](docs/Clustering.md) · [Prediction](docs/Prediction.md). Giữ thư mục `docs/` để còn hướng dẫn vận hành và bằng chứng phục vụ báo cáo đề tài.

Bản báo cáo kỹ thuật và câu hỏi bảo vệ: [Tài liệu tổng hợp](PROJECT_REPORT.md).


## T?n b?ng v? c?t trong MySQL

T? migration `0007_vietnamese_names`, c?c b?ng nghi?p v? d?ng t?n ti?ng Vi?t kh?ng d?u, v? d? `tram_xe`, `lich_su_so_xe`, `ket_qua_phan_tich`, `du_doan_so_xe`. Xem [b?ng ?nh x? v? c?ch truy v?n](docs/Ten_Bang_Tieng_Viet.md). T?n c? ???c gi? d??i d?ng VIEW t??ng th?ch cho c?c l?ch ?ang ch?y.

# Tổng hợp dự án NewYorkBike

Cập nhật tài liệu: 16/11/2026. File này nằm tại thư mục gốc, ngoài `docs/`. Các số liệu đánh giá là kết quả những lần chạy đã lưu, không phải trạng thái trực tiếp của DB tại thời điểm đọc.

## 1. Mục tiêu và kiến trúc

Dự án thu thập số xe có thể thuê tại 10 trạm Citi Bike ở New York, kết hợp thời tiết để phân tích chuỗi thời gian, phân cụm hành vi trạm và dự báo. Giao diện dùng tiếng Việt; tên riêng của trạm được giữ nguyên để đối chiếu nguồn.

```mermaid
flowchart LR
    S[Citi Bike và Open-Meteo] --> I[Thu thập]
    I --> B[Bronze: phản hồi nguồn và manifest]
    I --> DB[(MySQL / Aiven)]
    DB --> A[Phân tích]
    DB --> C[Phân cụm]
    DB --> P[Dự báo]
    A --> DB
    C --> DB
    P --> DB
    DB --> API[FastAPI]
    API --> WEB[React / Vite]
```

Bốn dịch vụ thu thập, phân tích, phân cụm và dự báo chạy độc lập. Frontend đọc kết quả qua API. Mở web không tự huấn luyện hoặc chạy lại các dịch vụ. Khi API chạy, EDA kiểm tra dữ liệu mới mỗi 15 phút và tạo báo cáo bằng tiến trình nền riêng; web tải báo cáo hoàn tất mỗi phút.

Các chức năng hiển thị gồm biểu đồ đường, phân tán, phân phối theo ngày/tuần/tháng; xu hướng, mùa vụ, tương quan; bản đồ nhóm trạm; dự báo +30 phút và dự báo từng giờ ngày mai.

Số xe sẵn có là trạng thái tồn xe tại trạm, khác với số lượt thuê. Thời gian lưu theo UTC, hiển thị theo `America/New_York`, có phân biệt EST/EDT.

## 2. Bố cục thư mục

```text
NewYorkBike/
├── config/                  # Trạm, nhịp lấy mẫu, SQL khởi tạo
├── frontend/                # React, Vite, Leaflet
├── services/
│   ├── data-ingestion/      # Thu thập
│   ├── data-analysis/       # Phân tích; chứa eda/
│   ├── clustering/          # Phân cụm
│   ├── prediction/          # Huấn luyện, dự báo, đánh giá
│   └── database-api/        # FastAPI
├── shared/                  # Cấu hình, mô hình DB và truy vấn chung
├── database/migrations/     # Nâng cấp cấu trúc DB
├── scripts/                 # Nhập lịch sử, sao lưu, chạy GitHub
├── tests/
├── data/                    # Gồm dữ liệu Bronze
├── artifacts/               # Báo cáo, kết quả và biên nhận
├── backups/
├── docs/                    # Tài liệu chuyên đề
├── .github/workflows/
├── docker-compose.yml
├── pyproject.toml
├── README.md
└── PROJECT_REPORT.md
```

Tên module Python được ánh xạ tới thư mục dịch vụ trong `pyproject.toml`. Cần cài dependencies trước khi chạy `python -m ...`.

## 3. Dữ liệu và cơ sở dữ liệu

- **Bronze:** phản hồi nguồn và manifest SHA-256 phục vụ truy vết.
- **Silver:** mẫu xe, thời tiết, liên kết xe–thời tiết và trạng thái chất lượng đã chuẩn hóa.
- **Gold:** kết quả phân tích, phân cụm, phiên bản mô hình và dự báo đã công bố.

Mẫu lỗi và khoảng thiếu không được coi là số xe bằng 0. Mỗi thuật toán có điều kiện độ phủ, thời gian và chất lượng riêng.

Migration `0007_vietnamese_names` đổi tên bảng/cột nghiệp vụ sang tiếng Việt không dấu. Thuộc tính Python và khóa JSON API vẫn có thể dùng tiếng Anh. VIEW tương thích tên cũ không phải bản sao dữ liệu.

| Tên cũ | Bảng chính |
| --- | --- |
| stations | tram_xe |
| collection_runs | luot_thu_thap |
| bike_observations | lich_su_so_xe |
| weather_observations | lich_su_thoi_tiet |
| observation_weather_links | lien_ket_xe_thoi_tiet |
| service_runs | luot_chay_dich_vu |
| analysis_results | ket_qua_phan_tich |
| clustering_runs | luot_phan_cum |
| station_clusters | nhom_tram |
| model_versions | phien_ban_mo_hinh |
| training_jobs | luot_huan_luyen |
| predictions | du_doan_so_xe |

Bảng `alembic_version` theo dõi migration. Ánh xạ chi tiết nằm trong [shared/database_names.py](shared/database_names.py).

### Lịch sử đã bổ sung

- Tháng 10: nhập 89.270 mẫu vào cùng bảng chính `lich_su_so_xe`, phân biệt bằng nguồn `citibike_historical`; 88.472 mẫu hợp lệ. Có 7.440 bản ghi thời tiết và 89.270 liên kết.
- Tháng 11: bổ sung 22.535 mẫu thực hợp lệ từ Parquet vào bảng chính, nguồn `citibike`, cùng dữ liệu thu trực tiếp; bỏ qua ô thời gian đã có mẫu hợp lệ. Thêm 2.210 bản ghi thời tiết và 22.535 liên kết.
- File tháng 11 kết thúc tại 23:59:19 UTC ngày 12/11/2026, tức 18:59:19 New York. File này không cung cấp mẫu thật cho các khoảng trống sau đó.
- Đã xóa 1.850 mẫu ước lượng bù thiếu theo yêu cầu, giữ dữ liệu thật. Công cụ tạo ước lượng lịch sử cũ đã được gỡ.

Thời tiết ERA5 và kho dự báo lịch sử có nguồn gốc riêng. Không mặc định coi thời tiết hồi cứu là thông tin đã có tại thời điểm phát hành dự báo trong quá khứ.

EDA đã được sửa để đọc thêm nguồn lưu trữ tháng 10. Thêm dữ liệu vào DB không tự khiến mọi mô hình sử dụng toàn bộ nguồn đó.

## 4. Các thuật toán

### Phân tích và EDA

Phân tích tổng hợp thống kê theo thời gian và công bố kết quả đạt chất lượng. EDA tạo ảnh chụp báo cáo với biểu đồ đường, phân tán, phân phối, xu hướng, mùa vụ và tương quan.

Mùa vụ theo tuần cần ít nhất hai tuần lịch hoàn chỉnh đạt điều kiện độ phủ. Lần kiểm tra sau khi bổ sung nguồn lưu trữ ngày 13/11/2026 có 80.190 dòng trong cửa sổ 28 ngày; cả 10 trạm đã có đường mùa vụ. Đây là kết quả đã lưu của lần chạy đó.

Phần EDA được bổ sung phân rã STL ngày 18/11/2026: chuỗi gốc trung bình theo giờ được tách thành xu hướng, mùa vụ chu kỳ 24 giờ và phần dư, riêng từng trạm. Chỉ tính trên đoạn liên tục gần nhất có ít nhất 7 ngày, mỗi giờ đạt độ phủ từ 80%; không nội suy giờ thiếu hoặc dùng mẫu ước lượng. Ngắt đoạn tại thay đổi UTC offset để giữ chu kỳ theo giờ địa phương. Kết quả là phân tích hồi cứu, không dùng làm đầu vào dự báo. Xem [điều kiện phân rã và tệp xuất](docs/EDA.md#phân-rã-chuỗi-thời-gian-theo-trạm).

### Phân cụm hành vi trạm

Các đặc trưng hành vi được chuẩn hóa rồi phân nhóm bằng K-means, có đánh giá lựa chọn số nhóm bằng silhouette. Đầu vào cần 7 ngày địa phương hoàn tất, độ phủ mỗi ngày tối thiểu 80% và ít nhất 6 trạm đủ điều kiện.

Kết quả giúp tìm các trạm có nhịp tồn xe tương tự, tô màu nhóm trên bản đồ và giải thích đặc trưng nhóm. Nhóm phân cụm khác với nhãn ít xe/trung bình/nhiều xe của dự báo.

### Dự báo sau 30 phút có thời tiết

Mô hình thử nghiệm là **Random Forest hồi quy**. Đầu vào gồm số xe hiện tại, độ trễ 30 phút, biến động số xe, giờ, thứ, cuối tuần, nhiệt độ, độ ẩm, mưa và gió.

Dữ liệu được chia theo thời gian thành tập huấn luyện, xác thực và kiểm thử. Mô hình cơ sở giữ nguyên số xe hiện tại để dự báo sau 30 phút. Kết quả đã lưu ngày 13/11/2026 trên 1.906 mẫu kiểm thử:

| Mô hình | MAE (xe) | RMSE (xe) |
| --- | ---: | ---: |
| Cơ sở: giữ nguyên số xe | 0,888 | 1,507 |
| Random Forest có thời tiết | 1,486 | 2,190 |

MAE là sai lệch tuyệt đối trung bình; RMSE nhạy hơn với các lần sai lớn. Hai chỉ số càng thấp càng tốt. Trong lần đánh giá này mô hình thời tiết kém hơn cơ sở, nên được bật dưới dạng **thử nghiệm** theo lựa chọn của người dùng.

Lần đánh giá ngày 13/11 có 12 ngày hợp lệ; huấn luyện chính thức yêu cầu tối thiểu 14 ngày cùng các điều kiện mẫu/chất lượng khác. Đủ 14 ngày không tự tạo mô hình: phải chạy huấn luyện và xem kết quả đánh giá.

Đối chiếu bổ sung ngày 16/11 trên **7.514 mốc dự báo thật đã phát hành** sau lần đánh giá trước, khử trùng theo trạm/mục tiêu: mô hình thời tiết đang chạy (#2) có MAE **1,829**, RMSE **2,634**; cơ sở giữ nguyên số xe ở cùng mẫu đầu vào có MAE **1,438**, RMSE **2,329**. Mô hình thời tiết có MAE cao hơn **27,25%**, kém hơn tại cả 10 trạm. Các mốc cách nhau 5 phút có tương quan; chưa đủ bằng chứng đưa mô hình thử nghiệm thành mô hình chính thức. Chỉ lấy các mục tiêu có kết quả thực tế đã được worker chấm, không tính những mục tiêu còn thiếu đối chiếu. Chi tiết: [đối chiếu dự báo đã phát hành](artifacts/prediction_weather_live/20261116T141249Z/report.md).

**Huấn luyện và đánh giá lại ngày 16/11:** 44.340 quan sát nguồn chính, 20.630 mẫu đủ biến xe và thời tiết, 15 ngày hợp lệ (02–16/11, New York). Chia thời gian thành 14.370 mẫu train, 3.040 validation, 3.110 test; loại 110 mẫu vượt ranh giới đáp án. Trên cùng tập test: cơ sở MAE **1,517**, RMSE **2,547**; Random Forest có thời tiết MAE **1,877**, RMSE **2,716**; Random Forest không thời tiết cũng đạt **1,877 / 2,716**. Hai biến thể chọn độ sâu 4 bằng validation; mô hình có thời tiết được chọn không dùng biến thời tiết ở nút chia nào. MAE thời tiết cao hơn cơ sở **23,74%**. Đủ ngưỡng dữ liệu tối thiểu nhưng chưa đạt hiệu quả để chuyển thành chính thức. Lần này chỉ lưu mô hình/báo cáo đánh giá tại máy, không kích hoạt mô hình mới. [Báo cáo đánh giá lại](artifacts/prediction_weather/20261116T141123Z/report.md).

Thiếu thời tiết hoặc độ trễ phù hợp có thể dẫn tới dùng mô hình cơ sở. Mẫu xe lỗi hoặc quá cũ có thể không có dự báo. Giao diện làm tròn số xe; tính toán và chấm sai số vẫn dùng giá trị gốc.

### Dự báo từng giờ ngày mai

Phần trực tiếp trên web so sánh ba phương pháp theo từng trạm: **cùng thứ/cùng giờ**, **cùng nhóm ngày thường hoặc cuối tuần/cùng giờ**, và trung bình cùng giờ 7 ngày. Đây là các mô hình cơ sở có xét lịch, chưa phải mô hình ML thời tiết cho ngày mai. Mục tiêu là số xe sẵn có, không phải nhu cầu thuê xe.

Cùng thứ cần ít nhất hai ngày cùng thứ có giờ đạt chất lượng trong lịch sử; khi thiếu có thể chuyển sang cùng nhóm ngày (ít nhất ba ngày), rồi phương pháp 7 ngày nếu đủ điều kiện. Ngày và giờ phải đạt độ phủ từ 80%; phương pháp 7 ngày vẫn cần đủ bảy ngày hoàn tất và ít nhất năm giờ tương ứng. Không dùng ngày phát hành chưa hoàn tất hoặc ngày mục tiêu làm đầu vào. Phân loại theo sức chứa: ít xe nếu không quá 20%, nhiều xe nếu từ 80% trở lên, còn lại là trung bình.

Các mô hình được so trên cùng trạm/ngày/giờ. Có thêm hai phương pháp kết hợp lịch với mức xe gần đây và một đối chứng giữ nguyên số xe mới nhất. Phần kết hợp dùng số xe mới nhất, độ lệch so với nhịp theo lịch trong ba giờ, thay đổi độ lệch trong một giờ, xu hướng các ngày hoàn tất gần nhất và chênh lệch với cùng ngày tuần trước. Cửa sổ ba giờ cần độ phủ từ 80%; mẫu mới nhất phải hợp lệ và không quá cũ. Điều chỉnh được làm giảm theo số giờ đến mục tiêu, giới hạn trong sức chứa, không kéo dài tuyến tính một xu hướng ngắn ra cả ngày.

Khi có ít nhất sáu ngày lịch sử so sánh chung, chọn phương pháp theo MAE trên ba ngày hoàn tất gần nhất. Kiểm thử cuốn chiếu ở nửa sau khoảng dữ liệu: tại mỗi ngày mục tiêu D, chỉ chọn bằng ba ngày có đáp án trước ngày phát hành D−1; không dùng ngày D−1 đang dở hoặc đáp án D. Đặc trưng gần đây được tái dựng tại đúng giờ phát hành theo New York, chỉ dùng mẫu đã thu tới thời điểm đó. Ngày D−1 được dùng phần đã quan sát để tính mức xe/xu hướng, không dùng cả ngày như thể đã hoàn tất. Khử trùng theo từng thời điểm phát hành để mẫu thu về sau không che mẫu đã có trước đó. Nếu chưa đủ dữ liệu, không công bố điểm kiểm thử giả. Giao diện ghi rõ phương pháp thực tế, dữ liệu gần đây, ngày tham chiếu và sai số so với hai đối chứng. Báo cáo EDA cũ giữ phương pháp tại thời điểm tạo.

Đánh giá cuốn chiếu phiên bản kết hợp ngày 14/11/2026 New York trên 1.976 lượt giờ có MAE 7,787 xe và RMSE 11,137 xe; đối chứng cùng thứ có MAE 8,829 và RMSE 12,448; đối chứng 7 ngày có MAE 8,602 và RMSE 11,657; giữ nguyên mức xe gần nhất có MAE 12,493 xe trên cùng tập. Đây là đánh giá hồi cứu, không phải sai số đã biết của ngày mai. Kết quả theo từng trạm có cả trường hợp kém hơn đối chứng; không ép bật phương pháp kết hợp nếu phương pháp khác tốt hơn trên tập xác thực gần nhất. Giao diện có bảng so sánh sáu ứng viên và ghi độ tin cậy thấp khi mức xe gần đây lệch nhiều hoặc sai số còn lớn. Xem `artifacts/day_ahead_evaluation/recent-rolling-20261114T195024/report.json`.

Lần đánh giá ngày 14/11/2026 New York ghi nhận 2.192 lượt giờ kiểm thử: phương pháp được chọn theo trạm có MAE 8,016 xe, RMSE 11,303 xe; phương pháp 7 ngày có MAE 8,804 xe, RMSE 11,950 xe trên cùng tập. Có 4 trạm chọn cùng thứ, 4 trạm chọn nhóm ngày, 2 trạm giữ phương pháp 7 ngày. Hai trạm có sai số kiểm thử tăng dù tốt hơn trên tập xác thực, nên kết quả không chứng minh cải thiện ở mọi trạm. Bản kết quả: `artifacts/day_ahead_evaluation/20261114T192111Z/report.json`.

Mô hình thời tiết +30 phút không trực tiếp thay thế phần này. Sai số thực tế của ngày mai chỉ tính được sau khi có quan sát tương lai; kiểm thử lịch sử theo từng giờ cần ít nhất 3 ngày đủ điều kiện.

Từ 16/11/2026, Prediction lưu một bản phát hành mỗi ngày New York vào bảng `luot_chay_dich_vu`, với `ten_dich_vu='day_ahead'`. Không cần thêm bảng hoặc migration. `tom_tat.report` lưu nguyên bản dự báo từng trạm/giờ, đầu vào, phương pháp, cutoff và thời điểm phát hành thực tế; `tom_tat.actual_evaluations` lưu kết quả đối chiếu riêng. Chạy lại trong cùng ngày không tính lại hoặc sửa bản đã phát hành. Không tạo lại dự báo cho các ngày quá khứ rồi gọi đó là bản đã phát hành.

API `/api/eda/day-ahead` chỉ đọc bản đã lưu cho hôm nay, không tính, huấn luyện hoặc ghi DB khi mở web. Web tải lại mỗi phút. Nếu hôm nay chưa phát hành được thì báo thiếu, vẫn cho xem kết quả đối chiếu các bản cũ. Bản EDA cũ vẫn riêng biệt. Nếu toàn bộ giờ chưa đủ điều kiện dự báo, worker chưa đóng băng bản rỗng mà thử lại ở lần chạy sau.

Mỗi lần Prediction chạy, sau khi giờ mục tiêu kết thúc và qua thời gian chờ thu thập, worker tính trung bình quan sát thật theo mốc lịch thu, cần ít nhất 80% mẫu hợp lệ. Mẫu mới nhất trong mỗi mốc có ưu tiên; mẫu lỗi không được thay bằng mẫu hợp lệ cũ. Dữ liệu ước lượng không được dùng làm đáp án. Chưa đủ mẫu thì chờ dữ liệu, không gán 0 hoặc điểm sai số giả. MAE/RMSE tính trên số gốc trước làm tròn; phân loại dùng sức chứa tại lúc phát hành. Đã chấm thì giữ nguyên snapshot kết quả cùng các ID quan sát để truy vết.

Giao diện tách **Sai số thực tế của dự báo đã lưu** khỏi **Kiểm thử lịch sử**. Phần thực tế hiển thị số giờ đã đối chiếu, MAE, RMSE, tỷ lệ phân loại đúng, giờ đang chờ và bảng từng giờ trong các bản phát hành bảy ngày gần nhất.

Chạy một lần riêng cho dự báo ngày mai, hoặc bật tiến trình kiểm tra mỗi năm phút mà không tạo thêm dự báo +30 phút:

```bat
.venv\Scripts\python.exe -m prediction.main --day-ahead
.venv\Scripts\python.exe -m prediction.main --day-ahead-schedule
```

Các chế độ `prediction.main --once` và `--schedule`, kể cả script GitHub Prediction khi sử dụng mã mới, đã tích hợp phát hành/chấm điểm ngày mai. Chỉ chọn một nơi chạy lịch để tránh trùng. Tiến trình local dừng khi máy tắt; mã chưa được đẩy lên GitHub không tự xuất hiện trên runner cloud.

Kiểm tra trong DB:

```sql
SELECT ma, thoi_diem_lich, trang_thai,
       JSON_UNQUOTE(JSON_EXTRACT(tom_tat, '$.report.target_date')) AS ngay_du_bao
FROM luot_chay_dich_vu
WHERE ten_dich_vu = 'day_ahead'
ORDER BY ma DESC;
```

Bản phát hành đầu tiên đã xác minh là #4597, phát hành 07:35:06 EST ngày 16/11/2026, mục tiêu 17/11, gồm 240 giờ của 10 trạm. Tại thời điểm lưu, tất cả còn chờ giờ mục tiêu, chưa có sai số thực tế. Bằng chứng API: `artifacts/day_ahead_publication/verification.json`.

## 5. Cài đặt và chạy local trên Windows

Các lệnh sau dành cho **CMD**. Yêu cầu Python từ 3.11, Node.js/npm và cấu hình MySQL hợp lệ.

### Cài đặt lần đầu

```bat
cd /d F:\126\NewYorkBike
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
if not exist .env copy .env.example .env
cd frontend
npm ci
```

Điền DB, chứng chỉ và proxy trong `.env` theo `.env.example`. Không đưa mật khẩu hoặc `.env` lên Git. Giữ `.env.example` làm mẫu cài đặt; hai file cấu hình không sử dụng `.env.development` và `.env.production` đã được xóa.

Bật môi trường bằng `.venv\Scripts\activate.bat`, tắt bằng `deactivate`. Các lệnh dùng trực tiếp Python trong `.venv` bên dưới không cần kích hoạt môi trường.

### Backend

```bat
cd /d F:\126\NewYorkBike
.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload --reload-dir services/database-api --reload-dir shared --log-level error --no-access-log
```

### Frontend — terminal khác

```bat
cd /d F:\126\NewYorkBike\frontend
npm run dev
```

Mở web tại `http://127.0.0.1:5173`, Swagger tại `http://127.0.0.1:8000/docs`. Nhấn `Ctrl+C` tại terminal tương ứng để dừng tiến trình. Lệnh `deactivate` chỉ thoát môi trường Python.

### Chạy từng dịch vụ một lần

```bat
cd /d F:\126\NewYorkBike
.venv\Scripts\python.exe -m ingestion.main --once
.venv\Scripts\python.exe -m analysis.main --once
.venv\Scripts\python.exe -m clustering.main --once
.venv\Scripts\python.exe -m prediction.main --once
```

### Chạy theo lịch — mỗi lệnh ở một terminal riêng

```bat
.venv\Scripts\python.exe -m ingestion.main --schedule --interval-minutes 5
.venv\Scripts\python.exe -m analysis.main --schedule
.venv\Scripts\python.exe -m prediction.main --schedule
.venv\Scripts\python.exe -m clustering.main --schedule
```

Thu thập, phân tích và dự báo chạy ngay rồi theo mốc 5 phút. Phân cụm chạy ngay rồi mỗi ngày lúc 02:00 New York. Collector mặc định có khoảng chạy 30 phút nên cần chỉ rõ `--interval-minutes 5`.

Mỗi dịch vụ chỉ nên có một nơi kích hoạt lịch. Khi chạy GitHub, dừng lịch local tương ứng để tránh trùng. Máy local tắt thì tiến trình local ngừng hoạt động.

Các dịch vụ chỉ xuất thông báo lỗi ra terminal, không tạo file log. Log truy cập API đã tắt. Khởi động lại tiến trình sau khi cập nhật mã để áp dụng; không chuyển stdout/stderr vào file nếu không muốn tạo lại log. Các bảng theo dõi lượt chạy và dữ liệu Bronze vẫn được giữ để truy vết kết quả.

### Huấn luyện và cập nhật báo cáo

```bat
.venv\Scripts\python.exe -m prediction.main --train
.venv\Scripts\python.exe -m prediction.main --once
.venv\Scripts\python.exe -m eda.main --days 28
```

Huấn luyện có thể từ chối nếu chưa đủ dữ liệu hợp lệ. Chạy dự báo không tự huấn luyện lại. EDA tự kiểm tra khi API khởi động và mỗi 15 phút; dữ liệu thay đổi sẽ tạo báo cáo mới trong `artifacts/eda/`. Web tự tải mỗi phút. Tắt bằng `EDA_AUTO_UPDATE=false`; giữ báo cáo cũ nếu tạo mới lỗi. Lệnh EDA thủ công vẫn dùng được.

Đánh giá riêng mô hình thời tiết:

```bat
.venv\Scripts\python.exe -m scripts.evaluate_weather_prediction
```

Xem báo cáo trước khi đăng ký/kích hoạt mô hình thử nghiệm. Chạy đánh giá không đồng nghĩa mô hình đã được kích hoạt hoặc tốt hơn cơ sở.

### Migration và Docker

Sao lưu DB hiện có trước khi nâng cấp; kiểm tra phiên bản trước khi thao tác:

```bat
.venv\Scripts\python.exe -m alembic current
.venv\Scripts\python.exe -m alembic upgrade head
```

Chạy web và API bằng Docker, dùng MySQL/Aiven đã cấu hình:

```bat
docker compose up --build database-api frontend
```

Frontend Docker dùng cổng 8080, API dùng 8000. Compose không tự chạy migration hoặc bật cả bốn worker. Ví dụ chạy phân tích riêng:

```bat
docker compose --profile jobs run --rm data-analysis
```

## 6. Proxy, GitHub và sao lưu Bronze

Ví dụ cấu hình local, thay thông tin mẫu bằng tài khoản proxy:

```dotenv
OUTBOUND_PROXY_ENABLED=true
OUTBOUND_PROXY_URLS=["http://USER:PASSWORD@HOST:PORT"]
```

Mật khẩu có ký tự đặc biệt cần mã hóa URL tương ứng. Khởi động lại collector sau khi đổi `.env`. Không tự chuyển sang gọi trực tiếp khi proxy lỗi.

Trên GitHub, đặt `OUTBOUND_PROXY_URLS` trong Secrets dưới dạng mảng JSON, không kèm tiền tố `OUTBOUND_PROXY_URLS=`. DB và chứng chỉ cũng lấy từ Secrets.

File workflow local `.github/workflows/citibike-ingestion.yml` hiện khai báo cron `0,30 * * * *`, tức 30 phút/lần; điều kiện lịch là `ENABLE_SCHEDULE=true`. Chạy thủ công dùng `workflow_dispatch`. Nếu có bộ lập lịch ngoài kích hoạt 5 phút/lần, phải kiểm tra riêng và tránh bật đồng thời hai lịch. Nội dung file local không xác nhận trạng thái lịch đang triển khai trên GitHub.

Runner GitHub có ổ đĩa tạm. Bronze cần được lưu ra ngoài; workflow cấu hình artifact giữ 7 ngày. Tải các artifact còn tồn tại về `backups/bronze/` bằng CMD:

```bat
cd /d F:\126\NewYorkBike
powershell -ExecutionPolicy Bypass -File scripts\backup_github_bronze.ps1 -Repository bap-05/NewYorkBike
```

Script không cần nhập ID từng lần chạy, bỏ qua ID artifact đã tải hoàn tất. Artifact khác ID vẫn có thể chứa nội dung trùng nhau.

## 7. API và kiểm tra hoạt động

| Đường dẫn | Chức năng |
| --- | --- |
| `/health/live` | Kiểm tra tiến trình API |
| `/health/ready` | Kiểm tra khả năng phục vụ |
| `/api/overview` | Tổng quan |
| `/api/stations` | Danh sách trạm |
| `/api/stations/{station_id}/history` | Lịch sử số xe |
| `/api/stations/{station_id}/predictions` | Dự báo của trạm |
| `/api/analysis` | Kết quả phân tích |
| `/api/clusters` | Các lần phân cụm |
| `/api/eda` | Báo cáo EDA |
| `/api/eda/day-ahead` | Dự báo ngày mai từ DB theo ngày hiện tại |
| `/api/eda/series` | Chuỗi dữ liệu EDA |

Xem tham số chính xác tại Swagger. Trên web, mở F12 → Network → Fetch/XHR, đổi bộ lọc và kiểm tra phản hồi. Ngoài mã HTTP cần xem thời điểm dữ liệu, nguồn và trạng thái chất lượng.

API đọc kết quả đã công bố. Muốn tính lại sau khi nhập dữ liệu, chạy worker tương ứng rồi tải lại web. Thao tác GET không tự tái tạo kết quả đã xóa hoặc huấn luyện mô hình.

## 8. Lỗi thường gặp

| Hiện tượng | Hướng kiểm tra |
| --- | --- |
| `proxy HTTP 407` | Proxy từ chối xác thực; kiểm tra thông tin, hạn dùng và hạn mức tài khoản |
| `OperationalError` | Xem lỗi MySQL chi tiết: kết nối, TLS, migration, khóa hoặc tài nguyên |
| `RuntimeError` khi thu thập | Thông báo chung chưa đủ kết luận; xem lần thu thập, Bronze và lỗi gốc |
| GitHub `Queued` / `No jobs were run` | Job chưa thực thi; kiểm tra Actions, quyền và điều kiện workflow |
| Upload artifact nhận HTML thay JSON | Lỗi bước lưu artifact; kiểm tra riêng bước thu thập để biết DB đã ghi hay chưa |
| `No module named eda` | Dùng Python `.venv`, cài dependencies tại thư mục gốc |
| Biểu đồ ngắt | Khoảng thiếu hoặc mẫu không đạt điều kiện; không tự nối bằng dữ liệu giả |
| EDA còn cũ | Kiểm tra API đang chạy, `EDA_AUTO_UPDATE` và lỗi terminal; lịch nền kiểm tra mỗi 15 phút, web tải mỗi phút |
| Chưa có sai số ngày mai | Chưa có quan sát tương lai hoặc chưa đủ mẫu kiểm thử |

## 9. Kiểm thử và việc cần theo dõi

Lần kiểm tra sau khi dọn mã ghi nhận **323 kiểm thử đạt**. Chạy lại bằng:

```bat
.venv\Scripts\python.exe -B -m pytest -q -p no:cacheprovider
```

Đã gỡ ba file cũ: công cụ tạo ước lượng lịch sử, công cụ dò cấu trúc DB dùng một lần và kiểm thử riêng của công cụ tạo ước lượng. Bản sao nằm trong `artifacts/cleanup/20261114T180623Z/`. Việc xóa cache/build trước đó bị cơ chế duyệt tự động chặn; các thư mục sinh tự động chưa được xóa.

Các việc cần tiếp tục theo dõi:

1. Lịch thực tế của bốn dịch vụ, độ mới dữ liệu và độ phủ; tránh lịch trùng.
2. Proxy hợp lệ và sao lưu Bronze ngoài runner tạm.
3. Huấn luyện khi đủ điều kiện; đánh giá theo trạm và trên dữ liệu tương lai giữ riêng.
4. Giữ nhãn thử nghiệm cho mô hình thời tiết khi chưa chứng minh được hiệu quả tốt hơn cơ sở.
5. Phân biệt dữ liệu thật, nguồn lưu trữ và thời tiết hồi cứu; không dùng mẫu ước lượng làm quan sát thực tế để chấm sai số.

Tài liệu không xác nhận dịch vụ cloud hiện đang chạy hoặc mọi thay đổi local đã được đẩy lên GitHub. Các trạng thái vận hành cần được kiểm tra từ lần chạy thực tế.

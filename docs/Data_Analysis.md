# Data Analysis độc lập cho Citi Bike

Ngày 07/11/2026. Đã viết service và migration, kiểm thử tự động và chạy tính toán
trên dữ liệu thật Aiven ở chế độ chỉ đọc. **Chưa nâng Aiven lên 0004_analysis,
chưa ghi Gold trên Aiven, chưa bật lịch hoặc đẩy mã lên GitHub.**

Lý do chưa nâng Aiven: collector trên GitHub hiện dùng mã cũ yêu cầu đúng revision
0003_bronze. Cần push bản cập nhật kiểm tra minimum revision trước, để việc thêm
bảng Gold không làm collector đang hoạt động từ chối chạy.

## Chức năng đã có

Luồng riêng: MySQL Silver → Analysis → MySQL Gold. Service không gọi Citi Bike,
Open-Meteo, proxy, ingestion, clustering hoặc prediction. API/React về sau đọc
Gold qua `shared.repositories.gold.analysis_results()`; chưa có website/API.

- Thống kê theo trạm, từng giờ và từng ngày America/New_York; lưu ranh giới UTC,
  nhãn địa phương có offset, giờ và thứ trong tuần. Ngày đổi DST có 23/25 giờ;
  hai giờ 01:00 lặp được phân biệt bằng khóa UTC và offset.
- 19 metric mỗi cửa sổ: số xe mean/min/max/độ lệch chuẩn, tỷ lệ hết/ít xe,
  biến động tuyệt đối giữa các mẫu gần nhau, tỷ lệ inactive/stale/không dùng được,
  thiếu mốc/thiếu weather, nhiệt độ/độ ẩm/gió, cường độ mưa, số xe khi mưa/khô,
  tương quan Pearson giữa nhiệt độ và số xe khi đủ mẫu.
- Không gọi biến động số xe là số lượt thuê: số xe còn phụ thuộc trả/điều chuyển.
  Tương quan thời tiết không phải bằng chứng nhân quả, còn bị ảnh hưởng giờ/ngày.
- Mỗi metric lưu số mẫu, số quan sát gốc, số mẫu kỳ vọng, coverage, đơn vị,
  input_cutoff, watermark, calculation_version, configuration_hash và service_run_id.

## Quy tắc dữ liệu

- Chỉ đọc source tương ứng từ lượt ingestion success/partial đã có finished_at,
  đã thu thập/hoàn tất không muộn hơn cutoff. Không đọc lượt đang ghi dở.
- Mẫu số xe dùng cho thống kê phải valid, có số xe, is_installed=true,
  is_renting=true. Inactive/stale vẫn được đếm trong metric chất lượng.
- Mỗi ô thời gian theo nhịp thu thập chọn **quan sát mới nhất**, tránh lượt chạy
  tay làm tăng trọng số. Nếu quan sát mới nhất inactive, không dùng quan sát cũ
  cùng ô để giả định trạm vẫn hoạt động. observed_sample_count vẫn đếm tất cả raw
  Silver rows trong cửa sổ; sample_count là số mẫu thực sự dùng cho metric.
- Coverage = số ô có xe dùng được / số ô kỳ vọng. Không thay khoảng thiếu bằng 0.
  Các ô đã đến lịch nhưng còn trong grace 120 giây chưa bị tính thiếu, trừ khi
  đã có quan sát thực. Không kỳ vọng lịch sử trước ô đầu tiên từng quan sát trạm.
- Thiếu weather không làm mất thống kê số xe. Metric cần weather dùng NULL nếu
  không đủ dữ liệu; missing_weather_ratio ghi rõ mức thiếu.
- Weather phải đúng tọa độ, nguồn, đơn vị, interval, còn mới so với collected_at
  của mẫu xe và đã được biết tại cutoff. Kiểm tra cả lượt đã công bố của weather
  khi có collection_run_id; không lấy weather tương lai hoặc của nguồn khác.
- Trung bình các trường weather chỉ đếm mỗi weather ID một lần trong cửa sổ.
  Mưa đổi từ mm/interval sang mm/h trước khi lấy trung bình; không cộng lượng mưa
  lặp do cache. So sánh số xe khi mưa/khô vẫn theo các mẫu xe có weather hợp lệ.
- Biến động giữa hai mẫu không nối qua inactive hoặc khoảng cách >1,5 nhịp thu
  thập. Nếu không có cặp phù hợp thì NULL, không phải 0.
- `quality_status`: ok, low_coverage hoặc insufficient_data. Giá trị có một mẫu
  có thể tính được nhưng vẫn bị đánh dấu insufficient_data khi min_samples=2.
  Tương quan cần ít nhất 3 cặp và 3 weather ID, có phương sai; nếu không thì NULL.
- Không tạo bất kỳ dự đoán, nhãn cụm hoặc quan sát thay thế nào.

## Cấu hình

Các biến đã có trong .env.example, không chứa secrets:

```dotenv
ANALYSIS_EXPECTED_INTERVAL_SECONDS=1800
ANALYSIS_WINDOW_DAYS=7
ANALYSIS_LOW_BIKE_THRESHOLD=3
ANALYSIS_MIN_SAMPLES=2
ANALYSIS_MIN_COVERAGE=0.8
ANALYSIS_INGESTION_GRACE_SECONDS=120
```

Analysis chạy mỗi 300 giây, nhưng **DATA hiện đến mỗi 1800 giây**. Đây là hai lịch
khác nhau. Không tự thay collector 00/30 trong lần triển khai này. Khi đổi nhịp
thu thập về 300 giây cần thống nhất chính sách độ phủ cho lịch sử có nhiều nhịp;
không áp nhịp mới cho toàn bộ lịch sử rồi coi lịch sử 30 phút là lỗi.

window_days là các ngày lịch New York, tính cả ngày cutoff, không phải số ngày
24 giờ cố định. Cửa sổ hiện tại có thể chưa kết thúc; input_cutoff cho biết phần
dữ liệu đã dùng. Thống kê không mặc định là thống kê của cả giờ/ngày đã kết thúc.

## Chạy trên Windows

PowerShell tại `F:\126\NewYorkBike`. Không cần sửa cấu hình proxy cho Analysis.

### 1. Xem trước ngay, chưa cần migration

```powershell
.\.venv\Scripts\python -m analysis.main --preview
```

Chỉ SELECT Aiven; kết quả JSON nằm ở `artifacts/analysis_preview.json` trên máy.
Không tạo service_runs, không ghi Gold, không gọi API ngoài.

### 2. Push mã trước khi nâng Aiven

Đưa đầy đủ mã mới lên GitHub, đặc biệt `scripts/run_github_collection.py` và
`shared/schema.py`. Collector mới chấp nhận revision 0003 và các nâng cấp cộng
thêm đã biết như 0004, đồng thời kiểm tra đủ cột Silver. Analysis yêu cầu 0004.

```powershell
git add analysis .github/workflows/citibike-analysis.yml database/migrations/versions/0004_analysis.py shared scripts/run_github_collection.py scripts/run_github_analysis.py .env.example README.md tests deploy database/data_layers.json docs/Data_Analysis.md docs/analysis_verification.json docs/Bronze_Silver_Gold.md docs/Yeu_Cau_Web_Seoul_Bike.md Yeu_Cau_Web_Seoul_Bike.md
git diff --cached --name-only
git commit -m "Add independent Citi Bike data analysis and Gold schema"
git push
```

Kiểm tra danh sách trước khi commit: không có .env thật, chứng chỉ, mật khẩu,
dữ liệu Bronze hoặc backup. Các thay đổi chưa stage khác của người dùng vẫn giữ
nguyên. Chờ GitHub có mã mới, thử collector hiện có một lần và xác nhận thành công
trên revision 0003 trước khi nâng database. Không cần bật lịch Analysis lúc này.

### 3. Tạo bảng và chạy Analysis đúng một lần

```powershell
.\.venv\Scripts\python -m alembic upgrade head
.\.venv\Scripts\python -m alembic current
.\.venv\Scripts\python -m analysis.main --once
```

Migration 0004 chỉ CREATE service_runs/analysis_results và index/constraint của
hai bảng mới. Không DROP/TRUNCATE hay ALTER các bảng Silver; không đổi database.
Downgrade phá hủy bị chặn. Chưa áp migration này lên Aiven trong đợt viết mã.

Cùng kỳ 5 phút và cùng cấu hình đã success/skipped thì không ghi lại. Chạy kỳ
sau mà thống kê không thay đổi sẽ lưu service_runs status=skipped, không chèn
bản sao Gold. Đó là trạng thái bình thường khi collector có nhịp 30 phút.

### 4. Kiểm tra kết quả trong MySQL

```sql
SELECT id, service_name, status, scheduled_at, result_count, error_summary
FROM service_runs WHERE service_name='analysis' ORDER BY id DESC LIMIT 10;

SELECT s.name, a.aggregation, a.window_start, a.window_end,
       a.metric_name, a.metric_value, a.sample_count,
       a.expected_sample_count, a.coverage, a.quality_status, a.dimensions
FROM analysis_results a
JOIN stations s ON s.source=a.source AND s.station_id=a.station_id
JOIN service_runs r ON r.source=a.source AND r.id=a.service_run_id
WHERE a.source='citibike' AND r.status='success' AND r.finished_at IS NOT NULL
  AND a.metric_name='available_bikes_mean'
ORDER BY a.window_start DESC, s.name LIMIT 30;
```

window_start/end là UTC; dimensions.local_start chứa nhãn New York có offset.
Nếu thay cấu hình sẽ có configuration_hash khác; API cần chọn cấu hình đang dùng,
không cộng/ghép hai phiên cấu hình vào một bảng thống kê.

### 5. Lịch chạy độc lập, chỉ bật sau khi kiểm tra

Máy cá nhân, terminal riêng:

```powershell
.\.venv\Scripts\python -m analysis.main --schedule
```

Chạy ngay theo cutoff floor 5 phút UTC rồi tại :00/:05/:10/...; không chạy chồng,
bỏ qua mốc đã qua khi tác vụ lâu, Ctrl+C để dừng. Không chạy nền lâu dài tự động.
Service có MySQL advisory lock riêng, không chiếm khóa ingestion. Ubuntu có mẫu
`deploy/citibike-analysis.service`, chưa được cài/bật.

GitHub có workflow **Citi Bike analysis**, tách hoàn toàn khỏi collection, dùng
cùng 6 Secrets Aiven và danh sách 10 trạm, không dùng proxy Secrets. Chạy bằng
Run workflow sau migration; job không tự nâng schema. Lịch GitHub mặc định tắt,
chỉ bật khi Variable ENABLE_ANALYSIS_SCHEDULE=true. Không sửa ENABLE_SCHEDULE
của collector để bật Analysis.

Nếu dùng cron-job.org như collector: tạo **job thứ hai**, POST tới:

```text
https://api.github.com/repos/bap-05/NewYorkBike/actions/workflows/citibike-analysis.yml/dispatches
```

Body `{"ref":"main"}`, các headers GitHub như job collector, token có Actions
write cho repo này. Chọn Every 5 minutes. Giữ ENABLE_ANALYSIS_SCHEDULE=false khi
dùng cron ngoài để tránh hai nơi kích hoạt. Không đưa token vào source hoặc chat.
GitHub vẫn có thể xếp hàng; đây là lịch yêu cầu, không bảo đảm đúng từng phút.

## Lưu trữ và publication

Gold là bảng thống kê materialized theo trạm/giờ/ngày, không nhân bản toàn bộ
report sau mỗi 5 phút. Chỉ upsert những metric thay đổi, giữ các ngày cũ ngoài
lookback, không tự xóa dữ liệu. Các tham số nằm trong configuration và hash;
đổi tham số giữ kết quả riêng. Độ lớn vẫn cần theo dõi trên quota Aiven.

service_runs có marker running được commit trước. Gold và marker success được
commit trong cùng transaction. Lỗi rollback toàn bộ Gold của lần chạy, giữ bản
cũ và ghi failed an toàn; retry không sinh trùng. Mất kết nối có thể khiến marker
running còn lại; lượt sau có khóa hợp lệ đánh dấu marker bị bỏ dở là failed.

Kết quả đã cập nhật trong cùng khóa giờ/ngày sẽ thay phiên trước: đây không phải
lịch sử snapshot Gold để time-travel. Muốn tái dựng một cutoff cũ, chạy lại từ
Silver/Bronze với quy tắc đã biết tại cutoff, không giả định Gold hiện tại là
snapshot bất biến. Dữ liệu/model/forecast chưa có không được tạo giả.

## Bằng chứng và giới hạn

- 153 tests đạt tại lần kiểm tra ban đầu: thống kê, nguồn/cutoff, thiếu weather,
  inactive, khoảng mất, cache mưa, DST, retry, rollback, khóa kỳ/config và scheduler.
- Preview Aiven thực tế: 2.305 quan sát, 10 trạm, 23.370 metric; dữ liệu thay đổi
  khi collector tiếp tục chạy, đây là snapshot kiểm tra không phải tổng cố định.
- Đã sao chép Silver thật vào SQLite in-memory tách biệt để thử publication và
  chống ghi trùng; không chèn fixture vào Aiven. Trung bình ngày 06/11 của cả 10
  trạm khớp truy vấn MySQL độc lập. Xem [analysis_verification.json](analysis_verification.json).
- Migration MySQL được kiểm tra biên dịch; tạo bảng/ghi Gold thực tế trên Aiven
  chưa được chạy vì cần push bản guard tương thích trước. Không tuyên bố đã áp dụng.
- Cú pháp GitHub workflow được kiểm tra riêng. Chưa chạy workflow Analysis thật,
  chưa bật cron Analysis, chưa xây API/React/Clustering/Prediction.

## File thêm hoặc cập nhật trong phần Analysis

| Nhóm | File |
| --- | --- |
| Service | analysis/__init__.py, analysis/config.py, analysis/dataset.py, analysis/statistics.py, analysis/worker.py, analysis/main.py |
| Model/kết nối/đọc dữ liệu | shared/models/__init__.py, shared/database.py, shared/config.py, shared/schema.py, shared/repositories/silver.py, shared/repositories/gold.py |
| Migration/hợp đồng | database/migrations/versions/0004_analysis.py, database/data_layers.json |
| CI/vận hành | scripts/run_github_collection.py, scripts/run_github_analysis.py, .github/workflows/citibike-analysis.yml, deploy/citibike-analysis.service, deploy/package-windows.ps1 |
| Cấu hình/tài liệu | .env.example, README.md, docs/Data_Analysis.md, docs/analysis_verification.json, docs/Bronze_Silver_Gold.md, docs/Yeu_Cau_Web_Seoul_Bike.md, Yeu_Cau_Web_Seoul_Bike.md |
| Tests | tests/test_analysis.py, tests/test_analysis_schedule.py, tests/test_schema_compatibility.py, tests/test_migrations.py |

Các thay đổi backup và báo cáo audit có sẵn trước lượt viết Analysis được giữ
nguyên, không tự commit/push hay đưa bí mật vào repository.

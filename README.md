# Citi Bike New York — database và ingestion

**Tên đề tài:** Dự đoán số xe đạp công cộng có thể thuê tại các trạm Citi Bike ở New York trong 30 phút tới dựa trên thời tiết và thời gian.

Giữ kiến trúc React + FastAPI + MySQL. Ingestion, Analysis, Clustering, Prediction
là các tiến trình riêng: Ingestion chạy ngay khi khởi động rồi tại phút 00/30 theo
giờ New York; Analysis/Prediction dự kiến 5 phút, Clustering hằng ngày.
Hiện chỉ database và ingestion đã được triển khai. Workspace chưa có React, app
FastAPI, Analysis, Clustering, Prediction hoặc huấn luyện; không có kết quả dự đoán giả.

Đã thêm **Bronze** lưu body API gốc và manifest mỗi lần thu thập. Các bảng quan sát
MySQL hiện có là **Silver**. **Gold** mới có hợp đồng đầu ra cho các service xử lý,
chưa có bảng/kết quả tính toán. Chi tiết: [Bronze/Silver/Gold](docs/Bronze_Silver_Gold.md)
và [hợp đồng dữ liệu](database/data_layers.json).

Đặc tả: [docs/Yeu_Cau_Web_Seoul_Bike.md](docs/Yeu_Cau_Web_Seoul_Bike.md).
Tên file cũ được giữ để không hỏng các liên kết. Kết quả chạy thật:
[docs/Kiem_Tra_Citi_Bike.md](docs/Kiem_Tra_Citi_Bike.md).

## Chạy trên Windows

Chạy PowerShell từ thư mục gốc hiện tại. Python 3.11+ (đã kiểm tra bằng 3.13),
MySQL 8.0.16+. Không cần đổi tên thư mục hay database.

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
```

Chỉ khi **chưa có** `.env` mới sao chép:

```powershell
Copy-Item .env.example .env
```

Giữ `.env` hiện có nếu đã điền MySQL/proxy; không commit/in file này.

| Biến | Ý nghĩa |
|---|---|
| MYSQL_HOST, MYSQL_PORT, MYSQL_DATABASE | Database hiện có; mặc định giữ tên cũ `seoul_bike` |
| MYSQL_USER, MYSQL_PASSWORD | Thông tin MySQL của bạn |
| BIKE_SOURCE | `citibike` |
| GBFS_DISCOVERY_URL | `https://gbfs.citibikenyc.com/gbfs/gbfs.json` |
| GBFS_STATUS_MAX_AGE_SECONDS | Mặc định 600, cho status feed và last_reported |
| GBFS_METADATA_MAX_AGE_SECONDS | Mặc định 86400, cho discovery/information |
| STATION_IDS | Các mã chuỗi thật, cách nhau bằng dấu phẩy |
| DISPLAY_TIMEZONE | `America/New_York` |
| OPEN_METEO_URL | `https://api.open-meteo.com/v1/forecast` |
| WEATHER_MAX_AGE_SECONDS | Mặc định 3600; weather quá cũ không được ghép |
| HTTP_TIMEOUT_SECONDS, HTTP_MAX_ATTEMPTS, HTTP_BACKOFF_SECONDS | Timeout/retry/backoff hữu hạn |
| OUTBOUND_PROXY_ENABLED, OUTBOUND_PROXY_URLS | Giữ cơ chế proxy HTTP/HTTPS hiện có; URL là JSON array |
| BRONZE_DIR | Thư mục raw/manifest, mặc định `data/bronze`, tương đối với gốc dự án |

Không còn đọc/yêu cầu SEOUL_API_KEY. `tzdata` hỗ trợ ZoneInfo trên Windows. Biến môi
trường tiến trình ưu tiên hơn `.env`; đường dẫn `.env` luôn theo gốc repository.

## Migration

**Workspace hiện tại đã ở revision 0003_bronze.** MySQL ban đầu có 5 bảng tạo thủ
công, chưa có Alembic và mỗi bảng có 0 dòng. Đã lưu schema/số dòng, kiểm tra layout,
ghi nhận baseline 0001 rồi áp dụng 0002 thành công. Không đổi tên database, không
DROP/TRUNCATE bảng, không xóa dữ liệu.
Migration 0003 chỉ thêm collection_runs.bronze_manifest_path (nullable); các run cũ
không có raw vẫn giữ NULL. Không tạo lại dữ liệu Bronze của quá khứ.

```powershell
.\.venv\Scripts\python -m alembic current
```

Database mới chưa có bảng, hoặc database đã có Alembic:

```powershell
.\.venv\Scripts\python -m alembic upgrade head
```

Database khác có bảng legacy nhưng chưa có Alembic: kiểm tra trước, rồi mới ghi baseline:

```powershell
.\.venv\Scripts\python -m scripts.adopt_legacy_schema
.\.venv\Scripts\python -m scripts.adopt_legacy_schema --stamp
.\.venv\Scripts\python -m alembic upgrade head
```

Không chạy `--stamp` trên database hiện đã có Alembic. Script không tạo lại bảng hay
tự nhận schema giống hệt 0001; migration 0002 hỗ trợ layout 0001 và layout thủ công
đã kiểm tra. Schema khác hoặc bản ghi trùng cần xem xét sẽ báo lỗi, không tự xóa.

0002 cần kết nối MySQL online để phản chiếu schema, không dùng `--sql`. MySQL DDL
không rollback nguyên tử: sao lưu database có dữ liệu trước khi áp dụng; nếu lỗi
giữa chừng, xem schema/revision trước khi chạy lại, không stamp head để che lỗi.
Downgrade 0002 bị chặn vì bỏ nguồn có thể làm trùng định danh.

Giữ các cột/default/index/độ rộng legacy, không ép xóa cột theo autogenerate:

- Station PK `(source, station_id)`; observation có composite FK và UNIQUE
  `(source, station_id, sampled_at)`; run UNIQUE `(source, scheduled_at)`.
- Station/observation cũ có source `seoul`; source run cũ giữ nguyên. Mẫu mới có
  source `citibike`. ORM vẫn đọc được dữ liệu cũ khi lọc source và dùng khóa đủ hai phần.
- Giữ `rack_count`, thêm `capacity` từ GBFS; không coi hai trường là tương đương.
- Đơn vị thời tiết cũ được giữ, không đổi nhãn km/h thành m/s cho số liệu cũ.

## Chọn trạm và thu thập một lần

```powershell
.\.venv\Scripts\python -m ingestion.main --list-stations --limit 5
```

Lệnh đọc discovery và hai feed, không ghi database. Mặc định liệt kê trạm đủ mới,
đang cho thuê/trả trong vùng chọn Manhattan (40.70–40.80, -74.015–-73.95), không phải
toàn bộ địa giới New York. Sao chép `station_id` thật vào STATION_IDS, giữ nguyên
chuỗi, ngăn cách bằng dấu phẩy. Có thể chọn mã khác từ feed bằng cấu hình.

Workspace đã được cấu hình 5 trạm được kiểm tra trong báo cáo. Chạy một lần:

```powershell
.\.venv\Scripts\python -m ingestion.main --once
```

Mã thoát 0 khi success, 1 khi partial/failed hoặc lỗi cấu hình. Không có tùy chọn
thì CLI chỉ hiện hướng dẫn. Đợt chuyển nguồn đã chạy đúng một lần thật; không bật lịch.

Kiểm tra bằng MySQL Workbench:

```sql
SELECT id, source, scheduled_at, status, success_count, error_count, attempt_count, bronze_manifest_path
FROM collection_runs ORDER BY id DESC LIMIT 10;

SELECT s.source, s.station_id, s.name, s.capacity,
       b.available_bikes, b.available_docks, b.is_renting, b.is_returning,
       b.quality_status, b.source_observed_at, b.collected_at,
       w.requested_latitude, w.requested_longitude, w.weather_time, w.units
FROM bike_observations b
JOIN stations s ON s.source=b.source AND s.station_id=b.station_id
JOIN collection_runs r ON r.id=b.collection_run_id
LEFT JOIN observation_weather_links l ON l.bike_observation_id=b.id
LEFT JOIN weather_observations w ON w.id=l.weather_observation_id
WHERE b.source='citibike' AND r.finished_at IS NOT NULL
ORDER BY b.collected_at DESC LIMIT 20;
```

## Quy tắc dữ liệu

- URL feed con lấy từ discovery ở mỗi lần fetch; xác nhận version giữa ba feed.
  Hỗ trợ 1.1, 2.0–2.3, 3.0; unknown version bị từ chối. Thực tế đã kiểm tra **1.1**;
  2.x/3.0 chỉ kiểm thử bằng fixture. Metadata version, URL và thời điểm cả hai feed
  nằm trong collection_runs.feed_metadata.
- Ghép station_id dạng chuỗi, không theo thứ tự dòng. Metadata/capacity từ
  station_information; xe/chỗ trả/trạng thái/last_reported từ station_status.
- 1.1/2.x dùng Unix seconds; 3.0 dùng RFC3339 có offset và num_vehicles_available.
  Thiếu status thì giữ count NULL/quality missing; thiếu metadata không tạo tọa độ giả.
- Quality: valid/missing/invalid/inactive/stale. Trạm không lắp đặt hoặc ngừng cho
  thuê là inactive dù count dương; is_returning lưu riêng. Kiểm tra độ mới cả feed
  lẫn last_reported; dữ liệu xe cho phép tối đa 60 giây lệch đồng hồ về tương lai.
- sampled_at là mốc chạy: lần đầu dùng thời điểm khởi động thực tế (đến giây), các
  lần định kỳ dùng mốc :00/:30. source_observed_at từ last_reported, feed_last_updated từ
  envelope, collected_at từ thời điểm nhận status. Không lấy giờ chạy làm giờ nguồn.
- Open-Meteo gọi theo tọa độ từng trạm, giữ cả tọa độ yêu cầu và ô lưới trả về;
  lưu °C, %, mm, m/s, units, interval_seconds, weather_time, collected_at. Có thể dùng
  lại weather đầy đủ, cùng tọa độ, tuổi tối đa 15 phút và trong giới hạn cấu hình,
  đã được thu thập tại thời điểm xe. Không dùng tâm bản đồ cho mọi trạm.
- Weather quá cũ hoặc ở tương lai so với quan sát xe không được ghép. Missing/NaN/
  invalid giữ NULL, không điền 0. Lỗi weather giữ xe và ghi partial khi có mẫu valid.
  UNIQUE vị trí/thời gian/nguồn tái sử dụng weather, không cộng lặp mưa.
- Run running được ghi trước; dữ liệu và trạng thái kết thúc commit cùng transaction.
  Lỗi bất ngờ rollback phần ghi dở. Service sau này chỉ đọc run kết thúc và quality
  phù hợp. success_count là số mẫu valid, error_count là số vấn đề lần thử gần nhất.
- Mọi response trong kỳ được lưu Bronze trước khi parse/chuẩn hóa; nếu Bronze ghi
  lỗi thì rollback ghi Silver của lần thử. Manifest có hash/kích thước body, thời gian
  UTC, run/lần thử, metadata nguồn và tham chiếu weather dùng lại. Raw vẫn giữ khi
  Silver rollback. Trạng thái MySQL là bằng chứng commit, không chỉ trạng thái manifest.
- Run success trùng source và timestamp đến giây được bỏ qua; retry giữ quan sát đã
  ghi và bổ sung phần thiếu. Khởi động lại ở giây khác tạo lần lấy ngay mới, không
  gom vào mốc nửa giờ trước đó. Không tạo realtime backfill cho kỳ bỏ lỡ.
- MySQL GET_LOCK chặn chạy chồng; tên khóa legacy được giữ để tương thích tiến trình
  cũ dùng cùng database. Foreign key RESTRICT bảo vệ lịch sử.

## Thời gian, giao diện và lịch

Lưu UTC, MySQL session +00:00; ORM trả aware UTC và từ chối datetime không có timezone.
`display_time` dùng ZoneInfo America/New_York, trả offset để phân biệt giờ lặp DST.
Tests kiểm tra cả DST mùa xuân/mùa thu; không dùng UTC-4/UTC-5 cố định.
Log collector và sample_time hiển thị giờ New York kèm offset và tên múi giờ,
không phụ thuộc giờ Việt Nam/Thái Lan của Windows. --list-stations giữ timestamp UTC
để máy đọc và bổ sung source_observed_at_local theo America/New_York cho người xem.
Timestamp trong MySQL/Bronze vẫn UTC; không đổi số giờ nguồn hoặc ghi đè dữ liệu cũ.

`shared/presentation.py` chứa tên mới và tâm bản đồ New York (40.7128, -74.0060) cho
API/React sau này. Hiện chưa có bản đồ chạy. React về sau dùng Intl.DateTimeFormat
với timeZone America/New_York.

Giữ proxy theo từng request/retry A → B → C → A, mở kết nối proxy mới, không fallback
trực tiếp khi proxy được bật. Không log URL/tài khoản/mật khẩu proxy. Feed Citi Bike
là công khai; không cần proxy để xác thực.

Sau khi xác minh và **chỉ khi bạn chủ động muốn bật lịch**, dùng:

```powershell
.\.venv\Scripts\python -m ingestion.main --schedule
```

Chạy ingestion riêng: lấy ngay một lần, sau đó vào phút **00 và 30 theo America/New_York**.
Ví dụ mở lúc 08:47:12 thì các lần ghi là 08:47:12 → 09:00 → 09:30 → 10:00.
Không phải chờ 30 phút sau mỗi lần (08:47 → 09:17). Ctrl+C để dừng; cần giữ terminal mở.
Nếu lần trước chưa xong khi đi qua một mốc, bỏ qua mốc đó để không chạy chồng; không
bù dữ liệu realtime cho thời gian đã qua. DST dùng UTC làm định danh nên hai giờ địa
phương lặp vẫn có timestamp/offset khác nhau.
Chưa tự bật lịch nền. Analysis/Prediction và Clustering vẫn chưa
được triển khai; lịch Clustering theo ngày New York cần xử lý một lần/ngày khi DST đổi.
Thay đổi chu kỳ ingestion không đổi mục tiêu dự đoán +30 phút hoặc lịch Analysis/Prediction.

Ngày 02/11/2026 đã kiểm tra và nâng schema của database đang cấu hình `newyorkbike`
từ layout legacy lên 0003_bronze; cả 5 bảng nghiệp vụ vẫn trống. Không đổi tên database,
không xóa dữ liệu và chưa chạy collector thật trên database mới trong lần sửa lịch này.

## Kiểm thử

```powershell
.\.venv\Scripts\python -m pytest -q
.\.venv\Scripts\python -m pip check
```

Tests dùng fixture riêng, SQLite in-memory, MockTransport và proxy localhost; không
seed MySQL và không gọi API thật. Kết quả thực tế MySQL/feed được ghi riêng trong
[báo cáo](docs/Kiem_Tra_Citi_Bike.md). Không tự chạy đề xuất xóa cột từ alembic check
để ép schema thủ công khớp model; các khác biệt legacy được giữ có chủ đích.

Kiểm tra một manifest thật bằng `python -m scripts.inspect_bronze <đường_dẫn_manifest>`.
Lệnh chỉ đọc file, không gọi API/ghi MySQL. Chi tiết lưu trữ, giới hạn và lệnh Windows
nằm trong [tài liệu phân tầng](docs/Bronze_Silver_Gold.md).
Lần kiểm tra bổ sung Bronze đã có 8 body thật được xác minh SHA-256, run 2 thành công,
91 tests đạt. Xem [bằng chứng Bronze](docs/bronze_verification.json); báo cáo chuyển
nguồn Citi Bike phía trên là kết quả lịch sử của run 1 trước khi có Bronze.

## Chạy trên server miễn phí khi tắt máy cá nhân

Danh sách `STATION_IDS` trong cấu hình cục bộ hiện có **10 trạm**: giữ 5 trạm ban
đầu và bổ sung 5 trạm. Đã kiểm tra feed thật qua proxy: đủ 10 trạm đang lắp đặt,
cho thuê và nhận trả xe, dữ liệu còn mới. Xem [danh sách đã kiểm tra](docs/citibike_station_selection.json).
Lần đổi cấu hình này chưa ghi dữ liệu MySQL hoặc bật lịch nền. Nếu collector đang
chạy, cần dừng bằng Ctrl+C rồi chạy lại để nạp danh sách mới; không thay đổi lịch
chạy ngay khi khởi động và sau đó tại phút 00/30 theo New York.

Không có thẻ: bắt đầu bằng [kết nối MySQL Aiven từ Windows](docs/Ket_Noi_Aiven_Windows.md).
Đã hỗ trợ CA/hostname verification qua `MYSQL_SSL_CA` và lệnh
`python -m scripts.check_database` không ghi dữ liệu. Ngày 02/11/2026 đã nâng schema
Aiven lên 0003_bronze và thu thập thật đúng một lần qua proxy: 5 trạm, 5 quan sát xe,
5 quan sát thời tiết, 5 liên kết; xem [bằng chứng Aiven](docs/aiven_verification.json).
Lần kiểm tra đó có 110 tests đạt; đây là bằng chứng lịch sử, không phải lần chạy
GitHub. Hiện đã chuẩn bị [workflow GitHub Actions + lưu Bronze artifact](docs/Deploy_GitHub_Actions_Aiven.md)
và cấu hình 10 trạm trong `config/citibike_stations.json`. Chưa push hoặc chạy
trên GitHub; schedule chờ Variable `ENABLE_SCHEDULE=true` sau khi thử thủ công.
Artifact giữ 7 ngày, cần sao lưu đều bằng `scripts/backup_github_bronze.ps1` hoặc
chọn kho lưu trữ khác trước khi bật lâu dài. Không có lưu trữ miễn phí vô hạn.

Xem [hướng dẫn Oracle Always Free từ Windows](docs/Deploy_Mien_Phi_Oracle.md):
tạo VM Ubuntu, cài MySQL, chuyển mã không kèm bí mật, chạy thử một lần rồi bật
`deploy/citibike-ingestion.service`. Oracle cần thẻ xác minh và tài nguyên đủ điều
kiện miễn phí; có thể hết suất hoặc thu hồi VM nhàn rỗi. Chưa deploy hay kiểm tra
trên cloud. Script `deploy/package-windows.ps1` đã được chạy để kiểm tra đóng gói;
archive không chứa `.env`, virtualenv, dữ liệu Bronze/MySQL hoặc SSH key.

## Nguồn

- [Citi Bike discovery](https://gbfs.citibikenyc.com/gbfs/gbfs.json)
- [GBFS 1.1](https://github.com/MobilityData/gbfs/blob/v1.1/gbfs.md)
- [GBFS 3.0](https://gbfs.org/documentation/reference/)
- [Open-Meteo](https://open-meteo.com/en/docs)
- [HTTPX proxy](https://www.python-httpx.org/advanced/proxies/)

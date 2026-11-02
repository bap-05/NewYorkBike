# Kiểm chứng chuyển nguồn Citi Bike New York

Ngày làm việc: **01/11/2026, Asia/Bangkok**. Thời điểm UTC của các request và kỳ chạy
nằm trong [citibike_verification.json](citibike_verification.json), có thể thuộc ngày
31/10/2026 vì lệch múi giờ. Tất cả số liệu dưới đây là kết quả thực tế tại lúc kiểm tra.

## Trạng thái mã nguồn

Đã đọc đặc tả và kiểm tra các module shared, ingestion, migration, cấu hình, proxy,
tests và README. Không có AGENTS.md hoặc bộ mã React/FastAPI/Analysis/Clustering/
Prediction trong workspace tại thời điểm kiểm tra. Không tạo các tính năng rỗng rồi
nhận là đã chạy; giữ chúng trong kiến trúc/yêu cầu cho bước sau.

## Nguồn thật

- Discovery: https://gbfs.citibikenyc.com/gbfs/gbfs.json, HTTP 200.
- Đọc discovery để tìm hai URL con, không hardcode trong client.
- Hai feed đều HTTP 200, GBFS **1.1**, mỗi feed 2.518 station_id tại lúc kiểm tra.
- Metadata thực tế có station_id/name/lat/lon/capacity; status có num_bikes_available,
  num_docks_available, is_installed/is_renting/is_returning và last_reported số nguyên
  Unix seconds. last_updated của envelope cũng là Unix seconds, ttl=60.
- Có trạm ngừng cho thuê và last_reported cũ trong feed, nên chỉ chọn trạm valid,
  đang cho thuê/trả và có tọa độ trong Manhattan cho cấu hình ban đầu.
- Giữ proxy đang hoạt động; toàn bộ request kiểm tra và collector dùng cấu hình này.
- 5 request Open-Meteo trong lần thu thập đều HTTP 200, tọa độ khác nhau theo trạm.

## Năm trạm đã chọn

Định danh lấy từ feed thật, đã điền vào STATION_IDS của `.env` hiện có. Không sao
chép tài khoản MySQL hay tài khoản/mật khẩu proxy vào tài liệu.

| Trạm | station_id | Vĩ độ | Kinh độ | capacity |
|---|---|---:|---:|---:|
| E 5 St & Ave A | 0096fecb-3a56-4585-9204-aa9554f7bc49 | 40.724790 | -73.984301 | 48 |
| Perry St & Greenwich Ave | 00d3e65e-b614-4408-aaa9-939ed96ce645 | 40.735918 | -74.000939 | 53 |
| E 54 St & 1 Ave | 0138452a-b9f4-4aee-80b0-7fae9a122ffe | 40.756265 | -73.964179 | 61 |
| Peck Slip & South St | 014a931b-8e1c-438a-8a22-f267ddd1e0d2 | 40.707519 | -74.001081 | 45 |
| 8 Ave & W 49 St | 053312f2-e77e-4674-b28b-ad357fbcb4ee | 40.761712 | -73.986551 | 65 |

Trạng thái/capacity có thể thay đổi sau lần kiểm tra; collector luôn lấy lại feed.
Không dùng số xe từ báo cáo làm dữ liệu hiện tại trên giao diện.

## MySQL và migration

- Kết nối thật thành công; MySQL **8.0.46**. Không đổi tên database hiện có.
- Ban đầu có đúng 5 bảng nghiệp vụ, mỗi bảng **0 dòng**, chưa có alembic_version.
  Schema thủ công khác 0001: BIGINT, ENUM, một số cột riêng về đơn vị, thiếu JSON
  units/attempt_count và có thêm created_at. Snapshot chỉ cấu trúc/số dòng:
  [mysql_schema_before_citibike.json](mysql_schema_before_citibike.json).
- Đã kiểm tra schema và ghi nhận baseline bằng scripts.adopt_legacy_schema --stamp,
  sau đó chạy Alembic upgrade head thành công. Revision hiện tại **0002_citibike**.
- Giữ các cột và dữ liệu legacy. Không DROP/TRUNCATE bảng, không xóa dữ liệu và
  không gán capacity từ rack_count. Không đổi đơn vị của số liệu weather cũ.
- PK stations là (source, station_id), FK observation theo cùng hai cột, UNIQUE
  observations theo (source, station_id, sampled_at), run theo (source, scheduled_at).
- UNIQUE weather nguồn/vị trí/thời gian đã tồn tại sau migration; index legacy có
  interval vẫn giữ. Chưa tự chuẩn hóa/xóa các type/index/cột khác do người dùng tạo.
- Kiểm tra GET_LOCK bằng hai connection thật: connection thứ nhất lấy được khóa,
  connection thứ hai bị chặn; đã nhả khóa sau kiểm tra.

## Lần thu thập thật duy nhất

Đã chạy **một lần** `python -m ingestion.main --once`, không chạy --schedule.

| Thuộc tính | Kết quả |
|---|---|
| Run ID | 1 |
| Source | citibike |
| Kỳ UTC | 2026-10-31T18:10:00+00:00 |
| Kỳ hiển thị New York | 2026-10-31T14:10:00-04:00 |
| Status | success |
| success_count / error_count / attempt_count | 5 / 0 / 1 |
| stations | 5 |
| collection_runs | 1 |
| bike_observations | 5 |
| weather_observations | 5 |
| observation_weather_links | 5 |

- Cả 5 quan sát có nguồn citibike, station_id khớp metadata và trạng thái valid.
- Tọa độ yêu cầu weather khớp tọa độ trạm cho cả 5 liên kết; không dùng một tâm chung.
- Thời điểm nguồn xe và thời điểm weather không nằm sau collected_at của xe trong
  5 bản ghi đã ghi. UTC nguồn và collected_at được lưu riêng.
- Truy vấn GROUP BY source/station_id/sampled_at không có nhóm trùng.
- Chống ghi trùng khi retry được kiểm tra trong unit tests; **không chạy collector
  thật lần thứ hai** chỉ để thử retry. UNIQUE trên MySQL được kiểm tra bằng introspection.
- Không có dự đoán, mô hình, kết quả phân tích hoặc phân cụm được tạo.

## Kiểm thử tự động và giới hạn

**68 tests passed**; pip check không phát hiện dependency lỗi. Tests dùng fixture riêng
và SQLite in-memory hoặc proxy localhost, không ghi dữ liệu thử vào MySQL hiện tại.
Bao phủ discovery URL động, ghép chuỗi ID, GBFS 1.1/2.x/3.0, timestamp theo version,
inactive/stale/missing, metadata/status không khớp, dữ liệu thiếu khác 0, tọa độ từng
trạm, weather reuse, UTC, DST xuân/thu, rollback, retry, source isolation và proxy.

Chưa kiểm tra chạy liên tục nhiều kỳ, khởi động lại qua DST, hạn mức/độ ổn định dài
hạn hoặc deployment. 2.x/3.0 chỉ thử bằng fixture, feed thật đang là 1.1. Chưa có
dữ liệu Seoul lịch sử không rỗng để xác minh chuyển đổi đầu cuối trên dữ liệu cũ;
đã kiểm tra cô lập nguồn và giữ rack_count bằng tests riêng.

Chưa triển khai React/FastAPI/Analysis/Clustering/Prediction/ML. Tên mới, múi giờ và
tâm bản đồ cho giao diện tương lai nằm trong shared/presentation.py và đặc tả.
Không có cấu hình bắt buộc còn thiếu để chạy collector hiện tại. Open-Meteo/Citi Bike
đều không yêu cầu API key ở các endpoint công khai đang dùng.

## File đã thay đổi hoặc bổ sung

- `ingestion/clients/seoul_client.py` → `ingestion/clients/citibike_client.py`.
- `ingestion/main.py`, `ingestion/collector.py`, `ingestion/normalizer.py`.
- `shared/config.py`, `shared/models/__init__.py`, `shared/time.py`, `shared/presentation.py`.
- `database/migrations/versions/0002_citibike.py` (giữ revision 0001 nguyên vẹn).
- `scripts/__init__.py`, `scripts/adopt_legacy_schema.py`.
- `.env.example`, `.env` riêng (chỉ cấu hình nguồn/múi giờ/mã trạm; giữ thông tin MySQL/proxy).
- `requirements.txt` (thêm tzdata cho Windows).
- `tests/conftest.py`, `tests/test_clients.py`, `tests/test_collector.py`,
  `tests/test_migrations.py`, `tests/test_gbfs.py`.
- `README.md`, `docs/Yeu_Cau_Web_Seoul_Bike.md`, `Yeu_Cau_Web_Seoul_Bike.md`.
- `docs/mysql_schema_before_citibike.json`, `docs/citibike_verification.json`, tài liệu này.

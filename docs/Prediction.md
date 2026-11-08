# Prediction — dự đoán số xe có thể thuê sau 30 phút

Service Python độc lập, đọc Silver và model trên MySQL. Không gọi GBFS/Open-Meteo,
không dùng proxy, không chạy collector/Analysis/Clustering bên trong. Huấn luyện
là lệnh riêng; vòng Prediction 5 phút **không huấn luyện lại mô hình**.

## Chạy trên Windows

Tại `F:\126\NewYorkBike`, giữ nguyên `.env` MySQL/CA hiện có:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-prediction.txt
.\.venv\Scripts\python.exe -m prediction.main --preview
```

Xem `artifacts\prediction_preview.json`. Preview dùng MySQL READ ONLY, không ghi
DB, không kích hoạt model, không phát hành dự đoán quá khứ. Đọc được Silver trước
khi nâng migration 0006. Báo cáo có dự đoán xem trước và đánh giá baseline lịch sử;
nếu đủ điều kiện cũng thử ML trong bộ nhớ nhưng không lưu/kích hoạt.

**Push mã mới trước khi nâng schema**: các service GitHub phải có file migration
0006 để guard nhận diện revision mới. Sau khi mã mới đã lên nhánh mặc định:

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic current
.\.venv\Scripts\python.exe -m prediction.main --once
```

Migration `0006_prediction` chỉ thêm **model_versions**, **training_jobs** và
**predictions** trong database hiện có. Không đổi/xóa bảng hay dữ liệu cũ.
Lệnh `--once` ghi một kỳ Prediction và đối chiếu các dự đoán trước đã đến hạn.

Chạy lịch trên máy, terminal riêng:

```powershell
.\.venv\Scripts\python.exe -m prediction.main --schedule
```

Chạy ngay, sau đó các mốc 5 phút UTC (hiển thị New York, đúng DST), bỏ mốc đã qua
nếu xử lý lâu, không bịa dự đoán đã phát hành trong quá khứ. Ctrl+C dừng; tắt máy
là dừng lịch local. Không chạy song song lịch local với lịch cloud cùng service.

## Mốc thời gian và độ mới

- `input_time = bike_observations.sampled_at`: mốc kỳ dữ liệu t thực sự được lưu.
- `target_at = input_time + 1.800 giây` trong UTC; không cộng theo số dòng hoặc
  giờ địa phương khi qua DST. `source_observed_at` được lưu trong features để biết
  độ trễ báo cáo của nguồn; không giả định nó bằng thời gian thu thập.
- `input_cutoff_at`: thời điểm worker chốt dữ liệu được phép đọc. Chỉ collection
  success/partial đã hoàn tất và quan sát đã được thu trước cutoff mới được dùng.
- `issued_at`: thời điểm tạo kết quả, luôn trước target đối với baseline/ML.
  Dự đoán mang nghĩa **+30 phút từ mốc dữ liệu**, không hứa còn đủ 30 phút từ lúc
  bạn nhìn màn hình. Ví dụ mẫu 09:00, chạy 09:07 vẫn dự đoán cho 09:30.
- Mẫu phải valid, installed và renting đều true, số xe không NULL. Chọn mẫu mới
  nhất kể cả inactive, không lùi về mẫu valid cũ để che trạm tạm ngừng.
- Giới hạn độ mới mặc định **600 giây**, xét cả sampled_at và source_observed_at.
  Mẫu cũ/mất/invalid/inactive ghi status unavailable, predicted_bikes=NULL cùng
  reason; không thay bằng 0. Không dùng rack_count làm capacity.

**Collector vẫn thu 30 phút/lần theo yêu cầu trước.** Prediction kiểm tra 5 phút
không tạo thêm quan sát mới. Các kỳ cách mẫu gần nhất quá 10 phút sẽ unavailable.
Không nới ngưỡng để trình bày dữ liệu cũ như mới. Muốn có đầu vào mới đều mỗi 5
phút thì phải đổi lịch collector sau một quyết định riêng.

## Baseline, ML và lưu phiên bản

Baseline **Persistence**: số xe dự đoán bằng số xe hiện tại, gắn status `baseline`
và model phiên bản riêng. Đây là mô hình đối chứng, chưa sử dụng thời tiết để điều
chỉnh số xe. Không gọi baseline là kết quả ML đã huấn luyện.

Khi có model ML đủ điều kiện và đang active, service dùng `random_forest`; nếu
thiếu lag/thời tiết cần thiết, trạm chưa từng huấn luyện hoặc model lỗi, dùng
baseline với reason rõ. Model không tương thích chính sách hoặc được tạo sau
cutoff sẽ không được dùng. Prediction v1 không phụ thuộc nhóm Clustering.

- `model_versions`: baseline hoặc RF, ngày tạo, cửa sổ train, chính sách đặc trưng,
  MAE/RMSE theo trạm, payload cây JSON và cờ active. Không dùng pickle hoặc file
  trên runner tạm. Bản model cũ được giữ lại để tra cứu; active chỉ chọn model ML.
- `training_jobs`: từng tác vụ train, trạng thái running/success/insufficient_data/
  baseline_preferred/failed, tham số, báo cáo và model tạo ra nếu có.
- `predictions`: input/cutoff/issued/target UTC, quan sát đầu vào, model_id,
  raw_predicted_bikes và predicted_bikes, status/reason, provenance đặc trưng,
  cùng quan sát thực tế/sai số khi đối chiếu được.
- Raw output được giữ nguyên để đánh giá. Số phục vụ giao diện chặn về >=0 và
  capacity hiện tại nếu có; chưa làm tròn, UI sẽ định dạng số nguyên sau này.
  Không dùng capacity hiện tại làm đặc trưng cho huấn luyện lịch sử.
- `service_runs`: service_name=prediction; khóa riêng và unique kỳ 5 phút/
  version/config. Chạy lại cùng kỳ không nhân đôi; dự đoán cùng marker hoàn tất
  commit một transaction. Lỗi rollback không để lộ kết quả công bố dở.
- Các kỳ 5 phút có thể cùng tham chiếu một quan sát/mốc đích; đó là các lần kiểm
  tra riêng, không phải dữ liệu xe mới. Trạm không có metadata được nêu trong
  summary, không tự tạo metadata hoặc hàng dự đoán cho trạm không tồn tại.

## Chuẩn bị nhãn và huấn luyện riêng

```powershell
.\.venv\Scripts\python.exe -m prediction.main --train
```

Lệnh dùng khóa `training` và sổ `training_jobs`, không nằm trong scheduler. Mặc
định cần ít nhất 14 ngày lịch NY có mẫu đầy đủ đặc trưng, 1.000 mẫu, 100 mẫu cho
mỗi trạm theo dõi, mỗi phần train/validation/test ít nhất 50 mẫu. Chưa đủ chỉ ghi
`insufficient_data`; không tạo model giả. Ngưỡng không bảo đảm mọi thời tiết đã
được đại diện. Có thể tiếp tục thu thập 2–4 tuần để đánh giá đáng tin hơn.

Pipeline:

1. Tìm đáp án tại t+30 phút theo timestamp thật; dung sai mặc định ±120 giây,
   lưu timestamp thực tế và độ lệch. Không lấy dòng kế tiếp khi mất nửa giờ.
   Mẫu đích phải valid, active, có báo cáo nguồn mới hơn đầu vào và được công bố.
2. Đặc trưng: station_id one-hot, số xe hiện tại, lag30 và thay đổi30, sin/cos giờ
   và thứ New York, cuối tuần; thêm nhiệt độ/ẩm/mưa/gió trong biến thể thời tiết.
   Nhịp dữ liệu 30 phút chưa có lag5/10/15 thật nên không dựng chúng.
3. Feature cutoff lịch sử là thời điểm collection đầu vào hoàn tất. Chỉ lấy lag
   đã có trước cutoff và thời tiết liên kết đã công bố, đúng trạm, đúng đơn vị
   (°C, %, mm, m/s), còn mới. Không dùng thời tiết thực tế tương lai hoặc điền 0.
   Giá trị 0 thật (hết xe, không mưa) được giữ nguyên.
4. Train/validation/test theo các mốc input_time 70/15/15, không random split.
   Purge mẫu train có nhãn còn chưa được công bố trước validation_start; tương
   tự validation trước test_start. Giữ cùng mốc input_time trong cùng phần.
5. So baseline với RF depth4/depth8, có/không thời tiết trên cùng cohort đầy đủ
   đặc trưng để so sánh công bằng. Chọn duy nhất theo validation MAE; phải thấp
   hơn persistence. Không cải thiện thì baseline_preferred, không tự đổi model cũ.
6. Tập test chỉ đánh giá sau chọn. Báo MAE/RMSE đơn vị xe, số mẫu và từng trạm.
   Sau báo cáo, refit cấu hình đã chọn trên toàn bộ cohort để phục vụ tương lai;
   test score lưu rõ thuộc model train-only, không phải điểm của bản refit.
7. Lưu payload JSON, tham số, phiên bản thư viện, hash tập dữ liệu, khoảng train.
   Kích hoạt model cùng transaction với training job thành công. Khi job lỗi/
   thiếu dữ liệu hoặc baseline được ưu tiên, giữ model active trước đó nếu có.

Tài liệu thuật toán: [RandomForestRegressor](https://scikit-learn.org/1.7/modules/generated/sklearn.ensemble.RandomForestRegressor.html),
[chia dữ liệu theo thời gian](https://scikit-learn.org/1.7/modules/cross_validation.html#time-series-split).

## Đối chiếu dự đoán đã đến hạn

Mỗi lần `--once`/scheduler sẽ xét dự đoán baseline/ML đã công bố, đã qua target
cộng dung sai, trong khoảng history_days. Chọn quan sát thực tế gần target trong
dung sai đã lưu ở cấu hình của lần phát hành. Inactive/missing không được tính
thành xe=0. Không tìm thấy thì actual/sai số còn NULL, không bịa đáp án.

Lưu absolute_error và squared_error theo raw, served_absolute_error theo đầu ra
đã chặn. Phần forecast đã phát hành không được viết lại sau khi biết đáp án.

```sql
SELECT p.id, s.name, p.status, p.reason, p.input_time, p.issued_at,
       p.target_at, p.predicted_bikes, p.model_version_id,
       p.actual_bikes, p.actual_time, p.target_offset_seconds, p.absolute_error
FROM predictions p
JOIN stations s ON s.source=p.source AND s.station_id=p.station_id
JOIN service_runs r ON r.source=p.source AND r.id=p.service_run_id
WHERE p.source='citibike' AND r.service_name='prediction' AND r.status='success'
  AND r.finished_at IS NOT NULL
ORDER BY p.id DESC LIMIT 30;

SELECT p.status, p.model_version_id, COUNT(*) AS matched_samples,
       AVG(p.absolute_error) AS mae_raw, SQRT(AVG(p.squared_error)) AS rmse_raw,
       AVG(p.served_absolute_error) AS mae_served
FROM predictions p
JOIN service_runs r ON r.source=p.source AND r.id=p.service_run_id
WHERE p.source='citibike' AND r.service_name='prediction' AND r.status='success'
  AND r.finished_at IS NOT NULL AND p.evaluated_at IS NOT NULL
GROUP BY p.status,p.model_version_id;
```

MySQL hiển thị các cột thời gian theo UTC; giờ NY dùng lớp hiển thị sau này.
Repository `shared.repositories.gold.predictions` chỉ công bố run success đã xong.
Khi đọc as-of, truyền available_at để loại dự đoán chưa được phát hành tại cutoff.

## GitHub và cron-job.org

Workflow riêng `Citi Bike prediction`, dùng lại Secrets Aiven hiện có, chỉ cài
requirements.txt để suy luận JSON, không cài sklearn/huấn luyện trên mỗi lần chạy.
Chạy thủ công một lần trước. Lịch tự động được chuẩn bị nhưng **chưa tự bật**.

- Chọn GitHub: Repository variable `ENABLE_PREDICTION_SCHEDULE=true`; cron
  phút 02/07/12/17/... mỗi giờ UTC (cách 5 phút, tránh dồn vào phút 00).
- Hoặc chọn cron-job.org giống Analysis, POST mỗi 5 phút đến
  `https://api.github.com/repos/bap-05/NewYorkBike/actions/workflows/citibike-prediction.yml/dispatches`,
  headers Authorization Bearer token riêng, Accept `application/vnd.github+json`,
  Content-Type `application/json`, body `{"ref":"main"}`; để biến GitHub trên tắt.
- Chọn một lịch. HTTP 204 chỉ xác nhận yêu cầu kích hoạt, phải xem workflow và DB
  tiếp. Chưa khẳng định lịch tự động đã hoạt động nếu chưa thấy lượt schedule thật.

Chưa có API quản trị nhận yêu cầu training, dashboard React hoặc cảnh báo. Không
tự huấn luyện lại định kỳ hay khởi chạy nền dài hạn trong lần triển khai này.

## Kiểm tra thực tế và file thay đổi

Preview Aiven ngày 08/11/2026 theo giờ Việt Nam (cutoff 07/11 18:44:44 UTC):
2.316 cặp baseline, 2.283 cặp đủ đặc trưng ML, mới 6 ngày dữ liệu. Chưa đạt gate
14 ngày nên chưa huấn luyện ML thật. Baseline test theo thời gian có 346 mẫu,
MAE 1,272 xe và RMSE 2,099 xe; đây là backtest khởi đầu, không phải chất lượng
mô hình đã triển khai. Lúc preview, cả 10 trạm quá ngưỡng 10 phút nên xem trước
đều unavailable. Không nới ngưỡng và không tạo số dự đoán giả.

208 tests đã qua, gồm source/time cutoff, nhãn đúng timestamp, thiếu thời tiết,
chống trùng, rollback, giữ model cũ, RF JSON khớp sklearn, scheduler không train
và dung sai đánh giá giữ theo lần phát hành. Đã kiểm thử trên SQLite riêng và kiểm tra DDL MySQL/migration cộng thêm, workflow
qua actionlint. Chưa áp migration 0006 lên Aiven, chưa kiểm tra commit dự đoán trên
MySQL thật hoặc runner Prediction thật; chưa bật lịch. Bằng chứng:
[prediction_verification.json](prediction_verification.json).

File thêm/sửa:

- `prediction/`: config, data, learning, registry, training, worker và main.
- `shared/models/__init__.py`, `shared/repositories/gold.py`, `shared/database.py`.
- `database/migrations/versions/0006_prediction.py`, `database/data_layers.json`.
- `requirements-prediction.txt`, `requirements-dev.txt`, `.env.example`.
- `.github/workflows/citibike-prediction.yml`, `scripts/run_github_prediction.py`.
- `tests/test_prediction.py`, `tests/test_migrations.py`, `tests/test_schema_compatibility.py`.
- README, hướng dẫn này, báo cáo kiểm tra, tài liệu Bronze/Silver/Gold và hai bản
  `Yeu_Cau_Web_Seoul_Bike.md` (gốc và docs).

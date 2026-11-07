# Clustering — phân nhóm trạm Citi Bike

Service độc lập: đọc Silver trên MySQL, tạo đặc trưng lịch sử từng trạm, chạy
StandardScaler + K-means, ghi snapshot Gold. Không gọi API nguồn, không cần proxy,
không chạy Analysis hoặc Prediction bên trong. Giữ lịch collector 30 phút và
Analysis 5 phút hiện có. Clustering chạy mỗi ngày theo America/New_York.

## Chạy trên Windows

Mở terminal tại `F:\126\NewYorkBike`. Dùng đúng Python của `.venv`:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-clustering.txt
.\.venv\Scripts\python.exe -m clustering.main --preview
```

Preview đọc Aiven với transaction READ ONLY, không cần migration mới và không ghi
bảng nào. Xem `artifacts\clustering_preview.json`: `parameters.status`, `summary`,
`rejected_stations` và `members`. Không có thành viên nếu chưa đủ điều kiện.

**Đẩy mã mới lên GitHub trước khi nâng schema.** Collector/Analysis đang chạy
trên GitHub cần có file migration mới để nhận diện revision 0005 là hậu duệ hợp lệ.
Chạy lại collector/Analysis trên mã mới và kiểm tra thành công, rồi mới chạy:

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic current
.\.venv\Scripts\python.exe -m clustering.main --once
```

Head mong đợi `0005_clustering`. Migration chỉ tạo `clustering_runs` và
`station_clusters` trong **database MySQL hiện có**; không đổi/xóa dữ liệu cũ.
`service_runs` được dùng chung làm sổ vận hành, phân biệt bằng `service_name`.

`status=success`: đã lưu snapshot và nhóm của các trạm đủ điều kiện.
`status=insufficient_data`: đã ghi lý do vào lịch sử, **không tạo nhóm**. Đây không
phải lỗi kết nối. `failed` là lỗi cần kiểm tra; lệnh trả mã thoát 1 khi có lỗi.

Khi chạy lại cùng ngày New York, phiên bản và cấu hình, snapshot thành công được
giữ nguyên, không nhân đôi. Lượt thiếu dữ liệu/lỗi có thể thử lại cùng khóa; số lần
thử nằm trong `service_runs.attempt_count`. Mỗi service có khóa MySQL riêng để tránh
hai tiến trình cùng công bố. Thành viên và trạng thái thành công commit cùng nhau;
lỗi không làm mất snapshot thành công trước.

Muốn chạy trên máy: mở terminal riêng:

```powershell
.\.venv\Scripts\python.exe -m clustering.main --schedule
```

Chạy ngay một lần, sau đó 02:00 New York mỗi ngày; ngày chuyển DST thiếu 02:00 thì
chạy 03:00. Tắt terminal/tắt máy là dừng. Ctrl+C để dừng. Không cần chạy lịch local
nếu đã chọn chạy trên GitHub. Lệnh không tự chạy nền khi bạn tắt máy.

## Cửa sổ và chất lượng dữ liệu

- Mặc định 7 **ngày lịch New York đã hoàn tất**, kết thúc lúc 00:00 ngày chạy.
  UTC được lưu trong DB; tuần chuyển DST có thể 167 hoặc 169 giờ.
- Chỉ đọc collection `success`/`partial` đã hoàn tất trước cutoff; quan sát phải
  được thu và nguồn đã báo trước cutoff. Không đọc Seoul sang Citi Bike.
- Mỗi slot thu thập 1.800 giây lấy bản thu cuối cùng, kể cả nếu bản cuối inactive.
  Không lấp khoảng mất, không biến NULL thành 0, không dùng dữ liệu chưa công bố.
- Chỉ dùng mẫu `valid`, installed và renting đều true, số xe từ 0 đến capacity.
  Mẫu inactive/stale/thiếu/không hợp lệ bị loại, có số đếm trong báo cáo.
- Mỗi ngày cần độ phủ >=80%; tổng >=200 mẫu; mỗi giờ địa phương có >=2 mẫu;
  có các cặp mẫu kề nhau. Tối thiểu 6 trạm đạt điều kiện để thử phân nhóm.
- Sức chứa phải dương. Không dùng `rack_count` thay capacity. Capacity lấy từ
  metadata hiện tại và lưu snapshot; chưa tái dựng capacity lịch sử từ Bronze.
  Nếu số xe vượt capacity hiện tại thì loại mẫu thay vì ép giá trị xuống.
- Khoảng thay đổi chỉ tính giữa hai slot kề nhau, không bắc cầu qua mẫu mất/lỗi.
  Không có liên kết thời tiết không làm mất mẫu xe trong Clustering v1: service
  này phân nhóm theo đặc điểm xe/thời gian; thời tiết vẫn thuộc Analysis/Prediction.

Các biến `CLUSTERING_*` nằm trong `.env.example`, có mặc định khi chưa thêm `.env`.
`CLUSTERING_EXPECTED_INTERVAL_SECONDS` là **nhịp dữ liệu**, không phải lịch worker.
Không giảm điều kiện để ép dữ liệu ít ngày thành kết quả có vẻ đầy đủ.

## Đặc trưng và thuật toán

9 đặc trưng theo thứ tự lưu ở `parameters.feature_names`:

1. Trung bình số xe / capacity.
2. Độ lệch chuẩn quần thể số xe / capacity.
3. Trung bình thay đổi tuyệt đối giữa các slot kề / capacity.
4. Tỷ lệ hết xe (=0).
5. Tỷ lệ ít xe (1 đến 3; ngưỡng cấu hình được), tách khỏi hết xe.
6. Trung bình xe / capacity vào 00–06 giờ.
7. Trung bình xe / capacity vào 06–10 giờ.
8. Trung bình xe / capacity vào 10–16 giờ.
9. Trung bình xe / capacity vào 16–24 giờ.

Chuẩn hóa bằng StandardScaler trên các trạm đủ điều kiện. Thử k từ 2 đến
min(`CLUSTERING_MAX_CLUSTERS`, số trạm / 2 làm tròn xuống, số vector khác nhau).
K-means dùng seed 42 và n_init=20. Loại phương án có nhóm chỉ 1 trạm hoặc suy biến;
chọn silhouette cao nhất, hòa điểm chọn k nhỏ hơn; chỉ công bố khi điểm >0.
Không có phương án phù hợp thì báo `insufficient_data`, không ép gán nhóm.

Lưu scaler, tâm cụm trước/sau chuẩn hóa, tất cả điểm ứng viên, kích thước nhóm và
phiên bản scikit-learn. Lưu thêm thống kê xe gốc, biểu đồ 24 giờ và độ phủ từng ngày
để diễn giải. Nhãn 0/1/2 chỉ là mã trong **một run**; không tự đặt tên “thiếu xe”
hoặc khẳng định nhóm giống nhau qua các ngày. Với 10 trạm, kết quả là thử nghiệm;
silhouette không đo độ chính xác dự đoán hay chứng minh nguyên nhân nhu cầu thuê.

Tài liệu thuật toán: [KMeans](https://scikit-learn.org/1.7/modules/generated/sklearn.cluster.KMeans.html),
[StandardScaler](https://scikit-learn.org/1.7/modules/generated/sklearn.preprocessing.StandardScaler.html),
[silhouette_score](https://scikit-learn.org/1.7/modules/generated/sklearn.metrics.silhouette_score.html).

## Xem kết quả trên Aiven

```sql
SELECT id, run_date, status, window_start, window_end, parameters, summary
FROM clustering_runs WHERE source = 'citibike'
ORDER BY run_date DESC, id DESC LIMIT 10;

SELECT c.clustering_run_id, c.station_id, s.name, c.cluster_label,
       c.sample_count, c.coverage, c.feature_values
FROM station_clusters c
JOIN stations s ON s.source=c.source AND s.station_id=c.station_id
WHERE c.source='citibike' AND c.clustering_run_id = (
  SELECT r.id FROM clustering_runs r
  JOIN service_runs sr ON sr.source=r.source AND sr.id=r.service_run_id
  WHERE r.source='citibike' AND r.status='success' AND r.finished_at IS NOT NULL
    AND sr.service_name='clustering' AND sr.status='success' AND sr.finished_at IS NOT NULL
  ORDER BY r.run_date DESC, r.finished_at DESC, r.id DESC LIMIT 1
)
ORDER BY c.cluster_label, c.station_id;
```

Repository `latest_clustering_run`/`station_clusters` cũng chỉ công bố snapshot
thành công, giữ bản trước nếu lượt mới lỗi/thiếu. Khi dùng cho Prediction tương
lai phải truyền `available_at` bằng cutoff dự đoán để tránh nhìn trước tương lai.
Có thể truyền `configuration_hash` để chỉ đọc cấu hình mong muốn.

## Chạy khi tắt laptop

Workflow riêng `.github/workflows/citibike-clustering.yml` và
`scripts/run_github_clustering.py`; dùng lại 6 Secrets MySQL/CA hiện có, không cần
Secret proxy. Sau push và migration, chạy **Actions → Citi Bike clustering → Run
workflow** một lần rồi kiểm tra log. Chưa tự bật lịch trong lần triển khai này.

Chọn **một** cách bật lịch:

- GitHub: Repository variable `ENABLE_CLUSTERING_SCHEDULE=true`. Workflow dùng
  07:00 UTC mỗi ngày: 02:00 EST hoặc 03:00 EDT; GitHub có thể khởi chạy trễ.
- cron-job.org: tắt/không bật biến trên; tạo cronjob mỗi ngày 02:00, timezone
  `America/New_York`, POST đến:
  `https://api.github.com/repos/bap-05/NewYorkBike/actions/workflows/citibike-clustering.yml/dispatches`.
  Dùng headers Authorization Bearer token riêng có quyền Actions write cho repo,
  Accept `application/vnd.github+json`, Content-Type `application/json`, body
  `{"ref":"main"}`. Không đưa token vào mã/URL/ảnh chụp. HTTP 204 chỉ xác nhận
  GitHub nhận yêu cầu; kiểm tra tiếp kết quả workflow và `clustering_runs`.

## Đã kiểm tra và giới hạn

Preview Aiven ngày 07/11/2026: cửa sổ từ 31/10 00:00 đến 07/11 00:00 giờ New York,
2.125 mẫu đầu vào, 10 trạm, 338 slot dự kiến/trạm (có ngày đổi DST). Không trạm nào
đủ độ phủ 7 ngày: kết quả `insufficient_data`, không ghi DB/không tạo thành viên.
Báo cáo local: `artifacts/clustering_preview.json`.

Sau khi người dùng xác nhận, mã đã push lên GitHub ở commit `946d597` và migration
0005 đã áp dụng Aiven thành công ngày 07/11/2026. Đã kiểm tra hai bảng mới tồn tại,
khóa ngoại đúng và còn trống; cột/số dòng các bảng cũ giữ nguyên tại lúc kiểm tra.
Chưa chạy phân nhóm ghi kết quả trên MySQL thật hoặc workflow Clustering trên runner thật;
kiểm thử migration, thuật toán, rollback và chống trùng dùng SQLite độc lập.
Chưa có Prediction, API hay giao diện phân nhóm. Không tạo số liệu nhóm giả.

Toàn bộ 176 tests đã qua, gồm cửa sổ/lịch DST, loại inactive/NULL, nguồn riêng,
dedup slot, gate 7 ngày, chọn k, tính lặp lại, chống ghi trùng, rollback nguyên tử,
giữ snapshot trước và migration không thay bảng cũ. Workflow qua actionlint.
Bằng chứng tóm tắt: [clustering_verification.json](clustering_verification.json).

## File thêm/sửa trong phần Clustering

- `clustering/__init__.py`, `config.py`, `features.py`, `algorithm.py`, `worker.py`,
  `main.py`: cấu hình, đọc Silver, thuật toán, lưu snapshot và CLI/lịch ngày.
- `shared/models/__init__.py`, `shared/repositories/gold.py`: model và đọc Gold.
- `database/migrations/versions/0005_clustering.py`, `database/data_layers.json`:
  migration cộng thêm và hợp đồng dữ liệu cập nhật.
- `requirements-clustering.txt`, `requirements-dev.txt`, `.env.example`: phụ thuộc
  riêng và mẫu cấu hình; không sửa `.env` thật.
- `scripts/run_github_clustering.py`, `.github/workflows/citibike-clustering.yml`:
  job riêng dùng Secrets hiện có, lịch tự động chưa bật.
- `tests/test_clustering.py`, `tests/test_migrations.py`,
  `tests/test_schema_compatibility.py`: kiểm thử và tương thích schema.
- `README.md`, `docs/Clustering.md`, `docs/clustering_verification.json`,
  `docs/Bronze_Silver_Gold.md`, `docs/Yeu_Cau_Web_Seoul_Bike.md` và bản yêu cầu
  gốc `Yeu_Cau_Web_Seoul_Bike.md`: tài liệu và kết quả kiểm tra.

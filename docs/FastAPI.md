# FastAPI — Dữ liệu và kích hoạt dịch vụ Citi Bike

EDA trên web: `GET /api/eda` và
`GET /api/eda/reports/{report_id}/figures/{filename}`. Chỉ đọc report hoàn tất tại
`API_EDA_REPORT_DIR` (mặc định artifacts/eda); không gọi database hoặc chạy EDA từ
request này. Chỉ trả metadata/thống kê cho phép và PNG, không công bố HTML/CSV hay
đường dẫn máy chủ. Xem [hướng dẫn EDA](EDA.md).

API ở `services/database-api/app/`, dùng SQLAlchemy model và Aiven MySQL hiện có. Các GET
công khai dùng transaction READ ONLY, chỉ đọc Silver/Gold đã công bố. Các POST quản trị
kích hoạt Analysis, Clustering, Prediction 30 phút và dự báo ngày mai bằng tác vụ nền có xác thực; không huấn luyện.
Không tạo schema khi
khởi động; yêu cầu database đã có `0006_prediction` hoặc revision kế thừa hợp lệ.

## Chạy trên Windows

Mở terminal tại thư mục gốc `F:\126\NewYorkBike`, giữ `.env`/chứng chỉ CA hiện có:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --log-level error --no-access-log
```

Mở trình duyệt:

- `http://127.0.0.1:8000/docs`: Swagger, chọn GET → Try it out → Execute.
- `http://127.0.0.1:8000/health/live`: tiến trình API còn hoạt động.
- `http://127.0.0.1:8000/health/ready`: kết nối và schema sẵn sàng.
- `http://127.0.0.1:8000/api/stations`: danh sách trạm và dữ liệu mới nhất.

Muốn tự tải lại khi sửa code, thêm `--reload` cho môi trường phát triển. Terminal
API cần mở; Ctrl+C để dừng. Đây là chạy local, chưa triển khai API lên server và
giao diện React chạy riêng ở `frontend/`, xem [hướng dẫn React](../frontend/README.md).
API không cần proxy, không ảnh hưởng các lịch cloud hiện có.
Không chạy migration lại chỉ vì thêm API hoặc tách file model.

Có thể kiểm tra nhanh từ PowerShell khi server đang mở:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health/ready
Invoke-RestMethod http://127.0.0.1:8000/api/overview
```

## Endpoint đã có

| GET | Nội dung |
|---|---|
| `/health/live` | Liveness không cần kết nối DB |
| `/health/ready` | DB/schema sẵn sàng; không khẳng định dữ liệu còn mới |
| `/api/overview` | Số trạm theo dõi, số xe trên mẫu còn mới, trạng thái worker |
| `/api/stations` | Tìm tên `q`, `monitored_only`, `source`, phân trang |
| `/api/stations/{station_id}` | Metadata, xe/thời tiết và dự đoán mới nhất |
| `/api/stations/{station_id}/history` | Quan sát lịch sử, gồm missing/inactive và weather nếu có |
| `/api/stations/{station_id}/predictions` | Lịch sử dự đoán đã lưu và đối chiếu nếu có |
| `/api/stations/{station_id}/predictions/latest` | Bản dự đoán mới nhất, kể cả bản unavailable |
| `/api/analysis` | Thống kê Gold đã tính, lọc trạm/metric/aggregation/cấu hình |
| `/api/clusters` | Lượt Clustering mới nhất và snapshot thành công gần nhất |
| `/api/clusters/{run_id}/stations` | Thành viên của snapshot thành công đã công bố |

Swagger/OpenAPI có schema kiểu dữ liệu. Các mã nguồn được hỗ trợ là `citibike`
(mặc định) và `seoul` (chỉ dữ liệu legacy thực sự có trong DB). Không ghép trạm hay
quan sát giữa hai nguồn. Giữ station_id là chuỗi, kể cả khi ID có số 0 ở đầu.
`monitored_only=false` cho phép xem cả metadata trạm đã ngừng theo dõi; dữ liệu cũ
không bị xóa. Các endpoint ghi bên dưới yêu cầu token quản trị.

## Chạy dịch vụ từ Swagger, không huấn luyện lại

1. Đặt `API_SERVICE_TOKEN` trong `.env` thành chuỗi bí mật ngẫu nhiên, rồi khởi động lại API.
   Có thể tạo chuỗi bằng `.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(32))"`.
   Token chỉ nằm ở backend, không đưa vào biến `VITE_*` hay Git.
2. Xuất mô hình phân cụm đã huấn luyện từ DB **trước khi xóa kết quả demo**:

   ```bat
   .venv\Scripts\python.exe -m clustering.main --export-model
   ```

   Lệnh chỉ đọc một lượt huấn luyện thành công rồi lưu scaler và tâm cụm vào
   `CLUSTERING_MODEL_FILE` (mặc định `artifacts/clustering/model.json`), không gọi fit.
   Có thể thêm `--training-run-id ID` để chọn lượt cụ thể. Giữ file này khi xóa đầu ra demo.
3. Mở `http://127.0.0.1:8000/docs`, nhấn **Authorize**, dán giá trị token (không thêm `Bearer`).
   Trong nhóm **Service activation**, chọn POST, nhấn **Try it out → Execute**.

| Endpoint | Tác dụng |
| --- | --- |
| `POST /api/services/analysis/run` | Tính và lưu thống kê Gold từ dữ liệu hiện có |
| `POST /api/services/prediction/run` | Dự báo 30 phút bằng mô hình đã lưu; vẫn áp dụng điều kiện dữ liệu mới |
| `POST /api/services/day-ahead/run` | Phát hành dự báo ngày mai vào DB và chấm các giờ đã kết thúc |
| `POST /api/services/clustering/run` | Gán nhóm bằng scaler và tâm cụm đã lưu, không chọn lại k |
| `GET /api/services/jobs/{job_id}` | Xem trạng thái và ID kết quả trong DB |
| `GET /api/services/clustering/model` | Xem phiên bản, cửa sổ huấn luyện và số nhóm của mô hình đã lưu |

Body chạy bình thường: `{"rebuild": false}`. Khi kết quả đã bị xóa nhưng dấu lượt chạy
thành công vẫn còn, dùng `{"rebuild": true}` để tạo lại phần thiếu. Prediction chỉ bổ sung
bản ghi thiếu trong kỳ hiện tại, giữ nguyên các dự báo còn tồn tại và thời điểm phát hành;
không dựng lại dự báo lịch sử. API Prediction này dành cho **30 phút**, không phải dự báo ngày mai.

Để chạy dự báo ngày mai, chọn **service = `day-ahead`** trong POST
`/api/services/{service}/run`, nhập `{"rebuild": false}` rồi Execute. Job trả
`publication_id`, `target_date`, `available_hours` và `trained: false`. Khi thành công,
web đọc bản đã lưu qua `GET /api/eda/day-ahead`.

Nếu bản ngày mai đã bị xóa, API tính và lưu lại từ dữ liệu gốc với thời điểm phát hành mới.
Nếu bản hoàn chỉnh còn tồn tại, chạy lại vẫn giữ nguyên ID, giá trị và giờ phát hành.
`{"rebuild": true}` chỉ cho phép thêm phiên bản cải thiện bản thiếu giờ khi dữ liệu đáp ứng,
giữ nguyên bản cũ. Thiếu dữ liệu để phát hành: job `skipped`, lý do
`no_eligible_forecast_inputs`; có thể chạy lại khi dữ liệu đủ. API cũng cập nhật đối chiếu
thực tế các bản đã lưu, dùng chung khóa `prediction` với worker 30 phút và lịch ngày mai.
Dữ liệu ngày mai nằm trong `luot_chay_dich_vu`, các dòng `ten_dich_vu = 'day_ahead'`,
cột `tom_tat`; xóa bảng `du_doan_so_xe` chỉ xóa dự báo 30 phút.

Analysis và Clustering nhận thêm `cutoff` là ISO timestamp có múi giờ trong quá khứ.
Để demo phân cụm bằng cửa sổ có dữ liệu đầy đủ, lấy `training_window_end` từ GET model
làm cutoff. Đây là chạy lại dữ liệu lịch sử để demo, không phải kiểm thử ngoài mẫu.
Prediction và `day-ahead` không nhận cutoff quá khứ. Nếu dữ liệu mới thiếu hoặc cũ, kết quả sẽ ghi rõ
`insufficient_data`/`unavailable`, không tự giảm ngưỡng chất lượng.

POST trả HTTP **202** kèm `job_id`; gọi GET job cho đến khi `status` là `success`,
`skipped` hoặc `failed`, rồi mở DB và tải lại web. Tác vụ dùng chung khóa MySQL với CLI;
nếu worker khác đang chạy, job báo bận để thử lại. Không tắt API giữa lúc job chạy;
đây là tác vụ nền trong tiến trình API, không phải hàng đợi bền vững qua việc khởi động lại.

Không cấu hình token: HTTP 503; sai token: 401; thiếu/hỏng mô hình phân cụm: 409.
API không tự huấn luyện khi thiếu mô hình. Trong Docker, giữ mount `./artifacts:/app/artifacts:ro`
của API và chuẩn bị file mô hình từ host hoặc job trước khi khởi động.
Chỉ xóa đầu ra trên DB demo; giữ Silver, metadata trạm, registry mô hình dự báo và file phân cụm.

CLI cũng hỗ trợ tái sử dụng:

```bat
.venv\Scripts\python.exe -m clustering.main --once --reuse-model
.venv\Scripts\python.exe -m clustering.main --once --reuse-model --rebuild
```

CLI `--once`/`--schedule` không có `--reuse-model` vẫn giữ hành vi huấn luyện hiện có.

## Phân trang, khoảng thời gian và thời gian New York

- `limit`: 1–500; `offset`: 0–100.000. Response có total/limit/offset/has_more.
- History/Prediction mặc định 24 giờ; Analysis mặc định 7×24 giờ gần nhất.
- `from`, `to`: ISO8601 **có múi giờ**, như `2026-11-08T00:00:00Z`.
  Yêu cầu `from < to <= now`, độ dài tối đa 31×24 giờ (cấu hình được). Không dùng
  chuỗi giờ VN/NY không có offset. Với offset `+`, phải encode `+` trong URL;
  dùng Swagger hoặc UTC `Z` để tránh lỗi. Khoảng từ bao gồm, đến không bao gồm.
- History sắp sampled_at/id tăng dần; Prediction sắp issued_at/id giảm dần;
  Analysis theo window_start giảm dần, rồi station_id/id. Không có export vô hạn.
- `aggregation=hour|day`; `metric_name` lọc tên metric; `configuration_hash` phải
  là 64 ký tự hex. Mặc định Analysis lấy cấu hình và phiên bản tính mới nhất đã
  công bố, không cộng trộn nhiều phiên bản/cấu hình vào một chuỗi.

Mọi timestamp trả dạng:

```json
{
  "utc": "2026-11-09T07:00:00Z",
  "local": "2026-11-09T02:00:00-05:00"
}
```

Ví dụ này chỉ mô tả định dạng thời gian, không phải dữ liệu trạm giả. Mỗi response
có `meta.source`, `meta.timezone=America/New_York`, `meta.as_of`. Khi đổi DST, cùng
01:30 địa phương có thể mang -04:00 hoặc -05:00; UTC phân biệt được hai thời điểm.

## Chất lượng và công bố dữ liệu

- Chỉ collection success/partial, có finished_at <= as_of; sampled/collected và
  source_observed_at nếu có không được ở tương lai. Mẫu mới nhất thắng, kể cả khi
  inactive/missing. Không tự lùi về mẫu valid cũ để trình bày trạm đang hoạt động.
- `availability_status`: fresh/stale/inactive/missing/invalid/unknown. `is_current`
  chỉ true khi valid và installed/renting đều true, số xe có giá trị và sampled_at
  lẫn source_observed_at đều còn mới (mặc định <=600 giây).
- NULL giữ NULL. Số 0 thật vẫn là 0. Tổng xe của overview là NULL nếu không trạm
  nào có mẫu fresh; không biến tình trạng thiếu dữ liệu thành “toàn hệ thống hết xe”.
- Thời tiết chỉ lấy qua link của quan sát đúng trạm, collection thời tiết đã
  công bố đúng nguồn. Giữ đơn vị gốc và interval; partial/stale/invalid có nhãn,
  không đổi km/h thành m/s chỉ bằng cách thay chữ. Weather chưa công bố không lộ.
- Gold chỉ đọc khi marker service tương ứng thành công và finished_at <= as_of.
  Lượt chạy dở không được công bố. Snapshot Clustering thành công trước vẫn đọc
  được khi lượt mới insufficient_data/failed; latest_attempt cho biết trạng thái mới.
- Chưa có nhóm thành công: `/api/clusters` trả trạng thái thật và latest_success=NULL,
  không tạo nhóm demo. Đọc thành viên run chưa công bố trả HTTP 409; không có run
  hoặc sai source trả 404.
- Prediction giữ status baseline/ml/unavailable và mốc input/cutoff/issued/target.
  `is_current`/`display_reason` bổ sung kiểm tra hết hạn, tuổi dự đoán và độ mới của
  chính quan sát đầu vào lẫn trạng thái trạm mới nhất. Không lấy baseline cũ thay
  bản unavailable mới. Giá trị dự đoán đã hết hạn vẫn có thể xem trong lịch sử,
  nhưng không được đánh dấu là dự đoán hiện tại.
- Model trả id/name/kind/trained_at, không trả cây RF, SQLAlchemy internals, raw
  error hoặc cấu hình DB. Các endpoint không nhận SQL hoặc đường dẫn file từ client.

Collector vẫn 30 phút. Vì ngưỡng fresh là 10 phút, nhiều thời điểm API sẽ trả
stale/unavailable; đây là phản ánh đúng độ mới, không phải API bị hỏng.

## Cấu hình và bảo vệ

`.env.example` có `API_CORS_ORIGINS` (JSON array), `API_BIKE_MAX_AGE_SECONDS`,
`API_PREDICTION_MAX_AGE_SECONDS`, `API_MAX_RANGE_DAYS`. Không thay `.env` thật nếu
đã điền MySQL. CORS chỉ cho phép origin cụ thể; mặc định React dev ở localhost/
127.0.0.1:5173, GET, không credentials. CORS không phải cơ chế đăng nhập.

API dùng engine riêng với transaction MySQL READ ONLY, không nâng schema hoặc
commit dữ liệu nghiệp vụ. Lỗi DB/schema trả 503 với thông báo an toàn. Live check
vẫn trả 200 khi DB không sẵn sàng. Khi lên server có thể dùng tài khoản MySQL chỉ
có SELECT cho API; bộ credential Aiven hiện tại vẫn hoạt động local qua READ ONLY.

Phần đăng nhập, sửa theo dõi trạm, yêu cầu train, kích hoạt model và export admin
**chưa triển khai**. Không có API ghi công khai chưa xác thực. Frontend React mới
có thư mục hướng dẫn, chưa có ứng dụng/bản đồ. Chưa kiểm thử tải nhiều người dùng,
chưa triển khai server công khai hoặc bật scheduler trong FastAPI.

Thiết kế theo [APIRouter](https://fastapi.tiangolo.com/tutorial/bigger-applications/),
[dependency có yield](https://fastapi.tiangolo.com/tutorial/dependencies/dependencies-with-yield/)
và [CORS](https://fastapi.tiangolo.com/tutorial/cors/) của tài liệu FastAPI.

## Kết quả kiểm tra ngày 09/11/2026

- 238 tests qua, gồm các worker cũ và API mới; kiểm tra phân trang, source, NULL,
  dữ liệu chưa công bố, hết hạn, CORS, schema, lỗi DB không lộ thông tin, DST và
  session từ chối ghi. Không ghi dữ liệu test vào Aiven.
- TestClient với Aiven READ ONLY trả 200 cho health, overview, stations/detail/
  history, analysis, clusters và predictions. Danh sách có 10 trạm; khi kiểm tra
  mẫu đã cũ nên trả stale. Analysis có 30.210 metric trong phạm vi mặc định.
- Clustering thật chưa có snapshot success nên API trả insufficient_data; route
  thành viên snapshot được kiểm thử bằng dữ liệu test cô lập, chưa xác minh bằng
  nhóm thật trên Aiven. Không tạo nhóm giả để thử giao diện.
- Đã khởi động Uvicorn tạm trên localhost và gọi HTTP thật tới Aiven, các endpoint
  thử đều 200; tiến trình thử đã dừng. Không để server nền chạy lâu dài.
- Định nghĩa class model được so sánh AST với trước tách file, giữ nguyên toàn bộ.
  Không chạy migration hoặc thay đổi lịch worker. Script đóng gói mới chạy thành
  công, vẫn loại .env, certs, Bronze và môi trường Python.

Bằng chứng: [api_verification.json](api_verification.json). Bố cục mới xem
[Tài liệu tổng hợp](../PROJECT_REPORT.md). Chưa push phần FastAPI hoặc triển
khai lên server công khai trong lần chỉnh sửa này.

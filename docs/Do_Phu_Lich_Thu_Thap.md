# Độ phủ khi đổi từ 30 phút sang 5 phút

Mốc người dùng xác nhận: **18:25 ngày 09/11/2026 giờ Việt Nam** = **06:25 New York
(EST)** = **2026-11-09T11:25:00+00:00**.

Analysis và Clustering đọc chung `config/sampling_schedule.json`. Trước mốc này,
nhịp lịch sử là 1800 giây; từ mốc này nhịp Citi Bike là 300 giây. Seoul có lịch
riêng. Không suy luận nhịp từ khoảng cách giữa các bản ghi: thiếu mẫu vẫn là thiếu,
không tự biến thành đổi lịch.

## Cách tính

- Mỗi mốc lịch lấy mẫu là một slot UTC. Nếu ghi nhiều lần trong slot, lấy mẫu cuối,
  kể cả mẫu cuối inactive/invalid. Không đếm lặp để nâng độ phủ.
- Coverage = số slot có mẫu hợp lệ / số slot kỳ vọng theo từng giai đoạn lịch.
- Analysis chỉ đòi slot đã đến hạn theo cutoff và grace 120 giây mặc định. Mẫu đã
  nhận trong grace được tính ngay; không đòi mẫu tương lai. Giữ quy tắc bắt đầu
  tính từ lịch sử đầu tiên thật của trạm, không phạt thời gian chưa theo dõi.
- Clustering giữ cửa sổ 7 ngày New York hoàn tất và ngưỡng 80% mỗi ngày. Đếm theo
  UTC nên ngày DST 23/25 giờ vẫn chính xác.
- Mẫu inactive/invalid không đạt coverage chất lượng, nhưng không bị coi là chưa
  thu được. `missing_slot_ratio` phân biệt slot không có bản ghi với slot lỗi.
- Biến động chỉ so hai slot liền kề theo lịch đang áp dụng, không nối qua slot
  5 phút bị mất vì lịch cũ từng là 30 phút.
- Không thêm dữ liệu giả, không điền NULL bằng 0 và không xóa dữ liệu gốc.

Ví dụ theo giờ New York ngày chuyển lịch:

| Cửa sổ | Slot kỳ vọng |
|---|---|
| 05:00–06:00 | 05:00, 05:30 → 2 mẫu |
| 06:00–07:00 | 06:00, 06:25, 06:30, 06:35, 06:40, 06:45, 06:50, 06:55 → 8 mẫu |
| 07:00–08:00 | 07:00, 07:05, …, 07:55 → 12 mẫu |

Ngày 08/11 có 48 slot; ngày chuyển 09/11 có 224; ngày thường đầy đủ sau đó có 288.
Đây là số kỳ vọng theo lịch, không phải khẳng định thực tế đã thu đủ.

Các trung bình/đặc trưng vẫn tính trên mẫu thật sau khử trùng slot; chưa đổi sang
trọng số thời lượng hoặc trọng số bằng nhau cho từng ngày. Sửa độ phủ không đổi
thuật toán Prediction/ML hoặc mục tiêu sampled_at +30 phút.

## Cấu hình và áp dụng

Giữ `ANALYSIS_EXPECTED_INTERVAL_SECONDS=1800` và
`CLUSTERING_EXPECTED_INTERVAL_SECONDS=1800` làm nhịp **trước lần chuyển đầu tiên**.
Không đổi hai biến thành 300 vì sẽ đánh giá sai dữ liệu cũ. Những lần chuyển sau
thêm vào JSON theo thứ tự thời gian, có offset; effective_at phải trùng mốc nhịp mới.
`SAMPLING_SCHEDULE_FILE` cho phép chọn file khác, mặc định tương đối từ gốc dự án.

File chỉ khai báo kỳ vọng, **không bật hoặc đổi lịch collector**. Lịch thật trên
cron-job.org vẫn đặt riêng. Không cần secret hoặc migration mới.

Kiểm tra từ thư mục gốc trên Windows:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_cadence.py tests/test_analysis.py tests/test_clustering.py -q
.\.venv\Scripts\python.exe -m analysis.main --preview --output artifacts/analysis_cadence_preview.json
.\.venv\Scripts\python.exe -m clustering.main --preview --output artifacts/clustering_cadence_preview.json
```

Preview chỉ đọc MySQL, không ghi Gold hoặc khởi chạy lịch nền. Workflow chỉ nhận
mã mới khi mã có trên ref mà nó chạy; mặc định các job hiện dùng main. Mã mới chỉ
ở nhánh feature chưa áp dụng cho các job main. Không tự push/merge/sửa ref trong
đợt sửa cách tính này.

Phiên bản mới `analysis-v2-cadence` và `clustering-v2-cadence`, cấu hình lịch cũng
nằm trong hash để không ghi đè kết quả cũ. API chọn cấu hình/phiên bản đã công bố
mới nhất; các Gold cũ được giữ để truy vết. Khi triển khai cloud, cập nhật đồng bộ
hai worker rồi kiểm tra lượt mới. Không công bố Gold v2 khi worker cloud vẫn v1.

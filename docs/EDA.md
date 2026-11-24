# Báo cáo EDA độc lập — Citi Bike

EDA khám phá dữ liệu để kiểm tra chất lượng và chuẩn bị cho huấn luyện. Công cụ
`services/data-analysis/eda/` đọc Silver trên Aiven. CLI xuất HTML/CSV/JSON/PNG ở máy;
worker `eda.snapshots` tính kết quả số và lưu trong DB để phục vụ web nhanh, không train model.

## Xem trên giao diện React

Các biểu đồ đường/phân tán/phân phối đã có ô chọn một ngày, tuần ISO hoặc
tháng lịch cụ thể theo New York, kèm lựa chọn trạm. Dữ liệu của kỳ đọc trực
tiếp từ Aiven bằng API chỉ đọc; không phụ thuộc thời điểm tạo báo cáo ảnh.
Kỳ hiện tại được báo chưa kết thúc, kỳ không có mẫu được hiển thị trống.
Các biểu đồ nâng cao đọc JSON đã được **Citi Bike analysis** tính và lưu trong DB.

Bản hiện tại có 12 hình tổng quan: đường, phân tán, phân phối theo
ngày/tuần/tháng, ma trận tương quan, xu hướng và mùa vụ tuần có điều kiện dữ liệu. Trang Dự đoán có
biểu đồ dự báo từng giờ ngày mai và phân loại mức xe sẵn có. Có bộ chọn trạm
và dạng biểu đồ **cột / đường / vùng**. Đổi trạm sẽ đổi dữ liệu dự báo tương ứng,
giữ dạng biểu đồ đã chọn. Đường/vùng được ngắt ở giờ thiếu dữ liệu hoặc giờ bị
ẩn bởi bộ lọc ít xe, không nối bù. Chọn một cột/điểm
để xem số ngày lịch sử cùng giờ, trạng thái và sai số kiểm thử. Xem phương pháp,
điều kiện và giới hạn tại [Yêu cầu chuỗi thời gian](Time_Series_Requirements.md).

Vào **Phân tích & phân nhóm → Khám phá dữ liệu (EDA)**. Chọn biểu đồ trong danh sách:
đường, phân tán, phân phối theo ngày/tuần/tháng, xu hướng, mùa vụ hoặc tương quan.
Có thêm mục **Phân rã xu hướng – mùa vụ – phần dư**, với bộ chọn trạm và nút mở ảnh lớn.
Các ảnh là snapshot của dữ liệu tại lúc tạo báo cáo.

### Phân rã chuỗi thời gian theo trạm

Dùng [STL của statsmodels](https://www.statsmodels.org/stable/generated/statsmodels.tsa.seasonal.STL.html),
chu kỳ 24 giờ và `robust=True`, với mô hình cộng:
**Chuỗi gốc = Xu hướng + Mùa vụ + Phần dư**. Chuỗi gốc là trung bình số xe theo giờ;
mùa vụ thể hiện chu kỳ ngày, không phải kết luận về mùa vụ năm hoặc tác động nhân quả của thời tiết.

Mỗi giờ phải có ít nhất 80% số mẫu hợp lệ theo lịch lấy mẫu đã khai báo. Chỉ sử dụng giờ hoàn tất,
khử trùng theo mốc và giữ ưu tiên nguồn hiện tại; mẫu lỗi mới nhất không được thay bằng mẫu cũ.
Không điền 0, không nội suy giờ thiếu, không dùng mẫu ước lượng. Chọn đoạn liên tục gần nhất
có ít nhất 168 giờ (7 chu kỳ ngày), ngắt đoạn khi thiếu giờ hoặc đổi UTC offset ở New York.
Nếu chưa đủ điều kiện, ảnh ghi rõ chưa đủ dữ liệu. Phạm vi dữ liệu được ghi trên ảnh.

Mỗi trạm có một ảnh bốn ô: chuỗi gốc, xu hướng, mùa vụ và phần dư. Kết quả số lưu trong
`time_series_decomposition.csv`; điều kiện chất lượng và đoạn được chọn lưu tại `summary.json`.
Đây là phân tích hồi cứu: STL sử dụng cả hai phía của chuỗi, không đưa các thành phần này
trực tiếp vào mô hình dự báo hoặc kiểm thử lịch sử vì có thể gây rò rỉ dữ liệu tương lai.

Giao diện EDA đọc dữ liệu đã công bố trong DB, không cần tạo report file trước.
Biểu đồ ngày/tuần/tháng dùng `/api/eda/series`. Xu hướng, mùa vụ, tương quan và phân rã
dùng `/api/eda/chart-data?kind=trend|seasonality|correlation|decomposition&days=28`;
có thể chọn 28/60/90 ngày và trạm phân rã. Giữ nguyên cửa sổ mở lớn, zoom và thao tác
xem giá trị của giao diện QUAN. Số liệu thiếu được giữ là NULL, chu kỳ thiếu độ phủ
được ngắt, không thay bằng 0. API chỉ đọc DB, không dự báo hay huấn luyện lại.
Worker giới hạn 100 trạm và 500.000 mẫu, đọc cửa sổ lớn nhất một lần rồi tính các cửa sổ
28/60/90 ngày. Dấu vân tay nội dung nhận biết cả sửa/xóa mẫu cũ, thay thời tiết, chất lượng,
metadata trạm và mốc giờ. Không đổi thì bỏ qua tính lại. API GET không tải lịch sử thô.

Chạy `python -m analysis.main --once` hoặc workflow **Citi Bike analysis** để cập nhật.
Kết quả nằm trong `luot_chay_dich_vu`, `ten_dich_vu='eda_snapshot'`; lượt tính có tên `eda`.
Toàn bộ kết quả được công bố trong một transaction, chỉ thay snapshot EDA cũ cùng phiên bản
và cửa sổ; không xóa dữ liệu nguồn hoặc kết quả dịch vụ khác. Lỗi giữ bộ thành công trước đó.
GET trả thời điểm dữ liệu và `status='missing'` nếu chưa có kết quả. API có xác thực
`POST /api/services/eda/run` cho phép tạo lại riêng EDA với `{"rebuild": true}`.

Trên Render đặt `EDA_AUTO_UPDATE=false` để tắt xuất báo cáo nền; biểu đồ DB vẫn chạy.
Không cần push `artifacts`, chép báo cáo GitHub Actions hoặc migration mới. Cần deploy
cả backend và frontend có route mới. Phần hướng dẫn xuất HTML/PNG dưới đây là tùy chọn.

Với endpoint báo cáo xuất file cũ, FastAPI đọc báo cáo đã hoàn tất trong `artifacts/eda/` ở máy chủ API, có thể đổi bằng
`API_EDA_REPORT_DIR` trong `.env`. Report chỉ được công bố sau khi cả summary.json
và report.html tồn tại. API chọn report có generated_at mới nhất đúng nguồn, không
chạy EDA trong HTTP request. API khởi động tiến trình nền riêng để kiểm tra dữ liệu
mới ngay khi khởi động và mỗi 15 phút (cần các phụ thuộc trong requirements.txt).
Mặc định dùng cửa sổ 28 ngày, tối đa 200.000 mẫu; không âm thầm cắt dữ liệu.
Web tự đọc số liệu DB mới mỗi phút. `EDA_AUTO_UPDATE=false` chỉ tắt lịch xuất file nền.
Khóa theo thư mục báo cáo tránh tạo trùng khi nhiều API worker cùng chạy. Thay đổi
lượt thu thập đã công bố, thêm lịch sử, thời tiết/liên kết hoặc đổi ngày New York
sẽ kích hoạt tạo lại. Không có thay đổi thì bỏ qua. Báo cáo mới được tạo trong
thư mục tạm ẩn và đổi tên sau khi hoàn tất; lỗi không thay báo cáo cũ. Trạng thái
kiểm tra ở `.automatic.json`, không ghi dữ liệu vào DB. Báo cáo cũ được giữ nguyên.

Sau khi thêm route mới, khởi động lại tiến trình FastAPI nếu không dùng `--reload`.
Vite tự cập nhật giao diện đang chạy. Nếu cần bản xuất file ở máy chủ API, chờ lịch
nền hoàn tất hoặc tạo bằng CLI bên dưới. Nếu API ở máy khác, sao chép nguyên thư mục
báo cáo tới thư mục EDA được cấu hình tại máy đó. Không cần migration mới.

`GET /api/eda` trả metadata, thống kê công khai và URL ảnh PNG có trong manifest.
Không công bố đường dẫn máy, HTML, audit CSV hoặc tham số model. Endpoint ảnh chỉ
đọc PNG trong danh sách cho phép, đúng report/nguồn và nằm trong thư mục báo cáo.

## Chạy trên Windows

```powershell
cd F:\126\NewYorkBike
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m eda.main --days 28
```

Log cuối in đường dẫn `artifacts/eda/<UTC-timestamp>/report.html`. Mở bằng Chrome,
Edge hoặc trình duyệt khác. HTML dùng ảnh và CSV trong cùng thư mục; nếu sao chép
để gửi hoặc lưu báo cáo, sao chép cả thư mục, không chỉ report.html.

Mở bản tạo gần nhất bằng PowerShell:

```powershell
$edaReport = Get-ChildItem .\artifacts\eda -Filter report.html -Recurse |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
Start-Process $edaReport.FullName
```

Chọn khoảng thời gian cụ thể (ISO bắt buộc có offset):

```powershell
.\.venv\Scripts\python.exe -m eda.main --from "2026-11-03T00:00:00-05:00" --to "2026-11-09T06:30:00-05:00" --output artifacts/eda/my_report
```

Mỗi lần mặc định tạo thư mục mới. `--output` chỉ nhận thư mục mới/trống, không ghi
đè báo cáo cũ. Khoảng tối đa 90 ngày, mặc định tối đa 100.000 bản ghi; vượt giới hạn
sẽ dừng, không âm thầm cắt mất dữ liệu. Có thể tăng `--max-rows` tối đa 1.000.000
nếu máy đủ RAM. Dùng `.env`/CA hiện có của Python; không thêm secret EDA riêng.

## Nội dung

| Tệp/phần | Ý nghĩa |
|---|---|
| report.html | Báo cáo để xem bằng trình duyệt |
| observations_audit.csv | Các quan sát đã công bố, cờ chất lượng, giờ UTC/NY, đơn vị/interval thời tiết; giữ mẫu thiếu |
| descriptive_statistics.csv | Mean, median, std population/sample, mode, min/max, quartiles, số mẫu; toàn bộ và từng trạm |
| missingness.csv | Thiếu raw, không dùng được, inactive, ghi lặp slot, số phép đo thời tiết khác nhau |
| daily_coverage.csv | Độ phủ từng trạm/ngày theo lịch 30/5 phút đã khai báo, cờ ngày một phần |
| outliers_review.csv | Cờ IQR, vượt sức chứa hiện tại, biến động lớn; không tự xóa |
| hourly/weekday/daily_profiles.csv | Thống kê theo giờ, thứ, ngày New York |
| correlation_*.csv và pair_counts_*.csv | Pearson và số cặp hợp lệ toàn bộ/từng trạm; JSON ghi tệp thuộc trạm nào |
| scaling_comparison.csv | Raw / Min-Max / Z-score và partition thời gian, thiếu vẫn để trống |
| summary.json | Phạm vi, cấu hình, số mẫu, tham số scaler và danh sách hình |
| figures/*.png | Chuỗi thời gian, histogram xe và các đặc trưng, giờ/thứ, độ phủ, thiếu dữ liệu, tương quan, boxplot, chuẩn hóa |

CSV mã hóa UTF-8 BOM để Excel trên Windows đọc đúng tên. ID trạm được giữ dạng
chuỗi trong Python/JSON; khi nhập CSV vào Excel, đặt cột station_id là Text để Excel
không tự bỏ số 0 đầu. Report/artifacts bị Git bỏ qua; không đưa dữ liệu/bí mật vào mã.

## Chính sách dữ liệu

- Chỉ dùng source đang chọn trong Settings, không trộn Citi Bike/Seoul. Chỉ đọc run
  success/partial đã hoàn tất tại cutoff; các mẫu chạy dở hoặc tương lai không được đọc.
- MySQL bắt buộc transaction READ ONLY, kiểm tra cờ phía server trước khi đọc.
  Đóng kết nối trước khi vẽ biểu đồ và xuất tệp.
- Khử trùng theo lịch ở config/sampling_schedule.json; lấy mẫu cuối trong slot
  kể cả inactive. CSV audit giữ raw rows và cờ slot_latest để truy vết.
- Không dropna toàn bộ DataFrame. Mẫu xe hợp lệ vẫn dùng cho thống kê xe khi thiếu
  thời tiết. Weather cohort yêu cầu nguồn/đơn vị/tọa độ/thời điểm và cả bốn giá trị
  hợp lệ theo chính sách Analysis. Missing raw khác với unusable do chất lượng.
- Các thống kê là sample-weighted sau khử trùng slot, không phải duration-weighted
  hoặc mỗi trạm/ngày có trọng số bằng nhau. Nhịp lấy mẫu khác nhau ảnh hưởng trọng số;
  xem từng trạm/ngày và độ phủ khi diễn giải trung bình toàn bộ.
- Đếm độ phủ theo từng giai đoạn 30/5 phút và DST. Trước lần đầu theo dõi trạm
  không tự phạt là mất mẫu. Ngày đầu/cuối có thể chỉ là ngày một phần.
- Median và mode không thay NULL bằng 0. Mode có thể nhiều giá trị, tối đa 20 giá
  trị được liệt kê kèm mode_count/modes_truncated. Std population ddof=0 và std sample
  ddof=1 được phân biệt; std sample thiếu nếu chưa có hai mẫu.
- Outlier là cờ xem xét: IQR 1,5 cho từng trạm/đặc trưng có ít nhất 8 giá trị; trường
  hợp IQR=0 ghi zero_iqr_deviation. Thay đổi lớn >max(10 xe, 50% sức chứa) chỉ so hai
  slot liền kề. Không nối qua mẫu mất/không hợp lệ. Trạm hết xe có thể là sự kiện thật.
- Capacity chỉ là snapshot metadata hiện tại; cờ vượt capacity không khẳng định mẫu
  lịch sử sai. Muốn kết luận phải có lịch sử sức chứa hoặc kiểm tra nguồn gốc.
- Rain là mm theo interval nguồn, không phải tổng ngày. Không cộng các mẫu thời
  tiết tái sử dụng. Khi interval khác nhau, cần quy về cùng thời lượng để so sánh.
- Pearson tối thiểu 3 cặp hợp lệ, không xác định cho biến hằng số. Dữ liệu có tự
  tương quan thời gian, thời tiết lặp và khác biệt trạm; hệ số chỉ mang tính mô tả,
  không phải kiểm định độc lập hoặc bằng chứng quan hệ nhân quả.

## Chuẩn hóa và ML

So sánh Min-Max và StandardScaler/Z-score: chia timestamp khoảng 70/15/15, purge
mẫu sát ranh giới nếu t+30 phút vượt sang phần sau. Mỗi scaler chỉ fit giá trị hữu
hạn của train; thiếu dữ liệu giữ nguyên. Holdout có thể ngoài [0,1], không clip về
giới hạn để che khác biệt phân phối.

Đây là minh họa EDA, không tạo nhãn/lag hoàn chỉnh để huấn luyện và không thay model
hiện tại. IQR mô tả dùng cửa sổ EDA; nếu dùng loại ngoại lệ trong ML, phải fit ngưỡng
trên train riêng. Pipeline Prediction giữ cách ghép nhãn +30 phút, đánh giá thời gian
và baseline hiện có. Clustering vẫn có StandardScaler riêng.

Báo cáo mô tả toàn khoảng đã chọn. Khi dùng EDA để chọn đặc trưng hoặc ngưỡng cho
ML, giới hạn báo cáo vào giai đoạn train và giữ tập test riêng cho đánh giá cuối.

## Kiểm tra

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_eda.py -q
```

Fixture chỉ dùng trong SQLite/bộ nhớ thử nghiệm, không seed dữ liệu sản xuất.
Kiểm tra median/mode, NULL/0, khử trùng inactive, lịch hỗn hợp, không nối khoảng mất,
chuẩn hóa không nhìn holdout, lọc run chưa công bố, JSON không NaN và escape HTML.

Tham khảo: [pandas describe](https://pandas.pydata.org/docs/reference/api/pandas.DataFrame.describe.html),
[scikit-learn: tránh rò rỉ dữ liệu](https://scikit-learn.org/stable/common_pitfalls.html#data-leakage),
[seaborn heatmap](https://seaborn.pydata.org/generated/seaborn.heatmap.html).
# Ngôn ngữ hiển thị

Giao diện, báo cáo HTML và các biểu đồ xuất mới dùng tiếng Việt cho tiêu đề,
tên trục, chú giải và thuật ngữ thống kê. Biểu đồ theo thứ ghi Thứ Hai đến
Chủ nhật. Tên riêng trạm và đường phố giữ nguyên để tra cứu đúng địa điểm.
Tên trường trong JSON/CSV và cơ sở dữ liệu giữ nguyên để các dịch vụ tiếp tục
đọc được. Báo cáo cũ được giữ nguyên; tạo báo cáo mới để nhận biểu đồ tiếng Việt.


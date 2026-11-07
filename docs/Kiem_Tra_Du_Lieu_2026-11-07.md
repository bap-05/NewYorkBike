# Kiểm tra dữ liệu Aiven ngày 07/11/2026

Kết luận: dữ liệu đủ để bắt đầu phân tích, kiểm tra pipeline và chuẩn bị dataset
thử nghiệm. Chưa đủ lịch sử để kết luận chất lượng dự đoán hoặc ảnh hưởng thời
tiết ổn định. Không thay đổi/xóa dữ liệu và không gọi API để tạo thêm mẫu trong
lần kiểm tra này. Các truy vấn dùng MySQL session READ ONLY.

Thời điểm kiểm tra: 2026-11-07 13:13:25 UTC, tức 08:13:25 New York và 20:13:25
Asia/Bangkok. Kết quả dạng máy đọc: [data_audit_latest.json](data_audit_latest.json).

## Phạm vi và số lượng

| Chỉ tiêu | Kết quả |
| --- | --- |
| Kết nối | TLS, UTC +00:00 |
| Migration | 0003_bronze |
| Số trạm | 10 |
| Collection runs | 230: 228 success, 2 partial |
| Quan sát xe | 2.295: 2.294 valid, 1 inactive |
| Quan sát thời tiết | 2.274 |
| Liên kết xe–thời tiết | 2.294 |
| Thời gian đầu/cuối (New York) | 02/11 11:51:39 → 07/11 08:00:34 |
| Độ dài lịch sử | 4,84 ngày |
| Trung vị khoảng cách giữa hai lượt | 30 phút |
| Lượt mới nhất cách thời điểm kiểm tra | Khoảng 13 phút |

Năm trạm ban đầu có 230 mẫu/trạm; năm trạm bổ sung có 229 mẫu/trạm do bắt đầu từ
lượt thứ hai. Không coi phần lịch sử trước khi bổ sung trạm là lỗi thu thập của
trạm đó. Thời tiết có thể được nhiều quan sát xe dùng lại nên không cần số hàng
weather bằng số hàng bike.

## Chất lượng và các điểm cần xử lý

- Không thấy trùng khóa mẫu xe (source, station_id, sampled_at) hoặc khóa run.
- Không có số xe NULL/âm, không có số xe vượt capacity hiện tại trong lần kiểm tra.
- Không có liên kết thời tiết sai tọa độ so với metadata trạm hiện tại.
- Với các bản ghi đã liên kết: đủ bốn trường thời tiết, đơn vị đúng, interval dương,
  không có weather_time quá cũ hơn giới hạn cấu hình hoặc đi trước mẫu quá 60 giây.
- Không có source_observed_at bị thiếu hoặc đi trước collected_at quá 60 giây.
- Mỗi run đều có đường dẫn Bronze; chưa kiểm tra sự tồn tại/hash của artifact trên
  GitHub hoặc các bản tải về, nên đường dẫn không chứng minh raw còn truy cập được.

Hai lượt partial:

1. Run 52, ngày 03/11 lúc 13:30:43 New York: cả 10 mẫu xe valid, nhưng mẫu của trạm
   Kent St & McGuinness Blvd thiếu liên kết thời tiết. Giữ mẫu xe; khi xây dataset
   cần loại/đánh dấu hàng thiếu weather hoặc có chính sách xử lý thiếu rõ ràng.
2. Run 230, ngày 07/11 lúc 08:00:34 New York: trạm 8 Ave & W 49 St có is_renting=false
   và is_returning=false, được đánh dấu inactive; 9 trạm còn lại valid. Không coi
   trạm đó là trạm hoạt động bình thường và không tự đổi số xe thành 0.

Đây là kết quả tại thời điểm kiểm tra, không chứng minh trạm ngừng hoạt động mãi mãi.

## Độ liên tục theo ngày New York

| Ngày | Runs | Quan sát xe |
| --- | ---: | ---: |
| 02/11 | 24 | 235 |
| 03/11 | 48 | 480 |
| 04/11 | 46 | 460 |
| 05/11 | 47 | 470 |
| 06/11 | 48 | 480 |
| 07/11 đến 08:00 | 17 | 170 |

Ngày đầu/cuối không phải ngày đầy đủ. Từ ô nửa giờ chứa mẫu đầu đến ô chứa mẫu
cuối có 234 ô, 228 ô có ít nhất một mẫu, thiếu 6 ô: 02/11 12:00, 12:30, 13:30;
04/11 05:00, 06:00; 05/11 11:00. Ba ô ngày đầu thuộc giai đoạn thiết lập. Ba ô
04–05/11 là các khoảng thiếu đáng theo dõi sau khi đã thu thập đều.

Đây là kiểm tra độ phủ dữ liệu, gồm cả mẫu chạy bằng tay; không phải xác minh
log trigger cron-job.org/GitHub. Không tạo dữ liệu giả để lấp khoảng trống.

## Sẵn sàng cho bước tiếp theo

Có 2.219 cặp mẫu xe có thể ghép gần mốc +30 phút nếu chấp nhận sai số ±5 phút;
2.218 cặp có đủ weather hiện tại theo các kiểm tra trên. Chỉ là số đếm chẩn đoán,
chưa tạo dataset hoặc huấn luyện. Không gọi đây là nhãn đúng chính xác +30 phút.

Nên bắt đầu Data Analysis và xây quy tắc dataset:

- Ghép cùng source/trạm theo thời gian thật, giữ khoảng thiếu và loại inactive
  khỏi các mẫu dự đoán hoạt động bình thường.
- Chốt sai số nhãn thời gian được chấp nhận; không mặc định hàng kế tiếp là +30 phút.
- Khi đặt cutoff cho mô hình, xét collected_at/finished_at để chỉ dùng dữ liệu đã
  biết ở thời điểm dự đoán; weather_time trước cutoff chưa đủ chứng minh đã nhận
  được weather tại cutoff. Phép đếm cặp sơ bộ này chưa kiểm tra toàn bộ leakage.
- Chia train/test theo thời gian. Lịch sử chưa tròn một tuần và chưa có Chủ nhật,
  không đủ cơ sở đánh giá độ tổng quát theo tuần hoặc nhiều kiểu thời tiết.
- Tiếp tục thu thập, sao lưu Bronze và theo dõi các lượt partial/mất mốc. Không
  cần xóa dữ liệu đã thu hoặc bắt đầu lại.

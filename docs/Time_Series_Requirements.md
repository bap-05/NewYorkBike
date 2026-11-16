# Đối chiếu yêu cầu chuỗi thời gian

## Các phần đã bổ sung

| Yêu cầu | Nơi xem trên web | Cách thực hiện |
|---|---|---|
| Biểu đồ đường ngày/tuần/tháng | Phân tích & phân nhóm → Khám phá dữ liệu → chọn biểu đồ | Ba cửa sổ nhìn lại 1, 7, 30 ngày theo giờ New York |
| Biểu đồ phân tán ngày/tuần/tháng | Cùng danh sách biểu đồ | Thời gian trên trục ngang, số xe trên trục dọc, chỉ điểm thật |
| Biểu đồ phân phối ngày/tuần/tháng | Cùng danh sách biểu đồ | Phân phối số xe trong từng cửa sổ, không coi mẫu thiếu là 0 |
| Xu hướng sau tổng hợp | Xu hướng sau tổng hợp tuần/tháng | Trung bình theo giờ → ngày → tuần/tháng; chỉ dùng kỳ hoàn tất có đủ độ phủ |
| Đường mùa vụ | Đường mùa vụ theo tuần | Chồng các đường Thứ Hai–Chủ nhật giữa các tuần hoàn chỉnh |
| Ma trận tương quan | Tương quan xe – thời tiết / từng trạm | Cặp dữ liệu hợp lệ, không suy diễn quan hệ nhân quả |
| Dự báo ngày mai | Dự đoán +30 phút → Dự báo và phân loại ngày mai | Dự báo số xe có thể thuê trung bình trong ngày lịch New York kế tiếp |
| Phân loại ngày mai | Cùng biểu đồ dự báo ngày mai | Ít xe / Mức trung bình / Nhiều xe theo tỷ lệ xe dự báo trên sức chứa |

Tổng cộng 12 hình khi có trạm và dữ liệu: chín hình đường/phân tán/phân phối,
một hình xu hướng, một hình mùa vụ và một ma trận tương quan.
Đã bỏ các hình ngoài yêu cầu khỏi giao diện và bộ tạo báo cáo mới: hộp/ngoại
lệ, so sánh chuẩn hóa, độ phủ, dữ liệu thiếu, nhịp giờ/thứ, tương quan riêng từng
trạm và các hình chuỗi/phân phối cũ trùng chức năng. Báo cáo lịch sử được giữ
để có thể đối chiếu, không tự xóa dữ liệu cũ.

### Chọn một ngày, tuần hoặc tháng cụ thể trên web

Với chín biểu đồ đường/phân tán/phân phối, chọn loại/phạm vi trong danh sách
Biểu đồ EDA rồi dùng ô **Ngày muốn xem / Tuần muốn xem / Tháng muốn xem**.
Có thể chọn một trạm hoặc toàn bộ trạm. Ngày, tuần ISO (Thứ Hai–Chủ nhật) và
tháng lịch đều tính theo New York, bao gồm ngày dài 23/25 giờ khi đổi giờ mùa.

Các biểu đồ này đọc trực tiếp dữ liệu đã công bố trong Aiven qua API chỉ đọc
`GET /api/eda/series?period=day|week|month&anchor=...&station_id=...`.
Định dạng kỳ: `YYYY-MM-DD`, `YYYY-Www`, `YYYY-MM`. Không chạy EDA hoặc gọi API
nguồn trong yêu cầu web. Kỳ hiện tại được cắt dữ liệu tại thời điểm đọc và báo
rõ chưa kết thúc; kỳ tương lai hoặc sai định dạng bị từ chối. Không có dữ liệu
thì báo trống, không tái dùng hình kỳ trước hoặc điền số 0.

Khử trùng theo mốc và giữ khoảng thiếu theo lịch thu đã khai báo. Chỉ mẫu xe
hợp lệ, lắp đặt và đang cho thuê mới có giá trị; các mẫu khác để trống. Truy vấn
giới hạn 100.000 hàng và 100 trạm; vượt giới hạn phải chọn một trạm/kỳ ngắn hơn.
Biểu đồ hiển thị toàn bộ điểm; đường thời gian không nối qua khoảng thiếu.

Ba biểu đồ còn lại và bảng thống kê vẫn lấy từ báo cáo EDA chụp tại thời điểm
tạo, không đổi theo ô chọn kỳ của các biểu đồ thời gian. Báo cáo HTML/PNG tải
ngoại tuyến vẫn được tạo bằng CLI như trước.
Một cửa sổ 30 ngày có thể chứa ít hơn 30 ngày quan sát nếu chưa thu thập đủ;
không kéo dài chuỗi bằng mẫu giả. Biểu đồ đường giữ khoảng trống khi mất mốc.
Phân phối vẫn là phân phối theo mẫu; sự thay đổi nhịp thu có thể thay đổi trọng
số trong biểu đồ này. Phần tổng hợp xu hướng/ngày mai sử dụng trọng số bằng
nhau giữa các giờ và giữa các ngày để giảm ảnh hưởng đó.

## Điều kiện và cách đọc xu hướng, mùa vụ

- Tuần lịch từ Thứ Hai đến Chủ nhật theo America/New_York. Tháng là tháng lịch.
- Ngày phải hoàn tất và đạt độ phủ từ 80%; kỳ tuần/tháng chỉ được công bố khi
  tất cả ngày trong kỳ đạt yêu cầu. Không điền kỳ thiếu bằng 0.
- Dùng xu hướng tháng khi có ít nhất ba tháng lịch hoàn chỉnh ở mọi trạm được
  chọn; nếu dữ liệu ngắn thì dùng tuần. Cần ít nhất hai kỳ hợp lệ để vẽ đường.
- Đường mùa vụ tuần so sánh trung bình ngày giữa ít nhất hai tuần hoàn chỉnh.
  Đây là đồ thị so sánh mẫu lặp theo lịch, **không phải** kết quả phân rã thống kê
  hoặc bằng chứng chắc chắn tồn tại mùa vụ.
- Khi thiếu kỳ, hình hiển thị lý do; mã đã có nhưng chưa thể có đường kết quả.
  Cần tiếp tục thu thập để quan sát đủ chu kỳ, không hạ chất lượng để có hình.

## Ý nghĩa dự báo và phân loại ngày mai

Mục tiêu bổ sung là **trung bình số xe có thể thuê của từng giờ ngày mai**, không phải
số xe tại một phút cụ thể hoặc số chuyến thuê. Mục tiêu +30 phút hiện tại vẫn
được giữ trong pipeline riêng và không đổi schema/database.

Mỗi giờ dùng trung bình của cùng giờ trong bảy ngày liền trước đã hoàn tất.
Mỗi ngày phải đạt độ phủ từ 80%; riêng giờ tương ứng phải có ít nhất 80% số
mẫu hợp lệ kỳ vọng theo lịch 30/5 phút. Cần ít nhất năm trong bảy ngày có giờ
đủ điều kiện để dự báo giờ đó. Không dùng trung bình cả ngày để lấp giờ thiếu.
Mẫu nguồn mới nhất phải hợp lệ, đang
cho thuê và không quá 600 giây tại mốc dữ liệu tạo báo cáo. Thiếu sức chứa hoặc
không đủ điều kiện thì giữ kết quả trống với lý do rõ ràng.

Phân loại bằng quy tắc đã công bố:

- Tỷ lệ số xe dự báo / sức chứa ≤20%: **Ít xe**.
- Tỷ lệ ≥80%: **Nhiều xe**.
- Khoảng giữa: **Mức trung bình**.

Đây là phân loại mức xe sẵn có dựa trên kết quả hồi quy cơ sở, chưa phải bộ
phân loại học máy đã huấn luyện. Không gọi đây là dự đoán nhu cầu cao/thấp.
Các trạm có thể cùng một lớp; không ép tạo các lớp khác nhau.
Sức chứa lấy thông tin hiện tại, chưa có tái dựng sức chứa lịch sử.
Mô hình này chưa sử dụng thời tiết tương lai và không thay thế đánh giá tác
động thời tiết của mô hình học máy +30 phút trong đề tài.

Ngày mục tiêu dùng khoảng nửa đêm–nửa đêm kế tiếp của New York, có 23, 24
hoặc 25 giờ. Duyệt giờ theo UTC, hiển thị độ lệch UTC để phân biệt hai giờ
cùng tên. Hai giờ lặp dùng chung mẫu lịch sử theo giờ địa phương, không giả
định có đủ dữ liệu để học riêng từng lần lặp.

Giao diện có chọn trạm, bộ chọn biểu đồ cột/đường/vùng theo từng giờ, bộ lọc chỉ xem giờ ít xe và phần tổng
hợp các giờ nguy cơ của mọi trạm. Ngưỡng phân loại giữ nguyên; không ép tạo
đủ ba lớp. Nếu chưa có giờ dưới ngưỡng nhưng vẫn còn giờ thiếu, giao diện
không kết luận cả ngày an toàn. Trung bình một giờ không bảo đảm luôn có xe
trong suốt giờ đó.

Kiểm thử tiến dần theo thời gian: mỗi ngày lịch sử chỉ được dùng bảy ngày trước
đó để dự báo; không dùng chính ngày mục tiêu để tính tham số. Công bố MAE, RMSE
và tỷ lệ phân loại đúng riêng từng giờ khi có ít nhất ba ngày kiểm thử cùng giờ. Các ngày chưa đủ lịch
sử hoặc độ phủ bị bỏ qua, không xem như dự báo đúng. Chưa thể biết sai số của
ngày mai trước khi ngày đó kết thúc.

## Cách cập nhật

Từ thư mục gốc, sau khi đã có phụ thuộc EDA và cấu hình Aiven:

```powershell
.\.venv\Scripts\python.exe -m eda.main --days 30
```

EDA chỉ đọc database và đóng kết nối trước khi tính biểu đồ. Dự báo ngày mai
được lưu trong báo cáo này: `summary.json`, `day_ahead_hourly.csv` và HTML.
Tệp tổng hợp cả ngày cũ còn được giữ để đọc tương thích, không dùng làm bảng
phân loại trên web.
API cung cấp các trường công khai qua `GET /api/eda`; không thực hiện huấn luyện
hoặc ghi dự báo vào MySQL khi mở website.

Khởi động lại FastAPI nếu đang dùng phiên bản chưa có trường `day_ahead`.
Vào trang Phân tích để xem hình, trang Dự đoán để xem ngày mai.
Nút Làm mới chỉ đọc báo cáo đã tạo; **không** tạo dự báo mới. Khi báo cáo không
còn có ngày mục tiêu là ngày mai hiện tại, web đánh dấu báo cáo cũ.

Phần bổ sung hiện chạy khi tạo báo cáo EDA, chưa có lịch tạo báo cáo hằng ngày
trên cloud. Không thêm lịch nền hoặc triển khai trong lần sửa này.

## Báo cáo và bảo vệ đề tài

Đã có tài liệu kỹ thuật và báo cáo khám phá dữ liệu; chúng chưa thay thế báo
cáo học phần hoàn chỉnh. Khi viết báo cáo cần có: bài toán và mục tiêu, kiến
trúc, nguồn và schema dữ liệu, chất lượng/độ phủ, phương pháp, thí nghiệm theo
thời gian, kết quả thật, giới hạn và hướng phát triển. Không ghi các kết quả
chưa đủ dữ liệu là đã kiểm chứng.

Chuẩn bị giải thích: vì sao lưu UTC nhưng hiển thị New York; vì sao thiếu khác
0; cách xử lý lỗi proxy; Bronze/Silver/Gold; sự khác nhau giữa phân nhóm và
phân loại; khác biệt +30 phút và trung bình ngày mai; lý do chia dữ liệu theo
thời gian và không dùng dữ liệu tương lai.

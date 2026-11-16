# Dự đoán 30 phút có thời tiết — bản thử nghiệm

Mô hình Random Forest dùng số xe hiện tại, số xe 30 phút trước, biến động số xe,
giờ, thứ, nhiệt độ, độ ẩm, mưa và tốc độ gió để dự đoán số xe có thể thuê sau 30 phút.
Đây là phần riêng với báo cáo dự báo từng giờ ngày mai.

## Kết quả đánh giá đang sử dụng

Báo cáo: `artifacts/prediction_weather/20261113T171903Z/report.json`.
Có 12.822 mẫu đầy đủ, trải trên 12 ngày hợp lệ. Ngưỡng huấn luyện chính thức vẫn là
14 ngày; người dùng đã chọn bật bản thử nghiệm và hiển thị đúng sai số.

Chia theo thời gian; chọn độ sâu bằng tập xác thực, không dùng tập kiểm thử để chọn.
Mô hình đăng ký là bản chỉ học trên tập huấn luyện của thí nghiệm, không học lại trên
các mẫu kiểm thử. Tập kiểm thử gồm 1.906 mẫu:

| Phương pháp | MAE (xe) | RMSE (xe) |
|---|---:|---:|
| Giữ nguyên số xe đầu vào | 0,888 | 1,507 |
| Random Forest có thời tiết | 1,486 | 2,190 |

Mô hình thời tiết hiện có sai số cao hơn mô hình cơ sở. Kết quả này được hiển thị
trên giao diện, cùng nhãn thử nghiệm; không thay bằng tỷ lệ chính xác tự quy đổi.
Mỗi lượt dự đoán được đối chiếu riêng khi có quan sát thực tế tại thời điểm mục tiêu.

## Chạy và đăng ký

Trong CMD, từ thư mục dự án:

```cmd
.venv\Scripts\python.exe -m scripts.evaluate_weather_prediction
.venv\Scripts\python.exe -m scripts.register_weather_trial --report artifacts/prediction_weather/20261113T171903Z --activate
.venv\Scripts\python.exe -m prediction.main --once
```

Thay đường dẫn báo cáo khi đánh giá lại. Bỏ `--activate` để chỉ đăng ký bản không hoạt động.
Mô hình và cấu hình nằm trong DB để dịch vụ trên GitHub đọc được, không cần file
mô hình trên máy chạy. Không huấn luyện lại trong mỗi lượt dự đoán.

Thời tiết phục vụ mô hình này phải là dữ liệu `open-meteo` thu trực tiếp với đúng
vị trí, đơn vị và độ mới. Không lấy ERA5 hoặc dự báo lịch sử vừa tải về làm thông
tin giả định đã biết tại thời điểm phát hành dự báo trong quá khứ.
Khi thiếu thời tiết hoặc mẫu trễ 30 phút, dịch vụ ghi rõ lý do dùng mô hình cơ sở;
mẫu xe không hợp lệ hoặc quá cũ không được công bố thành dự đoán hợp lệ.

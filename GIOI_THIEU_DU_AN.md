# Giới thiệu dự án NewYorkBike

**NewYorkBike** theo dõi và dự báo số xe có thể thuê tại 10 trạm Citi Bike ở New York. Hệ thống kết hợp trạng thái trạm từ Citi Bike GBFS với thời tiết từ Open-Meteo để xem diễn biến theo thời gian, so sánh các trạm và dự báo số xe sẵn có. Giao diện dùng tiếng Việt và hiển thị thời gian theo múi giờ New York.

Đơn vị chính trên biểu đồ là **số xe sẵn có tại trạm**. Đây là số xe người dùng có thể thuê tại thời điểm quan sát. Khi thiếu dữ liệu, giao diện thể hiện khoảng trống hoặc thông báo tương ứng.

## Mỗi trang dùng để làm gì?

| Trang | Đường dẫn | Chức năng |
| --- | --- | --- |
| **Tổng quan** | `/` | Xem nhanh số trạm theo dõi, tình trạng xe từ mẫu gần nhất, bản đồ và trạng thái các tác vụ xử lý dữ liệu. |
| **Bản đồ** | `/map` | Tìm và lọc trạm, chọn trạm trên bản đồ, xem số xe và chỗ trả, rồi mở trang chi tiết. |
| **Các trạm và chi tiết trạm** | `/stations`, `/stations/:stationId` | Chọn trạm để xem thông tin, số xe và chỗ trả, thời tiết tại tọa độ trạm và biểu đồ lịch sử số xe có thể thuê. |
| **Phân tích và phân nhóm** | `/analysis` | Xem thống kê và khám phá dữ liệu theo kỳ, bao gồm biểu đồ theo thời gian, xu hướng, mùa vụ, phân rã STL và tương quan. Phần phân nhóm cho biết các trạm có hành vi tương đồng, kèm bản đồ và thông tin nhóm. |
| **Dự báo** | `/predictions` | Xem dự báo từng giờ ngày mai, phân loại mức xe và đối chiếu với thực tế của ngày hôm qua. Phần bên dưới hiển thị dự báo sau 30 phút theo từng trạm. |
| **Lịch sử dự báo 30 phút** | `/predictions/:stationId/history` | Mở từ thẻ dự báo của một trạm để xem những lần dự báo đã công bố và đối chiếu với số xe thực tế khi đã có mẫu phù hợp. |

Trên trang **Dự báo**, bản đồ ngày mai luôn lấy danh sách trạm đang theo dõi. Có thể bấm ghim hoặc tìm theo tên để chọn trạm. Ghim được làm nổi bật và biểu đồ cập nhật theo trạm vừa chọn. Trạm thiếu dự báo vẫn chọn được và có thông báo riêng. Có thể đổi dạng biểu đồ cột, đường hoặc vùng và lọc chỉ xem giờ ít xe.

Các bản đồ có nút **+ / −** và hỗ trợ phóng to, thu nhỏ bằng con lăn khi con trỏ nằm trong vùng bản đồ.

## Đối chiếu với yêu cầu đồ án Time-series

NewYorkBike dùng dữ liệu số được thu thập theo thời gian. Phạm vi đối chiếu là nhóm **Time-series** trong slide. Nhóm **Text** áp dụng cho các đề tài dùng bài viết hoặc tin tuyển dụng.

| Yêu cầu | Phần đã triển khai | Nơi xem |
| --- | --- | --- |
| **1. Line, Scatter và Histogram cho ngày, tuần, tháng** | Có **9 tổ hợp**. Có thể chọn ngày, tuần ISO, tháng lịch và xem một trạm hoặc tất cả trạm. Line và Scatter đặt thời gian trên trục ngang. Histogram cho biết phân phối số xe trong kỳ đã chọn. Cả 9 tổ hợp đã được kiểm tra trên Chrome với bản Docker. | **Phân tích → Khám phá dữ liệu** |
| **2. Xu hướng sau khi tổng hợp lại** | Có xu hướng trung bình số xe theo tháng khi đủ tháng hoàn chỉnh, chuyển sang tuần khi lịch sử còn ngắn. Biểu đồ yêu cầu đủ số kỳ và độ phủ trước khi vẽ đường. | **Phân tích → Xu hướng sau tổng hợp** |
| **3. Đường mùa vụ** | Có đường mùa vụ **theo tuần**, so sánh trung bình từng ngày từ Thứ Hai đến Chủ nhật giữa các tuần hoàn chỉnh. Chế độ theo tháng còn thiếu. Phân rã STL theo trạm là biểu đồ bổ sung. | **Phân tích → Đường mùa vụ** |
| **4. Ma trận tương quan** | Có ma trận tương quan Pearson giữa các biến về xe và thời tiết, tính trên các cặp dữ liệu hợp lệ. | **Phân tích → Ma trận tương quan** |
| **5. Dự đoán ngày mai** | Có dự báo số xe có thể thuê trung bình của từng giờ ngày mai theo từng trạm. Kết quả được công bố vào database và đọc qua API. | **Dự báo → Dự báo và phân loại ngày mai** |
| **6. Phân loại ngày mai** | Có ba mức **Ít xe / Trung bình / Nhiều xe** dựa trên tỷ lệ số xe dự báo so với sức chứa. Từ 20% trở xuống là ít xe, từ 80% trở lên là nhiều xe, khoảng giữa là trung bình. Các giờ thiếu dữ liệu được hiển thị riêng. | **Dự báo → Dự báo và phân loại ngày mai** |

Các biểu đồ theo kỳ đọc dữ liệu qua `GET /api/eda/series`. Xu hướng, mùa vụ, phân rã STL và tương quan được vẽ trong trình duyệt từ JSON của `GET /api/eda/reports/{report_id}/chart-data`, có thể phóng to và xem giá trị trên biểu đồ. API đọc các bảng số liệu của báo cáo đã tạo trên máy chủ. Các file PNG vẫn phục vụ báo cáo ngoại tuyến. Dự báo ngày mai đọc bản đã công bố qua `GET /api/eda/day-ahead`.

## Hệ thống chạy như thế nào?

```text
Citi Bike + Open-Meteo → Data Ingestion → MySQL Aiven
                                         ↕
                            Analysis / Clustering / Prediction

MySQL Aiven → Database API → Frontend → Người dùng
```

| Container | Chức năng và lịch chạy |
| --- | --- |
| `frontend` | Phục vụ website React, vẽ bản đồ và biểu đồ từ dữ liệu API. |
| `database-api` | FastAPI cung cấp dữ liệu trạm và các kết quả đã lưu. Khi bật tự cập nhật EDA, tiến trình nền kiểm tra dữ liệu mỗi 15 phút để tạo báo cáo mới khi cần. |
| `data-ingestion` | Lấy trạng thái trạm và thời tiết, lưu dữ liệu gốc và dữ liệu chuẩn hóa. Chạy mỗi 5 phút. |
| `data-analysis` | Tính thống kê từ dữ liệu đã thu và lưu kết quả. Chạy mỗi 5 phút. |
| `clustering` | Phân nhóm hành vi của các trạm đủ điều kiện bằng StandardScaler và K-Means. Chạy hằng ngày lúc 02:00 theo giờ New York. |
| `prediction` | Dự báo sau 30 phút, kiểm tra phát hành dự báo ngày mai và đối chiếu với dữ liệu thực tế. Chạy mỗi 5 phút. |

**Backend xử lý** là các worker thu thập, phân tích, phân nhóm và dự báo. **Backend phục vụ giao diện** là Database API. Dữ liệu dùng chung nằm trên **MySQL Aiven**. Các lượt tự động chạy trong từng container. Các lệnh Run thủ công trên Swagger hiện thực thi tác vụ nền trong tiến trình Database API. Clustering chạy từ Swagger cần file model tương thích đã được xuất trước.

## Chạy và trình bày nhanh

Mở Docker Desktop. Trong thư mục `NewYorkBike`, cần có `.env` hợp lệ và chứng chỉ `certs/ca.pem` để kết nối Aiven. Docker tự cài phụ thuộc Python và Node.js trong quá trình build.

```powershell
docker compose up --build -d --wait
docker compose ps
```

- Mở [website](http://127.0.0.1:8080/) và [Swagger](http://127.0.0.1:8000/docs).
- Vào **Phân tích** để xem 9 tổ hợp biểu đồ, xu hướng, mùa vụ, tương quan và phân nhóm. Có thể mở F12, tab **Network**, để thấy request tải dữ liệu.
- Vào **Dự báo** để thử chọn trạm bằng bản đồ hoặc tìm kiếm, rồi xem kết quả theo từng giờ.
- Dùng `docker compose down` để xóa các container của dự án. Chạy lại lệnh `docker compose up --build -d --wait` để dựng lại. Dữ liệu database được lưu trên Aiven.

Đọc thêm [hướng dẫn cài đặt và vận hành](README.md), [báo cáo kỹ thuật](PROJECT_REPORT.md), [chi tiết các biểu đồ Time-series](docs/Time_Series_Requirements.md) và [hướng dẫn Swagger](docs/FastAPI.md).

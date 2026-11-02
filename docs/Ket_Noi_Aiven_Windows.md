# Kết nối MySQL Aiven từ Windows

Cập nhật ngày 02/11/2026. Đã kết nối Aiven của người dùng bằng TLS, nâng schema
lên 0003_bronze và chạy collector đúng một lần từ Windows: 5 trạm, 5 quan sát xe,
5 quan sát thời tiết và 5 liên kết, status=success, errors=0. Xem
[bằng chứng kiểm tra không chứa thông tin đăng nhập](aiven_verification.json).
Database đã nằm trên Aiven; collector vẫn chạy từ Windows, chưa phải triển khai
để thu thập khi tắt máy. Hướng dẫn Oracle không áp dụng nếu không có thẻ.

## 1. Lưu CA certificate

Trên trang service Aiven: Overview → Connection information → CA Certificate →
Download. Dùng phần kết nối MySQL, không phải MySQLx. Lưu chứng chỉ dưới tên
`aiven-ca.pem` trong thư mục `certs` của dự án.

PowerShell tại thư mục dự án:

```powershell
New-Item -ItemType Directory -Force .\certs | Out-Null
```

Đường dẫn cần có sau khi chép file:
`F:\126\Seoul Bike\certs\aiven-ca.pem`. Đây phải là nội dung PEM thật được tải
từ đúng project Aiven, không phải trang HTML. Không tạo chứng chỉ giả.
Thư mục certs đã được bỏ qua khi đưa mã lên Git.

Nguồn: [Aiven connection information và CA](https://aiven.io/docs/products/mysql/howto/connect-from-mysql-workbench),
[xác minh TLS](https://aiven.io/docs/platform/concepts/tls-ssl-certificates).

## 2. Điền .env riêng trên máy

Nếu collector Windows đang chạy, Ctrl+C để dừng trước khi đổi đích database.
Mở `.env`, chỉ sửa các dòng MySQL và thêm MYSQL_SSL_CA. Không chép đè toàn bộ
`.env` bằng `.env.example`, vì sẽ mất STATION_IDS/proxy riêng.

```dotenv
MYSQL_HOST=HOST_TU_AIVEN
MYSQL_PORT=PORT_TU_AIVEN
MYSQL_DATABASE=DATABASE_NAME_TU_AIVEN
MYSQL_USER=USER_TU_AIVEN
MYSQL_PASSWORD='MAT_KHAU_TU_AIVEN'
MYSQL_SSL_CA=certs/aiven-ca.pem
```

Thay tất cả placeholder bằng thông tin thật của service, không gửi chúng vào chat.
Host chỉ là hostname DNS, không thêm mysql://, https:// hay cổng phía sau.
Port lấy đúng từ Aiven, không mặc định 3306. Database dùng tên có sẵn trong Aiven
(ví dụ defaultdb nếu Console hiển thị như vậy), hoặc database bạn chủ động tạo.
Không dùng nguyên tên database cũ ở Windows nếu trên Aiven chưa có database đó.
Mật khẩu chứa ký tự đặc biệt cần được quote đúng cú pháp python-dotenv; không
percent-encode mật khẩu vì ứng dụng dùng các trường riêng, không dán connection URI.
Giữ nguyên các dòng STATION_IDS, OUTBOUND_PROXY_*, BIKE_SOURCE và múi giờ New York.

MYSQL_SSL_CA trống vẫn cho phép cấu hình MySQL local cũ. Với Aiven cần điền CA;
ứng dụng xác minh chuỗi chứng chỉ, hostname và kiểm tra kết nối đã mã hóa trước
khi dùng session. Không tắt xác minh để xử lý lỗi chứng chỉ.

## 3. Chỉ kiểm tra kết nối

Trong PowerShell tại thư mục dự án:

```powershell
.\.venv\Scripts\python -m scripts.check_database
```

Kết quả mong đợi, chưa phải kết quả đã chạy trên Aiven:

```text
MySQL connection: OK
Session timezone: +00:00
TLS: encrypted
CA and hostname verification: required
No migrations or application data writes performed.
```

Lệnh chỉ kiểm tra kết nối và cấu hình session UTC. Không tạo bảng, không ghi dữ
liệu quan sát và không gọi Citi Bike/Open-Meteo. Không in mật khẩu/connection URI.
Nếu lỗi: kiểm tra service đang chạy, DNS host, port, user/password, database name,
file CA và quy tắc mạng. Chỉ gửi dòng lỗi đã được script rút gọn, không gửi `.env`.

## 4. Bước tiếp theo khi kết nối thành công

Nếu database Aiven mới/trống và bạn muốn bắt đầu lịch sử mới:

```powershell
.\.venv\Scripts\python -m alembic upgrade head
.\.venv\Scripts\python -m alembic current
.\.venv\Scripts\python -m ingestion.main --once
```

Đây là các lệnh **ghi lên Aiven**: tạo/nâng schema rồi thu thập thật một lần.
Nếu database đã có bảng/dữ liệu, kiểm tra trạng thái migration trước; không DROP,
TRUNCATE hoặc stamp tùy tiện. Dữ liệu MySQL Windows không tự chuyển sang Aiven.
Bronze của lần chạy trên Windows vẫn lưu trên Windows.

Đã chuẩn bị [workflow GitHub Actions](Deploy_GitHub_Actions_Aiven.md) chạy một lần
mỗi job và upload Bronze ra artifact. Chưa push hoặc kiểm tra trên runner thật.
Còn cần tạo repository, điền GitHub Secrets, thử thủ công rồi mới bật lịch.
Artifact mặc định giữ 7 ngày, phải sao lưu trước khi hết hạn. Không bật --schedule
trong GitHub Actions như một server chạy liên tục. Lịch GitHub có thể trễ/bỏ lượt,
không bảo đảm đúng phút 00/30.

## Kết quả thực tế ngày 02/11/2026

- Schema Aiven ban đầu trống; đã áp dụng 0001_ingestion → 0002_citibike → 0003_bronze.
- Đã sửa cấu hình session để giữ ANSI_QUOTES do SQLAlchemy đã nhận diện từ server.
- Lần migration đầu dừng ở 0002 vì Aiven yêu cầu bảng luôn có primary key. Đã sửa
  bước thay khóa chính thành một ALTER, cho phép tiếp tục từ phần đã áp dụng;
  không xóa bảng/dữ liệu, không tắt yêu cầu primary key của server.
- Collector gọi Citi Bike và Open-Meteo qua 3 tuyến proxy cấu hình sẵn, thành công
  một lần lúc 11:51:39-05:00 New York (16:51:39 UTC), run 1 trên Aiven.
- Kiểm tra đủ cột model, tọa độ thời tiết khớp trạm, không có mẫu xe trùng.
- Bronze gồm 8 body thật, đã xác minh SHA-256, vẫn nằm trên đĩa Windows. Chưa có
  nơi lưu Bronze trên cloud; đường dẫn manifest trong MySQL chưa đủ để đọc raw từ máy khác.
- 110 tests đạt trong lần kiểm tra Aiven này. Chưa bật lịch nền hoặc chạy GitHub
  Actions thật; workflow được chuẩn bị trong bước triển khai tiếp theo.

Database hiện đã có dữ liệu thử thành công, không cần tạo lại bảng hoặc xóa dữ liệu.

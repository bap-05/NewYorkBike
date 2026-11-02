# Chạy collector trên Oracle Always Free từ Windows

Hướng dẫn chuẩn bị ngày 02/11/2026. Chưa tạo VM, chưa deploy và chưa kiểm tra thực tế
trên Oracle. Mẫu bên dưới dành cho Ubuntu 24.04, user ubuntu, mã đặt ở
/home/ubuntu/citibike. Chỉ triển khai ingestion + MySQL + Bronze, chưa có website.

## 1. Điều kiện để miễn phí

Đăng ký tại [Oracle Cloud Free Tier](https://www.oracle.com/cloud/free/).
Oracle yêu cầu thẻ tín dụng hoặc thẻ ghi nợ được hỗ trợ để xác minh. Có thể có khoản
tạm giữ để kiểm tra thẻ. Tài khoản Free Tier không tự tính phí nếu chưa nâng cấp.
Tham khảo [FAQ chính thức](https://www.oracle.com/cloud/free/faq/).

Chọn VM trong home region và tài nguyên đủ điều kiện Always Free, không dựa vào
credits dùng thử. Có thể dùng A1 Flex 1 OCPU, 2 GB RAM, boot volume 50 GB nếu Console
xác nhận cấu hình nằm trong miễn phí. Hiện hạn mức A1 miễn phí là tổng 2 OCPU/12 GB
RAM, cùng hạn mức lưu trữ riêng. Oracle có thể hết suất hoặc thu hồi VM nhàn rỗi;
không có bảo đảm uptime. Xem [Always Free Resources](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm).

Nếu không có thẻ, không thể tạo VM miễn phí hoặc Console chỉ cho tài nguyên tính
phí, dừng ở bước này; không chọn gói trả phí để làm tiếp theo hướng dẫn miễn phí.
Một máy chủ do trường cấp cũng dùng được phần Ubuntu bên dưới mà không cần Oracle.

## 2. Tạo VM Ubuntu

Trong Console: Compute → Instances → Create instance.

- Tên: citibike-collector.
- Image: Ubuntu 24.04 phù hợp kiến trúc shape.
- Shape/dung lượng: cấu hình đủ điều kiện Always Free ở bước 1.
- Networking: public subnet có kết nối Internet, public IPv4 để SSH.
- Tải/lưu private SSH key ở máy Windows; không đưa key lên Git hoặc vào chat.
- Kiểm tra điều kiện miễn phí trên Console trước khi Create.

Theo [hướng dẫn tạo instance](https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/launchinginstance.htm).
Đảm bảo có thể kết nối SSH cổng 22 từ máy của bạn. MySQL dùng nội bộ, không cần mở
cổng 3306 ra Internet. Chép public IP của VM để dùng ở bước sau.

## 3. Đóng gói mã trên Windows

PowerShell, tại thư mục dự án:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\deploy\package-windows.ps1
```

Lệnh tạo citibike-deploy.tar.gz trong thư mục TEMP và kiểm tra danh sách file.
Không đóng gói .env, .venv, dữ liệu MySQL, Bronze hay SSH key. Không thay execution
policy chung của Windows. Archive này chỉ chứa code và cấu hình mẫu.

Đặt các biến sau bằng thông tin VM thật, không dán nguyên placeholder:

```powershell
$VmAddress = 'IP_PUBLIC_CUA_VM'
$PrivateKeyPath = 'C:\DUONG_DAN\private-key.key'
scp -i "$PrivateKeyPath" "$env:TEMP\citibike-deploy.tar.gz" "ubuntu@${VmAddress}:~/"
ssh -i "$PrivateKeyPath" "ubuntu@$VmAddress"
```

Ubuntu platform image dùng username ubuntu. [Hướng dẫn SSH chính thức](https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/connect-to-linux-instance.htm).
Sau lệnh ssh bạn đang gõ lệnh trên Linux, không còn trong terminal Windows.

## 4. Cài môi trường trên VM

Các lệnh sau chạy trong SSH Ubuntu:

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip mysql-server
sudo systemctl enable --now mysql
mkdir -p /home/ubuntu/citibike
tar -xzf /home/ubuntu/citibike-deploy.tar.gz -C /home/ubuntu/citibike
cd /home/ubuntu/citibike
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

MySQL cài theo [hướng dẫn Ubuntu](https://ubuntu.com/server/docs/how-to/databases/install-mysql/).
VM phải chạy được cả MySQL và Python; nếu thiếu RAM, kiểm tra resource trước khi bật service.

## 5. Tạo MySQL trên server

Đây là database **mới trên VM**; không thay đổi hoặc xóa database Windows hiện tại.
Nếu muốn chuyển toàn bộ lịch sử, xem bước 10 trước khi bật collector mới.

```bash
sudo mysql
```

Trong MySQL, thay MAT_KHAU_MOI_CUA_BAN bằng mật khẩu thật do bạn tự chọn:

```sql
CREATE DATABASE IF NOT EXISTS newyorkbike CHARACTER SET utf8mb4 COLLATE utf8mb4_bin;
CREATE USER 'citibike_app'@'127.0.0.1' IDENTIFIED BY 'MAT_KHAU_MOI_CUA_BAN';
GRANT ALL PRIVILEGES ON newyorkbike.* TO 'citibike_app'@'127.0.0.1';
EXIT;
```

Nếu user đã tồn tại, không tạo lại hay tự xóa user: dùng tài khoản đã có hoặc kiểm
tra cấu hình riêng. Đừng ghi mật khẩu vào source, service file hoặc tin nhắn chat.

## 6. Cấu hình .env của server

```bash
cd /home/ubuntu/citibike
cp .env.example .env
chmod 600 .env
nano .env
```

Chỉ dùng cp khi chưa có .env để tránh ghi đè cấu hình riêng. Điền:

```dotenv
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_DATABASE=newyorkbike
MYSQL_USER=citibike_app
MYSQL_PASSWORD=MAT_KHAU_MOI_CUA_BAN
BIKE_SOURCE=citibike
DISPLAY_TIMEZONE=America/New_York
BRONZE_DIR=data/bronze
```

Điền STATION_IDS bằng 5 mã thật đang dùng trên Windows. Giữ GBFS_DISCOVERY_URL và
OPEN_METEO_URL trong mẫu. Nếu tiếp tục dùng proxy, chép hai giá trị
OUTBOUND_PROXY_ENABLED và OUTBOUND_PROXY_URLS từ .env của bạn vào editor trên VM.
Không gửi toàn bộ .env lên chat. Ctrl+O → Enter để lưu, Ctrl+X để thoát nano.

Citi Bike/Open-Meteo công khai không cần API key. Miễn phí VM không tăng quota proxy:
gói Decodo của bạn vẫn có giới hạn dung lượng riêng. Muốn thử gọi trực tiếp, chủ động
đặt OUTBOUND_PROXY_ENABLED=false; chương trình không tự bỏ qua proxy khi proxy lỗi.

Database server mới chưa có bảng:

```bash
.venv/bin/python -m alembic upgrade head
.venv/bin/python -m alembic current
```

Nếu đã import database có alembic_version, chỉ upgrade head. Nếu có schema thủ công
chưa version, đọc README phần adopt legacy; không chạy tạo lại bảng, không DROP/TRUNCATE.

## 7. Chạy thử một lần

```bash
cd /home/ubuntu/citibike
.venv/bin/python -m ingestion.main --once
```

Cần thấy status=success, valid_bikes=5, errors=0 và một đường dẫn Bronze manifest.
Nếu lỗi, kiểm tra kết nối MySQL, schema, proxy và quyền ghi Bronze trước khi bật lịch.

Xem dữ liệu:

```bash
mysql -h 127.0.0.1 -u citibike_app -p newyorkbike
```

```sql
SELECT id, status, success_count, error_count, bronze_manifest_path
FROM collection_runs ORDER BY id DESC LIMIT 5;
EXIT;
```

Thời gian log theo America/New_York, tự xử lý DST; database/Bronze vẫn dùng UTC.

## 8. Bật tiến trình chạy nền

Sau khi test server thành công, dừng collector đang chạy trên Windows bằng Ctrl+C.
Không chạy thêm lệnh --schedule thủ công trong SSH song song với service.

Mẫu service đã có trong deploy/citibike-ingestion.service:

```bash
sudo cp deploy/citibike-ingestion.service /etc/systemd/system/citibike-ingestion.service
sudo systemctl daemon-reload
sudo systemctl enable --now citibike-ingestion
sudo systemctl status citibike-ingestion --no-pager
journalctl -u citibike-ingestion -n 30 -o cat
```

Service dùng /home/ubuntu/citibike/.venv/bin/python và tự đọc .env trong project.
Chạy ngay khi khởi động, sau đó phút 00/30 New York, tự khởi động cùng VM và thử
khởi động lại khi tiến trình lỗi. systemd là trình quản lý tiến trình:
[tài liệu systemd.service](https://freedesktop.org/software/systemd/man/latest/systemd.service.html).

Nếu dùng user/thư mục khác, sửa User, Group, WorkingDirectory và ExecStart trong
service trước khi cài. --once ở bước 7 và service khởi động ở giây khác là hai lần
thu thập riêng; đây là hành vi lấy ngay khi chạy, không phải lỗi duplicate.

## 9. Kiểm tra rồi tắt laptop

Theo dõi log:

```bash
journalctl -u citibike-ingestion -f -o cat
```

Thấy Next collection và ít nhất một lần định kỳ thành công. Ctrl+C tại đây chỉ thoát
trình xem log, không dừng service. Gõ exit để đóng SSH; bạn có thể tắt Windows.
Sau đó kết nối SSH lại để kiểm tra run mới tiếp tục xuất hiện.

Các lệnh quản lý trên server:

```bash
sudo systemctl restart citibike-ingestion
sudo systemctl stop citibike-ingestion
sudo systemctl disable citibike-ingestion
df -h
du -sh /home/ubuntu/citibike/data/bronze
```

stop dừng hiện tại; disable bỏ tự chạy sau reboot. Không dùng các lệnh này để xóa
dữ liệu. MySQL và Bronze lưu trên đĩa VM, không phải thư mục tạm. Sao lưu chúng về
nơi khác trước khi thay/xóa VM; miễn phí không đồng nghĩa dữ liệu được bảo đảm mãi mãi.

## 10. Nếu muốn chuyển cả lịch sử Windows

Hướng dẫn chính bắt đầu database mới trên VM. Dữ liệu Windows vẫn giữ nguyên.
Để có một lịch sử thống nhất, trước khi bật service:

1. Dừng collector Windows để cố định trạng thái.
2. Trong MySQL Workbench: Server → Data Export → chọn toàn bộ database newyorkbike,
   gồm cả alembic_version, xuất cấu trúc và dữ liệu vào một file SQL.
3. Chép file SQL và toàn bộ thư mục Bronze sang VM qua SCP, giữ nguyên đường dẫn
   tương đối dưới BRONZE_DIR. Không chỉ chuyển SQL vì manifest còn trỏ đến raw.
4. Import vào database server mới/trống trước khi migration/chạy thử. Không import
   chồng lên database server đã có run mới vì ID và lịch sử có thể xung đột.
5. Chạy alembic current/upgrade head, kiểm tra manifest và số dòng rồi mới bật service.

Các bước này chưa được thực hiện tự động. Nếu server đã có dữ liệu, cần kế hoạch
hợp nhất riêng; không DROP/TRUNCATE hoặc ghi đè để làm theo hướng dẫn nhanh.

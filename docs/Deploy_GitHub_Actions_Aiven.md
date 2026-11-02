# Thu thập khi tắt laptop: GitHub Actions + Aiven

Chuẩn bị ngày 03/11/2026 (Asia/Bangkok). Workflow đã có trong mã nguồn, chưa được
đẩy lên GitHub, chạy thử trên runner hoặc bật lịch. Đây là triển khai collector,
không phải triển khai website React/FastAPI hoặc các service Gold chưa hoàn thiện.

## Mô hình và giới hạn

GitHub runner → proxy → Citi Bike/Open-Meteo → MySQL Aiven (Silver).
Raw Bronze được tạo trên runner, rồi upload artifact mang tên
`citibike-bronze-RUN_ID-RUN_ATTEMPT`. Mỗi job chạy đúng một lần, không bật --schedule
trong runner. MySQL không nằm trong runner và không mất khi job kết thúc.

Runner tiêu chuẩn cho repository công khai được miễn phí compute; private repo
có hạn mức riêng. Artifact storage có quota riêng (GitHub Free hiện liệt kê 500 MB),
không phải bộ nhớ không giới hạn. Giữ ngân sách không phát sinh phí và kiểm tra
Billing/Usage trong tài khoản. [Billing chính thức](https://docs.github.com/en/billing/concepts/product-billing/github-actions).

Mẫu giữ artifact **7 ngày** để hạn chế dung lượng. Đây là bản lưu tạm ngoài máy,
chưa phải kho Bronze lưu vĩnh viễn. Phải sao lưu trước khi hết hạn; nếu không thể
sao lưu đều, chưa bật lịch lâu dài mà hãy cấu hình kho lưu trữ khác trước.
Không xóa Bronze cũ trên Windows. Retention của GitHub có thể chịu giới hạn của
repo/organization. [Artifact retention](https://docs.github.com/en/actions/tutorials/store-and-share-data).

Cron phút 00/30 UTC cũng là phút 00/30 ở New York cả mùa EST/EDT. Tuy nhiên GitHub
có thể trễ hoặc bỏ lượt; thời điểm mẫu là lúc job thực sự chạy, không giả làm dữ
liệu ở mốc đã lỡ. Schedule chỉ chạy trên default branch, và repo công khai không
có hoạt động 60 ngày có thể bị tắt lịch. Không tự tạo commit giả để giữ lịch sống.
[Quy tắc schedule](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).

## 1. Tạo repository mới

1. Đăng nhập GitHub, chọn dấu + → New repository.
2. Đặt tên, ví dụ `citibike-prediction`.
3. Chọn Public nếu bạn đồng ý công khai mã để dùng compute miễn phí cho public
   repo. Người khác có thể đọc mã và dữ liệu artifact công khai theo quyền GitHub;
   mật khẩu/proxy chỉ nằm trong Secrets. Nếu cần giữ mã kín, chọn Private và kiểm
   tra hạn mức, không mặc định rằng chạy cả tháng sẽ miễn phí.
4. Tạo repo trống: không thêm README/.gitignore/license ở bước này vì local đã có.
5. Bấm Create repository, chép URL HTTPS thật của repo.

## 2. Đưa mã từ Windows lên GitHub

PowerShell tại `F:\126\Seoul Bike`. Các lệnh dưới dành cho thư mục chưa có Git.
Nếu đã là repository, giữ lịch sử/remote đang có, không khởi tạo hoặc thay remote lại.

```powershell
git init -b main
git add .github config ingestion shared database scripts deploy docs tests README.md requirements.txt alembic.ini .env.example .gitignore
git diff --cached --name-only
git check-ignore .env certs/aiven-ca.pem
```

Kiểm tra danh sách file đã stage: không có `.env` thật, `certs`, `data`, `backups`,
`.venv`, private key, password hay proxy credentials. `.env.example` là mẫu được
phép đưa lên. Không dùng GitHub Upload files để kéo cả thư mục dự án, vì thao tác
đó không tự áp dụng .gitignore như Git. Không đưa dump MySQL lên repo.

Sau khi kiểm tra, commit và push; thay URL placeholder bằng URL thật:

```powershell
git commit -m "Configure Citi Bike collection on GitHub Actions"
git remote add origin https://github.com/TEN_TAI_KHOAN/TEN_REPO.git
git push -u origin main
```

Git có thể mở trình duyệt để đăng nhập. Nếu yêu cầu user.name/user.email, điền
thông tin Git của bạn theo thông báo rồi commit lại. Không nhập mật khẩu hay token
vào URL remote, source hoặc chat. Chưa cần bật lịch ngay sau push.

## 3. Điền GitHub Secrets

Repo → Settings → Secrets and variables → Actions → tab Secrets → New repository
secret. Mỗi tên bên dưới là một secret riêng, phân biệt chữ hoa/chữ thường:

| Name | Secret value |
| --- | --- |
| MYSQL_HOST | Giá trị MYSQL_HOST trong .env Aiven đang kết nối thành công |
| MYSQL_PORT | Port Aiven thật, không mặc định 3306 |
| MYSQL_DATABASE | Tên database Aiven đã migration |
| MYSQL_USER | User Aiven |
| MYSQL_PASSWORD | Mật khẩu thật; không thêm dấu nháy bao ngoài như cú pháp .env |
| MYSQL_CA_CERT | Toàn bộ nội dung file certs/aiven-ca.pem |
| OUTBOUND_PROXY_URLS | JSON array proxy thật từ .env; không chép dấu nháy bao ngoài của dotenv |

Để lấy MYSQL_CA_CERT, mở file PEM bằng Notepad và chép cả khối từ
`-----BEGIN CERTIFICATE-----` đến `-----END CERTIFICATE-----`, gồm các dòng giữa.
Đây là **nội dung file**, không nhập chuỗi `certs/aiven-ca.pem`: runner không có
file chứng chỉ trên Windows. Workflow tạo file tạm, xác minh CA/hostname rồi xóa
file tạm. Không tạo secret MYSQL_SSL_CA; đường dẫn do runner tự thiết lập.

Không gửi ảnh có password/proxy URLs vào chat. Chưa cần thêm STATION_IDS:
`config/citibike_stations.json` đã có 10 ID thật, giữ 5 cũ và thêm 5 mới như local.
Nếu muốn danh sách khác, thêm repository Variable STATION_IDS dạng chuỗi ngăn
cách bằng dấu phẩy; đây là override cho cloud, không tự sửa .env Windows.

Mặc định workflow dùng proxy. Muốn chủ động chuyển sang gọi trực tiếp, thêm
repository Variable OUTBOUND_PROXY_ENABLED=false. Proxy lỗi không tự bỏ qua để
gọi trực tiếp. Quota Decodo không tăng khi chuyển sang GitHub.

## 4. Chạy thử thủ công trước

1. Chưa tạo Variable ENABLE_SCHEDULE hoặc để false.
2. Vào Actions → Citi Bike collection → Run workflow → chọn main → Run workflow.
3. Chờ job xong. Cần thấy `status=success`, `valid_bikes=10`, `errors=0`; nếu có trạm
   ngừng hoạt động hoặc lỗi API thì kiểm tra log thực tế, không tự giả định đủ 10.
4. Cần thấy bước Save Bronze thành công và artifact `citibike-bronze-...` ở cuối
   trang run. Bấm tải artifact, giải nén để kiểm tra manifest và file .body thật.
5. Kiểm tra Aiven có collection_runs mới, 10 bike observations và các liên kết
   weather tương ứng. Weather còn mới có thể được dùng lại, nên không mặc định
   phải tăng chính xác 10 weather rows mỗi lượt.

Job chỉ kiểm tra revision phải ở head, không tự chạy migration, tạo database hay
stamp. Aiven đã được nâng lên 0003_bronze trong lần kiểm tra trước. Nếu lệch schema,
dừng và nâng thủ công bằng mã đã kiểm tra. Nếu lỗi mạng/quyền: kiểm tra Aiven service
đang chạy, IP/network access và quyền user; IP GitHub runner khác IP Windows.
Không tắt TLS hoặc công khai credentials để xử lý lỗi kết nối.

Artifacts vẫn được upload sau lỗi collector thông thường để giữ raw và file
`github_collection.json`. Nếu runner bị hủy đột ngột, hết thời gian hoặc upload
lỗi, không bảo đảm raw đã lên GitHub dù Silver có thể đã commit. Đây là hai hệ
thống lưu trữ riêng; kiểm tra cả collector và upload đều thành công.

## 5. Bật lịch sau khi thử thành công

1. Dừng collector Windows bằng Ctrl+C để tránh hai nơi cùng ghi thêm mẫu.
2. Settings → Secrets and variables → Actions → tab Variables → New repository variable.
3. Name: ENABLE_SCHEDULE. Value: true.
4. Chờ lượt định kỳ, kiểm tra Actions và Aiven có bản ghi mới trước khi tắt máy.

Sau khi thiết lập, đóng trình duyệt/tắt laptop không dừng job trên GitHub. Mỗi ngày
thông thường có khoảng 48 lượt; lượt thủ công/retry là các lần khởi động riêng.
Chống chạy chồng bằng concurrency trong workflow và MySQL lock trong collector.
GitHub có thể thay lượt chờ khi có nhiều sự kiện; không bảo đảm đủ 48 mẫu/ngày.
Chưa triển khai tự backfill hoặc tự chạy lại dữ liệu realtime đã bỏ lỡ.

Muốn dừng, đổi ENABLE_SCHEDULE=false hoặc Actions → workflow → Disable workflow.
Đổi variable không dừng job đang chạy; nếu cần dừng ngay, Cancel run trong Actions.

## 6. Sao lưu Bronze trước 7 ngày

Không chỉ lưu đường dẫn manifest trong MySQL: raw nằm trong artifact theo từng
run GitHub. File github_collection.json nối GitHub run ID với các đường dẫn
manifest (và collection_run_id nằm trong manifest).

Có thể tải từng artifact ở trang run. Để tải hàng loạt, cài GitHub CLI chính thức
trên Windows, đăng nhập rồi chạy PowerShell tại thư mục dự án:

```powershell
gh auth login
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\backup_github_bronze.ps1 -Repository TEN_TAI_KHOAN/TEN_REPO
```

Thay OWNER/REPO bằng repo thật, không thêm URL. Lệnh tải các artifact Bronze chưa
hết hạn về `backups/bronze/ARTIFACT_ID/`, bỏ qua những artifact đã tải thành công.
Không xóa file local hoặc artifact GitHub. Lặp lại cách vài ngày, trước khi bất kỳ
artifact nào hết 7 ngày. Laptop có thể tắt giữa các lần sao lưu; nếu tắt quá lâu,
raw hết hạn không thể lấy lại chỉ từ Silver. Sao lưu tiếp sang ổ/cloud của bạn.

Sau giải nén/download, dưới thư mục artifact sẽ có `citibike/.../manifest.json`.
Ghép thư mục gốc artifact + bronze_manifest_path từ MySQL để tìm đúng file:

```powershell
.\.venv\Scripts\python -m scripts.inspect_bronze "DUONG_DAN_DAY_DU_TOI_MANIFEST_JSON"
```

Lần lấy weather được tái sử dụng có thể trỏ đến raw của run cũ; phải giữ cả artifact
của run cũ. Workflow không tự tải Bronze từ Windows lên GitHub; Bronze của các lượt
Windows trước đây vẫn cần được bạn sao lưu riêng. Không đổi ID/run provenance.

## Đã kiểm tra và chưa kiểm tra

- Đã kiểm tra orchestration bằng tests không dùng database/API thật; không tạo
  dữ liệu giả trong production. Đã kiểm tra cú pháp workflow bằng actionlint.
- Đã chuẩn bị cấu hình 10 trạm, kiểm tra CA, migration guard, một lần thu thập,
  giữ raw sau lỗi, tóm tắt không chứa bí mật, và xóa CA tạm.
- Chưa có repository/Secrets của người dùng, chưa push, chưa chạy runner thật,
  chưa bật lịch và chưa kiểm tra upload/download artifact thực tế.
- Script backup PowerShell được kiểm tra cú pháp; cần GitHub CLI, đăng nhập và
  artifact thật để xác minh toàn bộ. Không tuyên bố đã deploy thành công.

# Sai số của dự báo ngày mai

Trên trang **Dự đoán**, phần **Dự báo và phân loại ngày mai** có bảng **Sai số dự báo ngày mai**. Chọn trạm ở bộ lọc để đổi cả biểu đồ lẫn bảng sai số. Bộ lọc chỉ xem giờ ít xe chỉ áp dụng cho biểu đồ; bảng sai số vẫn giữ tất cả giờ để tránh che các khung giờ thiếu dữ liệu.

- **MAE:** trung bình độ lệch tuyệt đối giữa số xe dự báo và trung bình số xe thực tế trong giờ, đơn vị xe.
- **RMSE:** căn trung bình sai số bình phương, đơn vị xe; nhạy hơn với sai lệch lớn.
- **Phân loại đúng:** tỷ lệ dự báo đúng mức ít/trung bình/nhiều xe theo ngưỡng 20% và 80% sức chứa.
- **Số ngày kiểm thử:** chỉ tính ngày có dự báo lịch sử hợp lệ và trung bình giờ thực tế đạt chất lượng. Mỗi giờ cần ít nhất 3 ngày kiểm thử để công bố chỉ số; thiếu dữ liệu hiển thị dấu gạch ngang, không thay bằng 0.

Đây là **kiểm thử hồi cứu**, không phải sai số thực tế đã biết của ngày mai hay các dự báo đã phát hành. Với mục tiêu D, không dùng ngày phát hành D−1 đang chưa hoàn tất hoặc ngày D làm đầu vào. Phương pháp theo thứ lấy ít nhất hai ngày cùng thứ/cùng giờ trong lịch sử, ưu tiên tối đa bốn ngày gần nhất; phương pháp nhóm ngày lấy tối đa mười ngày cùng nhóm thường/cuối tuần, cần ít nhất ba ngày. Phương pháp 7 ngày dùng D−8 đến D−2, cần bảy ngày đạt chất lượng và ít nhất năm giờ tương ứng. Ngày và giờ đều cần độ phủ từ 80%.

Chọn phương pháp theo từng trạm trên cùng tập ngày/giờ có đáp án và các ứng viên đều dự báo được. Ngoài ba phương pháp theo lịch, có hai phương pháp điều chỉnh theo mức xe/xu hướng và đối chứng giữ nguyên mức xe gần nhất. Cần ít nhất sáu ngày so sánh. Dự báo hiện tại chọn bằng MAE trên ba ngày hoàn tất gần nhất. Kiểm thử cuốn chiếu trên nửa sau khoảng dữ liệu: mỗi mục tiêu D được chọn bằng ba ngày có đáp án trước ngày phát hành D−1; chỉ sau đó mới chấm đáp án D. Đáp án của một ngày kiểm thử đã hoàn tất có thể được dùng để chọn cho những lần phát hành sau, đúng với quá trình vận hành thực tế; không phải một tập kiểm thử tĩnh dùng lại để chọn tất cả mô hình. `selection_history` ghi lại các ngày xác thực của từng mục tiêu. Mỗi giờ chỉ công bố điểm nếu có ít nhất ba ngày kiểm thử hợp lệ.

Đặc trưng điều chỉnh gồm mức xe mới nhất, độ lệch ba giờ so với nhịp theo lịch, thay đổi độ lệch một giờ, xu hướng vài ngày và thay đổi so với tuần trước. Cửa sổ ba giờ cần độ phủ từ 80%; thiếu tham chiếu ngày/tuần được ghi rõ, không tạo số liệu giả. Kiểm thử tái dựng các đặc trưng tại cùng giờ địa phương của từng ngày phát hành, chỉ dùng timestamp/mốc thu không sau phát hành. Mẫu lỗi mới nhất chặn các đặc trưng gần đây thay vì lùi về mẫu hợp lệ cũ. Phần này là phương pháp thống kê thích nghi, không phải Random Forest thời tiết +30 phút; không tự huấn luyện mô hình thời tiết khi mở web.

Việc nhập lịch sử về sau cho phép đánh giá hồi cứu hành vi, không chứng minh hệ thống đã có các mẫu nhập đó ở thời điểm quá khứ. Kết quả trên web hiển thị rõ phương pháp thực tế của từng giờ và các ngày tham chiếu.

Các ô tổng hợp lấy trung bình MAE và tỷ lệ phân loại đúng có trọng số theo số mẫu từng giờ. RMSE tổng hợp bằng căn trung bình có trọng số của bình phương RMSE từng giờ, không lấy trung bình RMSE. Khi đổi giờ mùa thu, hai giờ trùng tên vẫn có dòng riêng theo UTC, nhưng không nhân đôi cùng nhóm kiểm thử trong phần tổng hợp.

Từ 16/11/2026, Prediction phát hành một bản mỗi ngày New York, lưu trong `luot_chay_dich_vu` với `ten_dich_vu='day_ahead'`. `tom_tat.report` giữ nguyên dự báo và thời điểm phát hành; `tom_tat.actual_evaluations` bổ sung kết quả thực tế sau đó. Không cần migration mới. `prediction.main --once`/`--schedule` đã tích hợp bước này; có thể dùng `--day-ahead` hoặc `--day-ahead-schedule` để chạy riêng, tránh tạo thêm lịch +30 phút.

Worker chỉ chấm sau khi toàn bộ giờ mục tiêu kết thúc và qua thời gian chờ thu thập; cần ít nhất 80% số mốc quan sát thật hợp lệ theo lịch thu đã lưu trong bản phát hành. Khử trùng từng mốc, ưu tiên quan sát nguồn chính và không bỏ qua mẫu lỗi mới nhất để lấy mẫu hợp lệ cũ. Không đủ mẫu thì giữ trạng thái chờ dữ liệu, không gán 0. Kết quả gồm trung bình thực tế trong giờ, sai số tuyệt đối/bình phương, phân loại đúng/sai theo sức chứa lúc phát hành, độ phủ, thời điểm chấm và ID các mẫu làm bằng chứng. Phát hành lặp không sửa dự báo gốc; chấm lặp không nhân đôi giờ đã chấm.

Web đọc bản đã lưu qua `/api/eda/day-ahead`; GET không chạy mô hình hoặc chấm điểm. Giao diện tải lại mỗi phút, tách phần **Sai số thực tế của dự báo đã lưu** khỏi **Kiểm thử lịch sử**. Khi chưa có bản mới hôm nay, vẫn xem được lịch sử đối chiếu. Sai số thực tế đầu tiên chỉ xuất hiện sau khi giờ mục tiêu kết thúc, khác với điểm kiểm thử hồi cứu đã có sẵn. Xem [tài liệu tổng hợp](../PROJECT_REPORT.md) để biết lệnh chạy và truy vấn kiểm tra.

Đường API hiện tại chỉ dùng quan sát thật đã công bố, gồm dữ liệu lưu trữ thật theo chính sách truy vấn; không gọi bộ nạp `citibike_estimated`. Các báo cáo EDA lịch sử có thể còn chứa thông tin về lần bù dữ liệu trước đây, nhưng không được dùng làm dự báo hiện tại trên web.

Kiểm thử tiến dần hiện tại vẫn dành cho phiên bản chỉ dùng dữ liệu thật; chưa dùng các dòng bù tạo về sau để giả lập rằng chúng đã tồn tại trong quá khứ. Không lấy nội suy hoặc trung vị ước lượng làm nhãn thực tế. Vì vậy kết quả có bù có thể được hiển thị trong khi phần sai số vẫn báo chưa đủ ngày kiểm thử; không được dùng sai số tham chiếu này để khẳng định chất lượng riêng của chế độ có bù thiếu.

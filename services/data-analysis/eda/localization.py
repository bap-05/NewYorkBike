"""Vietnamese presentation labels; data field names and station identities stay stable."""
FEATURE_LABELS = {
    'available_bikes': 'Xe có thể thuê', 'available_docks': 'Chỗ trả xe',
    'temperature': 'Nhiệt độ (°C)', 'humidity': 'Độ ẩm (%)',
    'rain': 'Mưa (mm/kỳ đo)', 'wind_speed': 'Tốc độ gió (m/s)',
}
WEEKDAYS = ['Thứ Hai', 'Thứ Ba', 'Thứ Tư', 'Thứ Năm', 'Thứ Sáu', 'Thứ Bảy', 'Chủ nhật']
TABLE_LABELS = {
    'uses_estimated_data': 'Có dùng dữ liệu ước lượng',
    'input_estimated_samples': 'Số mốc ước lượng trong đầu vào',
    'input_actual_samples': 'Số mẫu thật trong đầu vào',
    'actual_qualified_days': 'Số ngày đạt chuẩn chỉ với dữ liệu thật',
    'hour_label': 'Giờ New York (độ lệch UTC)', 'local_hour': 'Giờ địa phương',
    'history_days': 'Số ngày cùng giờ đủ dữ liệu',
    'status': 'Trạng thái', 'target_date': 'Ngày mục tiêu', 'target_start_utc': 'Bắt đầu ngày mục tiêu (UTC)',
    'target_end_utc': 'Kết thúc ngày mục tiêu (UTC)', 'input_cutoff_utc': 'Mốc dữ liệu đầu vào (UTC)',
    'capacity': 'Sức chứa', 'qualified_days': 'Số ngày đạt yêu cầu', 'predicted_mean_bikes': 'Số xe trung bình dự báo',
    'availability_class': 'Phân loại mức xe', 'evaluation_samples': 'Số ngày kiểm thử',
    'evaluation_status': 'Trạng thái kiểm thử', 'mae': 'Sai số tuyệt đối trung bình (xe)',
    'rmse': 'Căn sai số bình phương trung bình (xe)', 'classification_accuracy': 'Tỷ lệ phân loại đúng',
    'source': 'Nguồn dữ liệu', 'station_id': 'Mã trạm', 'station_name': 'Tên trạm',
    'column': 'Đặc trưng', 'count': 'Số mẫu', 'mean': 'Trung bình', 'median': 'Trung vị',
    'std_population': 'Độ lệch chuẩn tổng thể', 'std_sample': 'Độ lệch chuẩn mẫu',
    'mode_values': 'Giá trị xuất hiện nhiều nhất', 'mode_count': 'Số giá trị đồng tần suất',
    'min': 'Nhỏ nhất', 'max': 'Lớn nhất', 'raw_rows': 'Số quan sát ban đầu',
    'deduplicated_rows': 'Số quan sát sau khử trùng', 'duplicate_slot_rows': 'Số quan sát trùng mốc',
    'usable_bike_rows': 'Mẫu xe hợp lệ', 'inactive_rows': 'Mẫu ngừng cho thuê',
    'unusable_bike_rows': 'Mẫu xe không dùng được', 'missing_weather_link_rows': 'Mẫu thiếu liên kết thời tiết',
    'weather_unusable_rows': 'Mẫu thời tiết không dùng được',
    'usable_bikes_without_usable_weather': 'Mẫu xe thiếu thời tiết hợp lệ',
    'distinct_weather_observations': 'Số phép đo thời tiết khác nhau',
    'local_date': 'Ngày (giờ New York)', 'window_start_utc': 'Bắt đầu cửa sổ (UTC)',
    'window_end_utc': 'Kết thúc cửa sổ (UTC)', 'partial_day': 'Ngày chưa trọn vẹn',
    'expected_slots': 'Số mốc kỳ vọng', 'observed_slots': 'Số mốc đã thu', 'usable_slots': 'Số mốc hợp lệ',
    'missing_slots': 'Số mốc thiếu', 'coverage': 'Độ phủ', 'quality_status': 'Chất lượng',
    'observation_id': 'Mã quan sát', 'sampled_at': 'Thời điểm mẫu (UTC)',
    'sampled_at_local': 'Thời điểm mẫu (New York)', 'reason': 'Lý do đánh dấu',
    'value': 'Giá trị', 'lower_bound': 'Cận dưới', 'upper_bound': 'Cận trên', 'action': 'Cách xử lý',
    'outlier_flag_count': 'Số cờ cần xem xét', 'database_written': 'Đã ghi vào cơ sở dữ liệu',
    'training_count': 'Số giá trị huấn luyện', 'scale': 'Hệ số chuẩn hóa',
}
VALUE_LABELS = {
    'too_few_matching_hours': 'Chưa đủ 5 ngày có giờ tương ứng đạt độ phủ',
    'available': 'Có kết quả', 'insufficient_data': 'Chưa đủ dữ liệu',
    'low': 'Ít xe', 'balanced': 'Mức trung bình', 'high': 'Nhiều xe',
    'missing_capacity': 'Thiếu sức chứa hợp lệ', 'stale_observation': 'Mẫu nguồn quá cũ',
    'inactive_or_unusable_latest_observation': 'Mẫu mới nhất ngừng cho thuê hoặc không hợp lệ',
    'requires_seven_covered_completed_days': 'Cần 7 ngày liền trước hoàn tất, mỗi ngày đạt độ phủ từ 80%',
    'ALL': 'Tất cả các trạm', 'citibike': 'Citi Bike', 'seoul': 'Seoul Bike',
    'ok': 'Đạt yêu cầu', 'low_coverage': 'Độ phủ thấp', 'no_history': 'Chưa có lịch sử',
    'review_only_not_deleted': 'Chỉ xem xét, chưa xóa',
    'iqr_1_5': 'Ngoại lệ theo khoảng tứ phân vị (1,5 lần)',
    'zero_iqr_deviation': 'Khác mức phổ biến khi khoảng tứ phân vị bằng 0',
    'exceeds_current_capacity_snapshot': 'Vượt sức chứa hiện tại, cần kiểm tra',
    'negative_count': 'Số lượng âm', 'large_adjacent_change': 'Biến động lớn giữa hai mẫu liền kề',
    'train': 'Huấn luyện', 'validation': 'Xác thực', 'test': 'Kiểm thử',
    'purged_boundary': 'Loại ở ranh giới thời gian',
}


def column_label(name):
    if name.endswith('_missing_raw'):
        return f'{FEATURE_LABELS.get(name.removesuffix("_missing_raw"), name)}: thiếu dữ liệu gốc'
    if name.endswith('_unusable_pct'):
        return f'{FEATURE_LABELS.get(name.removesuffix("_unusable_pct"), name)}: không dùng được (%)'
    return TABLE_LABELS.get(name, name)

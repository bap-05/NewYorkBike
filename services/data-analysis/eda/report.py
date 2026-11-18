"""Write escaped, self-contained HTML navigation plus CSV/JSON/PNG artifacts."""
from datetime import date, datetime
from html import escape
import json

import numpy as np
import pandas as pd
from eda.localization import FEATURE_LABELS, TABLE_LABELS, VALUE_LABELS, column_label


def presentation_value(value):
    if isinstance(value, (bool, np.bool_)):
        return 'Có' if value else 'Không'
    if isinstance(value, str):
        return FEATURE_LABELS.get(value, VALUE_LABELS.get(value, value))
    return value


def presentation_table(data):
    """Translate a copy for HTML; exported data keeps stable field names."""
    shown = data.copy()
    for column in shown.columns:
        shown[column] = shown[column].map(presentation_value)
    shown = shown.rename(columns=column_label)
    return shown.to_html(index=False, escape=True, na_rep='—',
        float_format=lambda value: f'{value:.4g}', border=0)


def json_safe(value):
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, np.ndarray)):
        return [json_safe(item) for item in value]
    if isinstance(value, (float, np.floating)):
        return float(value) if np.isfinite(value) else None
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, (date, datetime, pd.Timestamp)):
        return value.isoformat()
    return value


def write_report(output, frame, tables, summary, figures):
    datasets = {
        'observations_audit.csv': frame,
        'descriptive_statistics.csv': tables['descriptive'],
        'missingness.csv': tables['missingness'], 'daily_coverage.csv': tables['coverage'],
        'outliers_review.csv': tables['outliers'], 'hourly_profiles.csv': tables['hour'],
        'weekday_profiles.csv': tables['weekday'], 'daily_profiles.csv': tables['day'],
        'scaling_comparison.csv': tables['scaled'],
    }
    for key in ('daily', 'weekly', 'monthly'):
        if key in tables:
            datasets[f'calendar_{key}.csv'] = tables[key]
    if 'decomposition' in tables:
        datasets['time_series_decomposition.csv'] = tables['decomposition']
    if 'day_ahead' in tables:
        datasets['day_ahead_forecast.csv'] = pd.DataFrame(tables['day_ahead']['items'])
        datasets['day_ahead_hourly.csv'] = pd.DataFrame([
            {'station_id': station['station_id'], 'station_name': station['station_name'],
             'target_date': station['target_date'], **hour}
            for station in tables['day_ahead']['items'] for hour in station.get('hourly_forecasts', [])])
    for name, data in datasets.items():
        data.to_csv(output / name, index=False, encoding='utf-8-sig', na_rep='')
    correlation_files = []
    for index, (station, result) in enumerate(tables['correlations'].items()):
        for kind, matrix in result.items():
            name = f'{kind}_{index:02d}.csv'
            matrix.to_csv(output / name, encoding='utf-8-sig', na_rep='')
            correlation_files.append({'station_id': station, 'kind': kind, 'file': name})
    summary['correlation_files'] = correlation_files
    summary['figures'] = figures
    summary['descriptive_statistics'] = tables['descriptive'].to_dict(orient='records')
    (output / 'summary.json').write_text(json.dumps(json_safe(summary), ensure_ascii=False,
        allow_nan=False, indent=2) + '\n', encoding='utf-8')

    def table(data):
        return presentation_table(data)
    links = ''.join(f'<li><a href="{escape(name, quote=True)}">{escape(name)}</a></li>' for name in datasets)
    corr_links = ''.join(f'<li>{escape(str(row["station_id"]))}: <a href="{row["file"]}">{row["kind"]}</a></li>' for row in correlation_files)
    images = ''.join(f'<figure><img loading="lazy" src="{figure["file"]}" alt="{escape(figure["title"], quote=True)}"><figcaption>{escape(figure["title"])}</figcaption></figure>' for figure in figures)
    scope = escape(f'{summary["window_start_local"]} → {summary["cutoff_local"]}')
    info = {key: summary[key] for key in ['source', 'raw_rows', 'deduplicated_rows',
        'usable_bike_rows', 'usable_bikes_without_usable_weather', 'outlier_flag_count', 'database_written']}
    info = {TABLE_LABELS[key]: presentation_value(value) for key, value in info.items()}
    scaling = tables['scaling_info']
    scaling_rows = pd.DataFrame([{'column': key, **{k: v for k, v in params.items()
        if k != 'status'}} for key, params in scaling.get('parameters', {}).items()])
    scaling_html = table(scaling_rows) if not scaling_rows.empty else '<p>Chưa đủ dữ liệu để so sánh chuẩn hóa.</p>'
    partition_text = ' · '.join(f'{VALUE_LABELS.get(key, key)}: {value}'
        for key, value in scaling.get('partition_counts', {}).items())
    hourly_export = datasets.get('day_ahead_hourly.csv', pd.DataFrame())
    day_ahead_html = table(hourly_export) if not hourly_export.empty else '<p>Chưa có dự báo từng giờ ngày mai.</p>'
    brief = tables['descriptive'][['station_id', 'column', 'count', 'mean', 'median', 'std_population',
        'mode_values', 'mode_count', 'min', 'max']]
    html = f'''<!doctype html><html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>NewYorkBike — Báo cáo EDA</title>
<style>body{{font:15px/1.8 system-ui,sans-serif;color:#243f3c;background:#f5f6f2;max-width:1250px;margin:auto;padding:35px}}
h1,h2{{color:#123b3a}}h1{{font-size:34px}}a{{color:#167c70}}section{{background:white;border:1px solid #e3e8df;padding:24px;border-radius:12px;margin:22px 0}}
.table{{overflow:auto;max-height:650px}}table{{border-collapse:collapse;width:100%;font-size:12px}}td,th{{padding:9px 12px;border-bottom:1px solid #e4e8e1;text-align:left;white-space:nowrap}}th{{background:#edf3e9;position:sticky;top:0}}
img{{width:100%;height:auto}}figure{{margin:25px 0}}figcaption{{font-size:12px;color:#6b8178}}pre{{white-space:pre-wrap;overflow-wrap:anywhere}}.note{{background:#f8f1df;padding:16px;border-radius:8px}}nav{{display:flex;gap:20px;flex-wrap:wrap}}
@media(max-width:650px){{body{{padding:15px}}section{{padding:15px}}h1{{font-size:27px}}}}</style></head><body>
<p>NEWYORKBIKE / EDA / DỮ LIỆU THẬT</p><h1>Khám phá dữ liệu trạm xe</h1><p>{scope}</p>
<nav><a href="#quality">Chất lượng</a><a href="#stats">Thống kê</a><a href="#charts">Biểu đồ</a><a href="#scaling">Chuẩn hóa</a><a href="#files">Tải CSV / JSON</a></nav>
<section><h2>Phạm vi và kết quả</h2><pre>{escape(json.dumps(info, ensure_ascii=False, indent=2))}</pre>
<p>Chỉ đọc cơ sở dữ liệu; không xóa dữ liệu, không ghi kết quả tổng hợp, không gọi nguồn hoặc huấn luyện mô hình học máy.</p>
<div class="note">Thống kê tính theo mẫu thật sau khử trùng mốc, không phải trung bình có trọng số thời lượng.
Hai nhịp 30/5 phút được xử lý theo lịch đã khai báo. Một số ngày đầu/cuối có thể chỉ là ngày một phần.
Sức chứa là thông tin trạm hiện tại, không phải lịch sử sức chứa tại từng mẫu.</div></section>
<section id="quality"><h2>1. Dữ liệu thiếu và chất lượng từng trạm</h2><div class="table">{table(tables['missingness'])}</div>
<h3>Độ phủ theo ngày New York</h3><div class="table">{table(tables['coverage'])}</div>
<p>Thiếu dữ liệu gốc là giá trị thực sự thiếu. Không dùng được là thiếu hoặc không đạt chính sách chất lượng/nguồn/đơn vị/tọa độ.
Không có thời tiết không làm mất mẫu xe khỏi thống kê xe. Các cột thời tiết dùng tập mẫu có thời tiết hợp lệ đầy đủ.</p></section>
<section id="stats"><h2>2. Trung bình, trung vị, độ lệch chuẩn và giá trị phổ biến</h2><div class="table">{table(brief)}</div>
<p>Bảng hiển thị độ lệch chuẩn tổng thể; tệp dữ liệu có thêm độ lệch chuẩn mẫu. Có thể có nhiều giá trị phổ biến cùng tần suất;
tệp dữ liệu ghi số giá trị đó và cờ rút gọn nếu quá 20 giá trị. Mã định danh, giờ và tọa độ không được coi là đặc trưng số để lấy trung bình.</p></section>
<section><h2>3. Ngoại lệ cần kiểm tra</h2><p>{summary['outlier_flag_count']} cờ, trên {summary['outlier_observation_count']} mẫu.
Một mẫu có thể có nhiều cờ. IQR 1,5 theo từng trạm/đặc trưng (tối thiểu 8 giá trị), vượt sức chứa hiện tại,
hoặc biến động lớn hơn max(10 xe, 50% sức chứa) giữa hai slot liền kề.</p>
<p>Hết xe, trạm đầy hoặc điều phối xe có thể là sự kiện thật; các cờ này không tự loại mẫu.
Khoảng tứ phân vị tính cho phân tích mô tả; nếu dùng lọc ngoại lệ khi huấn luyện phải tính ngưỡng chỉ trên tập huấn luyện.</p>
<div class="table">{table(tables['outliers'].head(200))}</div><p>Bảng xem tối đa 200 cờ; CSV chứa đầy đủ.</p></section>
<section id="charts"><h2>4. Chuỗi thời gian, phân phối và tương quan</h2><p>Biểu đồ để khoảng trống khi mất mẫu.
Bản đồ nhiệt dùng cặp quan sát hợp lệ, tối thiểu 3 cặp; cột hằng số có tương quan không xác định.
Tương quan không chứng minh nhân quả; xem theo từng trạm để giảm ảnh hưởng khác biệt sức chứa.
Thời tiết có thể được tái sử dụng, nên số cặp không đồng nghĩa số phép đo thời tiết độc lập.</p>{images}</section>
<section><h2>Đơn vị thời tiết</h2><p>Nhiệt độ °C, độ ẩm %, tốc độ gió m/s. Mưa giữ mm theo kỳ đo nguồn,
không phải tổng mưa cả ngày; xem weather_interval_seconds trong CSV. Không cộng các mẫu thời tiết được dùng lại.
Nếu so sánh lượng mưa có kỳ đo khác nhau cần đổi về cùng thời lượng trước.</p></section>
<section id="scaling"><h2>5. Chuẩn hóa nhỏ nhất–lớn nhất và điểm chuẩn</h2><div class="table">{scaling_html}</div><p>{escape(partition_text)}</p>
<p>Chia mốc thời gian khoảng 70/15/15; bỏ mẫu sát ranh giới có t+30 phút vượt sang tập sau.
Tham số chuẩn hóa chỉ tính từ các giá trị hữu hạn của tập huấn luyện; giữ thiếu dữ liệu, không điền 0. Giá trị ở tập xác thực và kiểm thử có thể ngoài [0,1].
Đây là minh họa tiền xử lý, không phải bộ dữ liệu đã sẵn sàng huấn luyện hoặc một mô hình mới.
Mô hình rừng ngẫu nhiên hiện tại không bị thay đổi; phần phân nhóm vẫn dùng bộ chuẩn hóa riêng.</p></section>
<section><h2>6. Dự báo và phân loại ngày mai</h2>
<p>Mục tiêu là số xe có thể thuê trung bình từng giờ ngày mai theo giờ New York, tách riêng dự đoán +30 phút.
Mỗi giờ lấy trung bình của cùng giờ trong 7 ngày liền trước hoàn tất, mỗi ngày đủ từ 80% mốc đầu vào.
Đầu vào dự báo ngày mai có thể bổ sung nguồn citibike_estimated vào mốc thiếu; các cột đánh dấu rõ số mẫu thật, mẫu bù và số ngày đạt chuẩn riêng của dữ liệu thật.
Mẫu bù không làm tăng độ phủ thật ở bảng chất lượng và không được dùng làm đáp án thực tế để chấm sai số.
Cần ít nhất 5 ngày có giờ tương ứng đạt độ phủ từ 80%; giờ thiếu không được thay bằng trung bình ngày hoặc số 0.
Ngày đổi giờ có 23 hoặc 25 giờ; giữ mốc UTC và độ lệch để phân biệt hai giờ cùng tên.
Phân loại theo tỷ lệ xe dự báo trên sức chứa hiện tại: ít xe từ 0 đến 20%, nhiều xe từ 80%, còn lại là mức trung bình.
Đây là quy tắc phân loại mức xe sẵn có, không phải nhu cầu chuyến đi hoặc mô hình học máy dùng thời tiết.
Kiểm thử tiến dần chỉ dùng dữ liệu thật và các ngày trước mục tiêu; cần ít nhất 3 ngày kiểm thử cùng giờ để công bố sai số.
Các sai số này là tham chiếu của phiên bản chỉ dùng dữ liệu thật, chưa đánh giá riêng phiên bản có bù thiếu.
Sức chứa dùng thông tin hiện tại, chưa tái dựng lịch sử thay đổi sức chứa.</p><div class="table">{day_ahead_html}</div></section>
<section id="files"><h2>7. Tệp xuất</h2><ul>{links}<li><a href="summary.json">summary.json</a></li></ul>
<details><summary>Ma trận tương quan và số cặp hợp lệ</summary><ul>{corr_links}</ul></details></section>
<p>Thời điểm tạo UTC: {escape(summary['generated_at_utc'])} · America/New_York · EDA v1</p></body></html>'''
    (output / 'report.html').write_text(html, encoding='utf-8')

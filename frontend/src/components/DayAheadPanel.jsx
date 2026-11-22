import { useState } from "react";
import { Search } from "lucide-react";
import { useApp } from "../App.jsx";
import { get } from "../lib/api.js";
import { number } from "../lib/data.js";
import { useResource } from "../lib/useResource.js";
import { Empty, Feedback, Panel } from "./UI.jsx";
import HourlyForecastChart from "./HourlyForecastChart.jsx";
import StationMap from "./StationMap.jsx";
import YesterdayForecastComparison from "./YesterdayForecastComparison.jsx";
import { usableForecast } from "../lib/hourlyForecast.js";

const reasons = {
  missing_capacity: "Chưa có sức chứa hợp lệ",
  inactive_or_unusable_latest_observation:
    "Trạm ngừng cho thuê hoặc mẫu mới nhất không hợp lệ",
  stale_observation: "Mẫu nguồn quá cũ tại thời điểm tạo báo cáo",
  requires_seven_covered_completed_days:
    "Cần 7 ngày liền trước hoàn tất, mỗi ngày đạt độ phủ từ 80%",
  too_few_matching_hours: "Chưa có ít nhất 5 ngày với giờ tương ứng đủ độ phủ",
  too_few_calendar_matches: "Chưa đủ lịch sử cùng thứ hoặc cùng nhóm ngày tại giờ này",
  recent_inputs_unavailable: "Mẫu gần nhất hoặc cửa sổ xu hướng chưa đạt chất lượng",
};

function tomorrowInNewYork() {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date());
  const part = (type) => Number(parts.find((p) => p.type === type).value);
  return new Date(Date.UTC(part("year"), part("month") - 1, part("day") + 1))
    .toISOString()
    .slice(0, 10);
}

export default function DayAheadPanel({ stations }) {
  const { revision, refresh } = useApp();
  const report = useResource(
    (signal) => get("/eda/day-ahead", signal, 60000),
    "day-ahead",
    revision,
  );
  const [stationId, setStationId] = useState("");
  const [query, setQuery] = useState("");
  const [onlyLow, setOnlyLow] = useState(false);
  const [chartType, setChartType] = useState("bar");
  const tomorrow = tomorrowInNewYork();
  const defaultId = report.data?.item?.day_ahead?.[0]?.station_id;
  const station = stations.find((row) => row.station_id === (stationId || defaultId)) || stations[0];
  const search = query.trim().toLowerCase();
  const matches = search
    ? stations.filter((row) => row.name.toLowerCase().includes(search))
    : stations;
  function selectStation(id) {
    setStationId(id);
    setQuery("");
  }
  return (
    <Panel
      className="day-ahead-panel"
      title="Dự báo và phân loại ngày mai"
    >
      <div className="forecast-station-picker">
        <div className="forecast-station-sidebar">
          <label className="forecast-search-label" htmlFor="forecast-station-search">
            Tìm trạm dự báo ngày mai
          </label>
          <div className="search-box">
            <Search size={16} aria-hidden="true" />
            <input id="forecast-station-search" type="search" value={query}
              onChange={(event) => setQuery(event.target.value)} placeholder="Nhập tên trạm" />
          </div>
          {matches.length ? (
            <ul className="forecast-station-results" aria-label="Các trạm dự báo">
              {matches.map((row) => (
                <li key={row.station_id}>
                  <button
                    type="button"
                    aria-pressed={row.station_id === station.station_id}
                    onClick={() => selectStation(row.station_id)}
                  >
                    {row.name}
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="forecast-search-empty" role="status">Không tìm thấy trạm phù hợp.</p>
          )}
          <p className="forecast-current-station" role="status">
            <span>Trạm đang xem</span>
            <strong>{station.name}</strong>
          </p>
        </div>
        <StationMap
          stations={stations}
          selected={station}
          compact
          onSelect={selectStation}
          focusSelected={Boolean(stationId)}
        />
      </div>
      <Feedback resource={report} retry={refresh}>
        {(data) => {
          const selected = data.item?.day_ahead?.find(
            (row) => row.station_id === station.station_id,
          );
          if (!selected?.hourly_forecasts?.length)
            return (
              <>
                <Empty title="Chưa có dự báo ngày mai cho trạm này">
                  Bạn có thể chọn trạm khác trên bản đồ hoặc trong danh sách.
                </Empty>
                {(data.history || []).map((station) => (
                  <details key={station.station_id} className="forecast-details">
                    <summary>Đối chiếu dự báo đã lưu · {station.station_name}</summary>
                    <YesterdayForecastComparison station={station} />
                  </details>
                ))}
              </>
            );
          const hours = selected.hourly_forecasts;
          const current = selected.target_date === tomorrow;
          const available = hours.filter(usableForecast);
          const low = hours.filter(
            (h) => h.status === "available" && h.availability_class === "low",
          );
          const missing = hours.filter((h) => h.status !== "available");
          const visible = onlyLow ? low : hours;
          return (
            <>
              <div className="toolbar forecast-chart-controls">
                <label>
                  Dạng biểu đồ dự báo
                  <select
                    aria-label="Dạng biểu đồ dự báo"
                    value={chartType}
                    onChange={(event) => setChartType(event.target.value)}
                  >
                    <option value="bar">Biểu đồ cột</option>
                    <option value="line">Biểu đồ đường</option>
                    <option value="area">Biểu đồ vùng</option>
                  </select>
                </label>
                <label className="hourly-risk-filter">
                  <input
                    type="checkbox"
                    checked={onlyLow}
                    onChange={(event) => setOnlyLow(event.target.checked)}
                  />{" "}
                  Chỉ xem giờ ít xe
                </label>
              </div>
              <div className="forecast-risk-summary" role="status">
                <strong>
                  {!available.length
                    ? "Chưa thể xác định giờ có nguy cơ ít xe."
                    : `${
                        current
                          ? "Giờ có nguy cơ ít xe"
                          : "Giờ ít xe trong báo cáo cũ"
                      }: ${number(low.length)}/${number(available.length)} giờ có dự báo.`}
                </strong>{" "}
                {!available.length
                  ? reasons[selected.reason] ||
                    "Các giờ chưa có dự báo đạt điều kiện."
                  : low.length
                    ? low.map((h) => h.hour_label).join("; ")
                    : missing.length
                      ? "Chưa thấy giờ ít xe trong các giờ có kết quả; còn giờ thiếu dữ liệu."
                      : "Không có giờ nào dưới ngưỡng ít xe theo phương pháp đã chọn."}
                {missing.length > 0 && (
                  <span>
                    {" "}
                    Có {number(missing.length)} giờ chưa đủ dữ liệu, không được
                    coi là an toàn.
                  </span>
                )}
                {selected.reason ===
                  "requires_seven_covered_completed_days" && (
                  <span>
                    {" "}
                    Số ngày đạt yêu cầu của trạm:{" "}
                    <strong>{number(selected.qualified_days)}/7</strong>.
                  </span>
                )}
              </div>
              <HourlyForecastChart
                key={selected.station_id}
                hours={visible}
                chartType={chartType}
                stationName={selected.station_name}
                capacity={selected.capacity}
                current={current}
                reasons={reasons}
              />
              <YesterdayForecastComparison station={selected} />
            </>
          );
        }}
      </Feedback>
    </Panel>
  );
}

import { useEffect, useState } from "react";
import { useApp } from "../App.jsx";
import { get } from "../lib/api.js";
import { number } from "../lib/data.js";
import { useResource } from "../lib/useResource.js";
import { Empty, Feedback, Panel } from "./UI.jsx";
import HourlyForecastChart from "./HourlyForecastChart.jsx";
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

export default function DayAheadPanel() {
  const { revision, refresh } = useApp();
  const [tick, setTick] = useState(0);
  useEffect(() => {
    const timer = setInterval(() => setTick((value) => value + 1), 60000);
    return () => clearInterval(timer);
  }, []);
  const report = useResource(
    (signal) => get("/eda/day-ahead", signal, 60000),
    "day-ahead",
    `${revision}:${tick}`,
  );
  const [stationId, setStationId] = useState("");
  const [onlyLow, setOnlyLow] = useState(false);
  const [chartType, setChartType] = useState("bar");
  const tomorrow = tomorrowInNewYork();
  return (
    <Panel
      className="day-ahead-panel"
      title="Dự báo và phân loại ngày mai"
    >
      <Feedback resource={report} retry={refresh}>
        {(data) => {
          const stations = data.item?.day_ahead || [];
          const selected =
            stations.find((r) => r.station_id === stationId) || stations[0];
          if (!selected?.hourly_forecasts?.length)
            return (
              <>
                <Empty title="Chưa có bản dự báo ngày mai được lưu hôm nay">
                  Dịch vụ Prediction cần chạy để phát hành dự báo mới. Web chỉ đọc bản đã lưu trong DB.
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
              <div className="toolbar">
                <label>
                  Trạm dự báo ngày mai
                  <select
                    aria-label="Trạm dự báo ngày mai"
                    value={selected.station_id}
                    onChange={(event) => setStationId(event.target.value)}
                  >
                    {stations.map((row) => (
                      <option value={row.station_id} key={row.station_id}>
                        {row.station_name}
                      </option>
                    ))}
                  </select>
                </label>
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

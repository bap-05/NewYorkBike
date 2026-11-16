import { useState } from "react";
import { number, percent } from "../lib/data.js";
import { forecastSegments, usableForecast } from "../lib/hourlyForecast.js";

const colors = { low: "#bd5840", balanced: "#167c70", high: "#436fad" };
const classes = { low: "Ít xe", balanced: "Mức trung bình", high: "Nhiều xe" };
const methods = {
  adaptive_recent: "Theo thứ/giờ, mức xe và xu hướng gần đây",
  adaptive_balanced: "Theo thứ/giờ, điều chỉnh thận trọng theo xu hướng",
  persistence: "Giữ nguyên số xe mới nhất",
  weekday: "Cùng thứ và cùng giờ",
  day_type: "Cùng nhóm ngày thường/cuối tuần và cùng giờ",
  seven_day: "Trung bình cùng giờ 7 ngày",
};

export default function HourlyForecastChart({
  hours,
  capacity,
  current,
  reasons,
  chartType = "bar",
  stationName,
}) {
  const [selectedKey, setSelectedKey] = useState(null);
  if (!hours.length) return null;
  const selected =
    hours.find((hour) => hour.target_start_utc === selectedKey) || hours[0];
  const usable = usableForecast;
  if (!hours.some(usable))
    return (
      <div className="hourly-forecast-chart">
        <h3>Xe dự báo trung bình theo giờ</h3>
        <p className="hourly-station-name">
          <strong>Trạm: {stationName}</strong>
        </p>
        <div className="subtle" role="status">
          <strong>Chưa có giờ nào đủ điều kiện để vẽ dự báo.</strong>{" "}
          {reasons[selected.reason] ||
            "Các giờ đang thiếu dữ liệu đạt chất lượng."}{" "}
          Chưa thể kết luận trạm ít hay nhiều xe vào ngày mục tiêu.
        </div>
      </div>
    );
  const max = Math.max(
    1,
    Number.isFinite(capacity) ? capacity : 0,
    ...hours.filter(usable).map((hour) => hour.predicted_mean_bikes),
  );
  const ceiling = Math.max(5, Math.ceil(max / 5) * 5);
  const width = Math.max(760, hours.length * 46 + 70);
  const step = (width - 80) / hours.length;
  const base = 250;
  const height = 200;
  const y = (value) => base - (value / ceiling) * height;
  const pointX = (index) => 60 + index * step + (step - 8) / 2;
  return (
    <div className="hourly-forecast-chart">
      <h3>Xe dự báo trung bình theo giờ</h3>
      <p className="hourly-station-name">
        <strong>Trạm: {stationName}</strong>
      </p>
      <div className="hourly-chart-legend">
        {Object.entries(classes).map(([key, label]) => (
          <span key={key}>
            <i className="dot" style={{ background: colors[key] }} />
            {label}
          </span>
        ))}
        <span>
          <i className="dot gray" />
          Chưa đủ dữ liệu (—)
        </span>
      </div>
      <div
        className="hourly-chart-scroll"
        tabIndex={0}
        role="region"
        aria-label="Cuộn biểu đồ dự báo từng giờ"
      >
        <svg
          className="hourly-forecast-svg"
          data-chart-type={chartType}
          viewBox={`0 0 ${width} 330`}
          style={{ width }}
          role="group"
          aria-label="Biểu đồ số xe trung bình dự báo theo giờ New York"
        >
          <text x="12" y="24">
            Số xe trung bình
          </text>
          {[0, 1, 2, 3, 4].map((tick) => {
            const value = (ceiling * tick) / 4;
            return (
              <g key={tick}>
                <line
                  x1="52"
                  x2={width - 15}
                  y1={y(value)}
                  y2={y(value)}
                  stroke="#dce5df"
                  strokeDasharray="4 4"
                />
                <text x="44" y={y(value) + 4} textAnchor="end">
                  {number(value)}
                </text>
              </g>
            );
          })}
          {chartType !== "bar" &&
            forecastSegments(hours).map((segment, index) => {
              const points = segment
                .map(
                  ({ hour, index: position }) =>
                    `${pointX(position)},${y(hour.predicted_mean_bikes)}`,
                )
                .join(" ");
              return (
                <g key={index} pointerEvents="none">
                  {chartType === "area" && segment.length > 1 && (
                    <polygon
                      className="hourly-value-area"
                      points={`${pointX(segment[0].index)},${base} ${points} ${pointX(segment.at(-1).index)},${base}`}
                      fill="#167c70"
                      fillOpacity="0.16"
                    />
                  )}
                  <polyline
                    className="hourly-value-line"
                    points={points}
                    fill="none"
                    stroke="#167c70"
                    strokeWidth="2.5"
                    strokeLinejoin="round"
                  />
                </g>
              );
            })}
          {hours.map((hour, index) => {
            const available = usable(hour);
            const value = available ? hour.predicted_mean_bikes : null;
            const x = 60 + index * step;
            const label = `${hour.hour_label}: ${available ? `${number(value)} xe · ${classes[hour.availability_class] || "Chưa phân loại"}` : "Chưa đủ dữ liệu"} · ${number(hour.history_days)} ngày hỗ trợ · ${methods[hour.forecast_method] || "Mô hình cơ sở"}`;
            const choose = () => setSelectedKey(hour.target_start_utc);
            return (
              <g
                key={hour.target_start_utc}
                className="hourly-forecast-column"
                role="button"
                tabIndex={0}
                aria-label={label}
                aria-pressed={
                  selected.target_start_utc === hour.target_start_utc
                }
                onClick={choose}
                onFocus={choose}
                onMouseEnter={choose}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    choose();
                  }
                }}
              >
                <title>{label}</title>
                <rect
                  x={x - 3}
                  y="35"
                  width={step - 2}
                  height="222"
                  rx="4"
                  fill={
                    selected.target_start_utc === hour.target_start_utc
                      ? "#edf3ee"
                      : "transparent"
                  }
                  fillOpacity={chartType === "bar" ? 1 : 0.45}
                />
                {available ? (
                  <>
                    {chartType === "bar" ? (
                      <rect
                        className="hourly-value-bar"
                        x={x + 3}
                        y={y(value)}
                        width={step - 14}
                        height={base - y(value)}
                        rx="3"
                        fill={colors[hour.availability_class] || "#8d969b"}
                      />
                    ) : (
                      <circle
                        className="hourly-value-point"
                        cx={pointX(index)}
                        cy={y(value)}
                        r="5"
                        fill={colors[hour.availability_class] || "#8d969b"}
                        stroke="white"
                        strokeWidth="1.5"
                      />
                    )}
                    {chartType === "bar" && value === 0 && (
                      <line
                        x1={x + 3}
                        x2={x + step - 11}
                        y1={base}
                        y2={base}
                        stroke={colors[hour.availability_class] || "#8d969b"}
                        strokeWidth="3"
                      />
                    )}
                  </>
                ) : (
                  <rect
                    x={x + 3}
                    y="65"
                    width={step - 14}
                    height="185"
                    fill="#f3f5f4"
                    stroke="#9ba9a2"
                    strokeDasharray="3 4"
                  />
                )}
                <text
                  x={x + (step - 8) / 2}
                  y={available ? y(value) - 8 : 158}
                  textAnchor="middle"
                  fontWeight="600"
                >
                  {number(value)}
                </text>
                <text x={x + (step - 8) / 2} y="276" textAnchor="middle">
                  {hour.hour_label.split(" ")[0]}
                </text>
                <text
                  x={x + (step - 8) / 2}
                  y="294"
                  textAnchor="middle"
                  className="hourly-offset"
                >
                  {hour.hour_label.slice(hour.hour_label.indexOf(" ") + 1)}
                </text>
              </g>
            );
          })}
          <text x={width / 2} y="322" textAnchor="middle">
            Giờ New York (độ lệch UTC)
          </text>
        </svg>
      </div>
      <div className="hourly-selection" aria-live="polite" aria-atomic="true">
        <h4>
          {selected.hour_label} ·{" "}
          {usable(selected)
            ? `${number(selected.predicted_mean_bikes)} xe — ${classes[selected.availability_class] || "Chưa phân loại"}`
            : "Chưa đủ dữ liệu"}
        </h4>
        <p>
          <strong>Dữ liệu hỗ trợ:</strong>{" "}
          {selected.forecast_method === "persistence"
            ? "Mẫu xe hợp lệ mới nhất."
            : `${number(selected.history_days)} ngày có cùng khung giờ đạt chất lượng.`}
        </p>
        {methods[selected.forecast_method] && <p>Phương pháp giờ này: {methods[selected.forecast_method]}.</p>}
        {selected.support_dates?.length > 0 && (
          <p>Ngày tham chiếu: {selected.support_dates.join(", ")}.</p>
        )}
        {selected.forecast_method?.startsWith("adaptive_") && selected.recent_adjustment != null && (
          <p>
            Mức theo lịch: {number(selected.seasonal_bikes)} xe;
            điều chỉnh gần đây: {number(selected.recent_adjustment, 1)} xe.
          </p>
        )}
        {selected.uses_estimated_data && (
          <p>
            <strong>Có dữ liệu bù thiếu:</strong>{" "}
            {number(selected.input_actual_samples)} mẫu thật +{" "}
            {number(selected.input_estimated_samples)} mốc ước lượng trong lịch
            sử giờ này. Sai số kiểm thử bên dưới chỉ dành cho phiên bản dùng dữ
            liệu thật.
          </p>
        )}
        <p>
          {!usable(selected)
            ? reasons[selected.reason] || "Chưa đủ dữ liệu"
            : !current
              ? "Báo cáo cũ — mô hình cơ sở"
              : "Dự báo bằng mô hình cơ sở"}
        </p>
        {!current && !usable(selected) && <p>Báo cáo cũ.</p>}
        <p>
          {selected.evaluation_status === "available"
            ? `Kiểm thử lịch sử · ${number(selected.evaluation_samples)} ngày cùng giờ · Sai số tuyệt đối trung bình: ${number(selected.mae, 2)} xe · Căn sai số bình phương trung bình: ${number(selected.rmse, 2)} xe · Phân loại đúng: ${percent(selected.classification_accuracy)}`
            : "Chưa đủ 3 ngày kiểm thử cùng giờ để công bố sai số."}
        </p>
      </div>
    </div>
  );
}

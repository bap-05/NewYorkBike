import { useState } from "react";
import { useApp } from "../App.jsx";
import { get, query } from "../lib/api.js";
import { calendarDefault, chartSegments } from "../lib/calendar.js";
import { number, time } from "../lib/data.js";
import { useResource } from "../lib/useResource.js";
import { Empty, Feedback } from "./UI.jsx";

const periods = { day: "Ngày", week: "Tuần", month: "Tháng" };
const types = {
  line: "Đường thời gian",
  scatter: "Phân tán",
  histogram: "Phân phối",
};

export default function CalendarExplorer({ period, kind, stations }) {
  const { revision, refresh } = useApp();
  const [anchor, setAnchor] = useState(() => calendarDefault(period));
  const [station, setStation] = useState("ALL");
  const key = `${period}:${anchor}:${station}`;
  const result = useResource(
    (signal) =>
      anchor
        ? get(
            `/eda/series?${query({
              period,
              anchor,
              station_id: station === "ALL" ? undefined : station,
            })}`,
            signal,
          )
        : Promise.resolve(null),
    key,
    revision,
  );
  return (
    <div className="calendar-explorer">
      <div className="toolbar">
        <label>
          {periods[period]} muốn xem
          <input
            aria-label={`${periods[period]} muốn xem`}
            type={period === "day" ? "date" : period}
            value={anchor}
            max={calendarDefault(period)}
            onChange={(event) => setAnchor(event.target.value)}
          />
        </label>
        <label>
          Trạm trên biểu đồ
          <select
            aria-label="Trạm trên biểu đồ"
            value={station}
            onChange={(event) => setStation(event.target.value)}
          >
            <option value="ALL">Toàn bộ trạm</option>
            {stations.map((s) => (
              <option key={s.station_id} value={s.station_id}>
                {s.name}
              </option>
            ))}
          </select>
        </label>
      </div>
      {!anchor ? (
        <Empty title="Chọn kỳ muốn xem" />
      ) : (
        <Feedback resource={result} retry={refresh}>
          {(data) =>
            data && (
              <>
                <p className="panel-footnote">
                  {types[kind]} · {periods[period]} {anchor} · Giờ New York.
                  <br />
                  Từ {time(data.range_start_utc)} đến {time(data.range_end_utc)}
                  .
                  {data.partial_period && (
                    <>
                      {" "}
                      Kỳ chưa kết thúc; dữ liệu đọc đến{" "}
                      {time(data.available_until_utc)}.
                    </>
                  )}{" "}
                  Đọc trực tiếp dữ liệu đã thu trong Aiven; không tạo lại báo
                  cáo ảnh.
                </p>
                {!data.items.some((s) => s.points.length) ? (
                  <Empty title="Chưa có dữ liệu trong kỳ đã chọn">
                    Thử ngày, tuần hoặc tháng khác. Khoảng chưa thu thập không
                    được điền số 0.
                  </Empty>
                ) : (
                  <div className="calendar-chart-grid">
                    {data.items.map((s) => (
                      <article className="calendar-chart" key={s.station_id}>
                        <h3>{s.name}</h3>
                        <SeriesChart station={s} data={data} kind={kind} />
                      </article>
                    ))}
                  </div>
                )}
              </>
            )
          }
        </Feedback>
      )}
    </div>
  );
}

function SeriesChart({ station, data, kind }) {
  const valid = station.points.filter((p) => Number.isFinite(p.value));
  if (!valid.length)
    return (
      <Empty title="Chưa có mẫu xe hợp lệ">
        Mẫu thiếu, ngừng cho thuê hoặc sai chất lượng được giữ trống.
      </Empty>
    );
  const first = Date.parse(data.range_start_utc),
    last = Date.parse(data.range_end_utc);
  const maxValue = valid.reduce((m, p) => Math.max(m, p.value), 1);
  const minValue = valid.reduce((m, p) => Math.min(m, p.value), Infinity);
  const x = (at) => 60 + ((Date.parse(at) - first) / (last - first)) * 700;
  const y = (value, maximum) => 222 - (value / maximum) * 185;
  const segments = chartSegments(station.points);
  const bins = Math.min(30, Math.ceil(Math.log2(valid.length) + 1));
  const width = (maxValue - minValue + 1) / bins;
  const counts = Array(bins).fill(0);
  for (const p of valid)
    counts[Math.min(bins - 1, Math.floor((p.value - minValue) / width))]++;
  const maxCount = Math.max(1, ...counts);
  const axisMax = kind === "histogram" ? maxCount : maxValue;
  const tooltipStride = Math.max(1, Math.ceil(valid.length / 300));
  return (
    <>
      <svg
        className="calendar-svg"
        viewBox="0 0 800 280"
        role="img"
        aria-label={`${types[kind]} ${station.name}, ${data.anchor}`}
      >
        {[0, 0.25, 0.5, 0.75, 1].map((part) => (
          <g key={part}>
            <line
              x1="60"
              x2="760"
              y1={y(part * axisMax, axisMax)}
              y2={y(part * axisMax, axisMax)}
              stroke="#dfe8e3"
            />
            <text x="50" y={y(part * axisMax, axisMax) + 4} textAnchor="end">
              {number(part * axisMax, 1)}
            </text>
          </g>
        ))}
        {kind === "line" &&
          segments.map((segment, i) => (
            <polyline
              key={i}
              points={segment
                .map((p) => `${x(p.at)},${y(p.value, maxValue)}`)
                .join(" ")}
              fill="none"
              stroke="#167c70"
              strokeWidth="2"
            />
          ))}
        {kind === "scatter" && (
          <path
            d={valid
              .map(
                (p) =>
                  `M${x(p.at).toFixed(1)},${y(p.value, maxValue).toFixed(1)}h2v2h-2z`,
              )
              .join(" ")}
            fill="#167c70"
            opacity=".7"
          />
        )}
        {kind !== "histogram" &&
          valid
            .filter((_, i) => i % tooltipStride === 0)
            .map((p) => (
              <circle
                key={p.at}
                cx={x(p.at)}
                cy={y(p.value, maxValue)}
                r="2"
                fill="#167c70"
              >
                <title>
                  {time(p.at)} · {number(p.value)} xe
                </title>
              </circle>
            ))}
        {kind === "histogram" &&
          counts.map((count, i) => (
            <rect
              key={i}
              x={60 + (i / bins) * 700}
              y={y(count, maxCount)}
              width={700 / bins - 1}
              height={222 - y(count, maxCount)}
              fill="#167c70"
            >
              <title>
                {number(minValue + i * width, 1)}–
                {number(minValue + (i + 1) * width, 1)} xe: {number(count)} mẫu
              </title>
            </rect>
          ))}
        {[0, 0.5, 1].map((part) => (
          <text
            key={part}
            x={60 + part * 700}
            y="250"
            textAnchor={part === 0 ? "start" : part === 1 ? "end" : "middle"}
          >
            {kind === "histogram"
              ? `${number(minValue + part * (maxValue - minValue + 1), 1)} xe`
              : time(new Date(first + part * (last - first)).toISOString())}
          </text>
        ))}
      </svg>
      <p className="panel-footnote">
        {number(valid.length)} mẫu hợp lệ / {number(station.points.length)} mốc
        · Trục dọc: {kind === "histogram" ? "số mẫu" : "số xe có thể thuê"}.
        {kind === "line" &&
          " Khoảng mất mẫu theo lịch 30/5 phút được ngắt, không nối bù."}
      </p>
    </>
  );
}

import ChartZoom from "./ChartZoom.jsx";
import { number, splitSegments, time } from "../lib/data.js";
import { Empty } from "./UI.jsx";

export default function LineChart({
  points,
  gapMinutes = 45,
  label = "Số xe",
  ceiling,
}) {
  const segments = splitSegments(points, gapMinutes * 60000);
  const valid = segments.flat();
  const hasEstimates = valid.some((p) => p.estimated);
  if (!valid.length) return <Empty title="Chưa đủ dữ liệu để vẽ biểu đồ" />;
  const allTimes = points.map((p) => Date.parse(p.at)).filter(Number.isFinite);
  const minT = Math.min(...allTimes),
    maxT = Math.max(...allTimes);
  const maxY = Math.max(1, ceiling || 0, ...valid.map((p) => p.value));
  const x = (at) => 54 + ((Date.parse(at) - minT) / (maxT - minT || 1)) * 746;
  const y = (value) => 224 - (value / maxY) * 190;
  return (
    <div className="chart">
      <ChartZoom><svg
        viewBox="0 0 830 275"
        role="img"
        aria-label={`${label}. ${hasEstimates ? "Gồm mẫu thật và dữ liệu ước lượng bù thiếu; xem loại mẫu tại từng điểm." : "Chỉ hiển thị các mẫu thật; khoảng mất dữ liệu được ngắt."}`}
      >
        {[0, 0.25, 0.5, 0.75, 1].map((t) => (
          <g key={t}>
            <line
              x1="54"
              x2="800"
              y1={y(t * maxY)}
              y2={y(t * maxY)}
              stroke="#e4eae7"
              strokeDasharray="4 5"
            />
            <text x="40" y={y(t * maxY) + 4} textAnchor="end">
              {number(t * maxY, 1)}
            </text>
          </g>
        ))}
        {segments.map((segment, i) => (
          <g key={i}>
            {segment.slice(1).map((p, j) => {
              const previous = segment[j];
              const estimated = p.estimated || previous.estimated;
              return (
                <line
                  key={j}
                  className={
                    estimated ? "estimated-segment" : "observed-segment"
                  }
                  x1={x(previous.at)}
                  y1={y(previous.value)}
                  x2={x(p.at)}
                  y2={y(p.value)}
                  stroke="#147d70"
                  strokeWidth="2.5"
                />
              );
            })}
            {segment.map((p, j) => (
              <circle key={j} cx={x(p.at)} cy={y(p.value)} r="3" fill="#147d70">
                <title>
                  {time(p.at)} · {number(p.value, 2)} ·{" "}
                  {p.estimated ? "Ước lượng bù thiếu" : "Mẫu thật"}
                </title>
              </circle>
            ))}
          </g>
        ))}
        {[minT, (minT + maxT) / 2, maxT].map((t, i) => (
          <text
            key={i}
            x={54 + i * 373}
            y="252"
            textAnchor={i === 0 ? "start" : i === 2 ? "end" : "middle"}
          >
            {time(new Date(t).toISOString())}
          </text>
        ))}
      </svg></ChartZoom>
      <p className="chart-note">
        Giờ New York · Di chuột vào điểm để xem mẫu ·{" "}
        {hasEstimates
          ? "Gồm mẫu thật và ước lượng bù thiếu; loại mẫu được ghi tại từng điểm."
          : "Khoảng thiếu dữ liệu được ngắt."}
      </p>
    </div>
  );
}

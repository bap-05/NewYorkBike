import { useState } from "react";
import ChartZoom from "./ChartZoom.jsx";
import { ExpandableChart } from "./ChartDialog.jsx";
import { number, splitSegments, time } from "../lib/data.js";
import { Empty } from "./UI.jsx";

export default function LineChart({
  points,
  gapMinutes = 45,
  label = "Số xe",
  ceiling,
  domain,
  inspect = false,
  expandable = false,
  unit = " xe",
}) {
  const [cursor, setCursor] = useState(null);
  const segments = splitSegments(points, gapMinutes * 60000);
  const valid = segments.flat();
  const hasEstimates = valid.some((p) => p.estimated);
  if (!valid.length) return <Empty title="Chưa đủ dữ liệu để vẽ biểu đồ" />;
  const allTimes = points.map((p) => Date.parse(p.at)).filter(Number.isFinite);
  const minT = Math.min(...allTimes),
    maxT = Math.max(...allTimes);
  const minY = domain?.[0] ?? Math.min(0, ...valid.map((p) => p.value));
  const maxY = domain?.[1] ?? Math.max(1, ceiling || 0, ...valid.map((p) => p.value));
  const x = (at) => 54 + ((Date.parse(at) - minT) / (maxT - minT || 1)) * 746;
  const y = (value) => 224 - ((value - minY) / (maxY - minY || 1)) * 190;
  const activeSegment = cursor === null ? null : segments.find(
    (segment) => cursor >= x(segment[0].at) - 4 && cursor <= x(segment.at(-1).at) + 4,
  );
  const active = activeSegment?.reduce((nearest, point) =>
    Math.abs(x(point.at) - cursor) < Math.abs(x(nearest.at) - cursor) ? point : nearest,
  );
  const cursorX = active ? x(active.at) : cursor;

  function inspectPoint(event) {
    const transform = event.currentTarget.getScreenCTM();
    if (!transform) return;
    const point = new DOMPoint(event.clientX, event.clientY).matrixTransform(transform.inverse());
    const inside = point.x >= 52 && point.x <= 802 && point.y >= 28 && point.y <= 226;
    setCursor(inside ? Math.min(800, Math.max(54, point.x)) : null);
  }
  const renderChart = (interactive) => (
      <svg
        viewBox="0 0 830 275"
        onPointerMove={interactive ? inspectPoint : undefined}
        onPointerDown={interactive ? inspectPoint : undefined}
        onPointerLeave={interactive ? (event) => {
          if (event.pointerType !== "touch") setCursor(null);
        } : undefined}
        role="img"
        aria-label={`${label}. ${hasEstimates ? "Gồm mẫu thật và dữ liệu ước lượng bù thiếu; xem loại mẫu tại từng điểm." : "Chỉ hiển thị các mẫu thật; khoảng mất dữ liệu được ngắt."}`}
      >
        {[0, 0.25, 0.5, 0.75, 1].map((t) => (
          <g key={t}>
            <line
              x1="54"
              x2="800"
              y1={y(minY + t * (maxY - minY))}
              y2={y(minY + t * (maxY - minY))}
              stroke="#e4eae7"
              strokeDasharray="4 5"
            />
            <text x="40" y={y(minY + t * (maxY - minY)) + 4} textAnchor="end">
              {number(minY + t * (maxY - minY), 1)}
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
        {interactive && (
          <rect x="54" y="30" width="746" height="194" fill="transparent" />
        )}
        {interactive && cursorX !== null && (
          <g className="station-chart-cursor" pointerEvents="none">
            <line x1={cursorX} x2={cursorX} y1="30" y2="224" />
            {active && <circle cx={cursorX} cy={y(active.value)} r="6" />}
          </g>
        )}
      </svg>
  );
  const reading = inspect && (
        <p className="station-chart-reading">
          {active
            ? <><strong>{number(active.value, 2)}{unit}</strong> · {time(active.at)}{active.estimated && " · Có dữ liệu ước lượng"}</>
            : cursor !== null
              ? "Không có mẫu tại khoảng thời gian này."
              : "Rê chuột hoặc chạm vào biểu đồ để xem số liệu."}
        </p>
  );
  return (
    <div className="chart">
      {expandable ? (
        <ExpandableChart title={label} renderChart={renderChart} reading={reading} onClose={() => setCursor(null)} />
      ) : (
        <>
          <ChartZoom>{renderChart(inspect)}</ChartZoom>
          {reading}
        </>
      )}
      <p className="chart-note">
        Giờ New York · {!inspect && "Di chuột vào điểm để xem mẫu · "}
        {hasEstimates
          ? "Gồm mẫu thật và ước lượng bù thiếu; loại mẫu được ghi tại từng điểm."
          : "Khoảng thiếu dữ liệu được ngắt."}
      </p>
    </div>
  );
}

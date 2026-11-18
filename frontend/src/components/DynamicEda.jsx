import { useMemo } from "react";
import { get } from "../lib/api.js";
import { useResource } from "../lib/useResource.js";
import { Empty, Feedback } from "./UI.jsx";
import ChartZoom from "./ChartZoom.jsx";

const colors = ["#167c70", "#3f6fb0", "#a66a32", "#8a63b8", "#b84f5d", "#49834c", "#666"];
const labels = { available_bikes: "Số xe", available_docks: "Chỗ trống", temperature: "Nhiệt độ", humidity: "Độ ẩm", rain: "Mưa", wind_speed: "Gió" };
const numeric = (value) => value === "" || value == null ? null : Number.isFinite(Number(value)) ? Number(value) : null;
const yes = (value) => String(value).toLowerCase() === "true";

export default function DynamicEda({ reportId, figure, stations, revision, refresh }) {
  const data = useResource((signal) => get(`/eda/reports/${encodeURIComponent(reportId)}/chart-data`, signal), reportId, revision);
  return <Feedback resource={data} retry={refresh}>{(tables) => <EdaGraph tables={tables} figure={figure} stations={stations} />}</Feedback>;
}

function EdaGraph({ tables, figure, stations }) {
  const name = figure.filename;
  const graph = useMemo(() => {
    if (name === "correlation_all.png") return { matrix: tables.correlation };
    if (name.startsWith("decomposition_")) {
      const rows = tables.decomposition.filter((row) => row.station_id === figure.station_id);
      return { panels: ["observed", "trend", "seasonal", "residual"].map((key, i) => ({ title: ["Chuỗi gốc", "Xu hướng", "Mùa vụ (24 giờ)", "Phần dư"][i], series: [{ label: key, points: rows.map((row) => [row.hour_utc, numeric(row[key])]) }] })) };
    }
    if (name === "weekly_seasonality.png") {
      const panels = stations.map((station) => {
        const weeks = tables.weekly.filter((row) => row.station_id === station.station_id && yes(row.complete)).map((row) => row.period);
        return { title: station.name, series: weeks.length < 2 ? [] : weeks.map((week) => ({ label: week, points: tables.daily.filter((row) => row.station_id === station.station_id && row.week === week).map((row) => [row.local_date, numeric(row.mean_bikes)]) })) };
      });
      // Map each week to the same weekday axis.
      panels.forEach((panel) => panel.series.forEach((series) => { series.points = series.points.map(([date, value]) => [String((new Date(date + "T00:00:00Z").getUTCDay() + 6) % 7), value]); }));
      return { panels, weekday: true };
    }
    const useMonth = stations.length > 0 && stations.every((station) => tables.monthly.filter((row) => row.station_id === station.station_id && yes(row.complete)).length >= 3);
    const rows = useMonth ? tables.monthly : tables.weekly;
    return { panels: stations.map((station) => ({ title: station.name, series: [{ label: useMonth ? "Tháng" : "Tuần", points: rows.filter((row) => row.station_id === station.station_id).map((row) => [row.period, numeric(row.mean_bikes)]) }] })) };
  }, [tables, name, figure.station_id, stations]);
  if (graph.matrix) return <Matrix rows={graph.matrix} />;
  return <div>{graph.panels.map((panel, index) => <section key={index}><h3>{panel.title}</h3><Plot series={panel.series} weekday={graph.weekday} /></section>)}</div>;
}

function Plot({ series, weekday }) {
  const all = series.flatMap((line) => line.points);
  const keys = [...new Set(all.map(([key]) => key))].sort();
  const values = all.map(([, value]) => value).filter((value) => value !== null);
  if (!values.length) return <Empty title="Chưa đủ dữ liệu để vẽ biểu đồ" />;
  const min = Math.min(0, ...values), max = Math.max(0, ...values), span = max - min || 1;
  const x = (key) => 65 + keys.indexOf(key) / Math.max(1, keys.length - 1) * 690;
  const y = (value) => 210 - (value - min) / span * 170;
  return <><ChartZoom><svg className="dynamic-chart" viewBox="0 0 800 270" role="img" aria-label="Biểu đồ tương tác">
    {[0, .25, .5, .75, 1].map((tick) => <g key={tick}><line x1="65" x2="755" y1={y(min + span * tick)} y2={y(min + span * tick)} stroke="#dfe8e3" /><text x="55" y={y(min + span * tick) + 4} textAnchor="end">{(min + span * tick).toFixed(1)}</text></g>)}
    {series.map((line, i) => <g key={line.label}>{line.points.map(([key, value], j) => value === null ? null : <g key={j}>{j > 0 && line.points[j - 1][1] !== null && <line x1={x(line.points[j - 1][0])} y1={y(line.points[j - 1][1])} x2={x(key)} y2={y(value)} stroke={colors[i % colors.length]} strokeWidth="2" />}<circle cx={x(key)} cy={y(value)} r="3" fill={colors[i % colors.length]}><title>{line.label} · {key} · {value.toFixed(2)}</title></circle></g>)}</g>)}
    {[0, .5, 1].map((v) => { const key = keys[Math.round((keys.length - 1) * v)]; return <text key={v} x={65 + 690 * v} y="235" textAnchor={v === 0 ? "start" : v === 1 ? "end" : "middle"}>{weekday ? ["T2", "T3", "T4", "T5", "T6", "T7", "CN"][Number(key)] : key}</text>; })}
  </svg></ChartZoom>{series.length > 1 && <div className="hourly-chart-legend">{series.map((line, i) => <span key={line.label}><i className="dot" style={{background: colors[i % colors.length]}} />{line.label}</span>)}</div>}</>;
}

function Matrix({ rows }) {
  if (!rows.length) return <Empty title="Chưa có dữ liệu tương quan" />;
  const columns = Object.keys(rows[0]).filter(Boolean);
  const cell = 72, left = 160, top = 125, size = left + columns.length * cell + 10;
  return <ChartZoom><svg className="dynamic-chart" viewBox={`0 0 ${size} ${top + rows.length * cell + 10}`} role="img" aria-label="Ma trận tương quan Pearson">
    {columns.map((column, i) => <text key={column} transform={`translate(${left + i * cell + 35},${top - 10}) rotate(-55)`}>{labels[column] || column}</text>)}
    {rows.map((row, i) => <g key={i}><text x={left - 8} y={top + i * cell + 40} textAnchor="end">{labels[row[""]] || row[""]}</text>{columns.map((column, j) => { const value = numeric(row[column]); const color = value === null ? "#f1f3f2" : value >= 0 ? `rgba(22,124,112,${Math.abs(value) * .75 + .1})` : `rgba(189,88,64,${Math.abs(value) * .75 + .1})`; return <g key={column}><rect x={left + j * cell} y={top + i * cell} width={cell - 1} height={cell - 1} fill={color}><title>{row[""]} / {column}: {value === null ? "-" : value.toFixed(2)}</title></rect><text x={left + j * cell + 35} y={top + i * cell + 40} textAnchor="middle">{value === null ? "-" : value.toFixed(2)}</text></g>; })}</g>)}
  </svg></ChartZoom>;
}

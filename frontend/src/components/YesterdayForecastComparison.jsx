import { number, time } from "../lib/data.js";
import { Empty, Table } from "./UI.jsx";

const newYorkDate = new Intl.DateTimeFormat("en-CA", {
  timeZone: "America/New_York", year: "numeric", month: "2-digit", day: "2-digit",
});

function localDate(value) {
  const parts = newYorkDate.formatToParts(new Date(value));
  const part = (kind) => parts.find((p) => p.type === kind).value;
  return `${part("year")}-${part("month")}-${part("day")}`;
}

export default function YesterdayForecastComparison({ station }) {
  const today = localDate(new Date());
  const yesterday = new Date(`${today}T12:00:00Z`);
  yesterday.setUTCDate(yesterday.getUTCDate() - 1);
  const date = yesterday.toISOString().slice(0, 10);
  const rows = (station.issued_evaluation?.items || [])
    .filter((row) => localDate(row.target_start_utc) === date)
    .sort((a, b) => a.target_start_utc.localeCompare(b.target_start_utc));

  return (
    <section className="day-ahead-issued-evaluation" aria-label="Chênh lệch dự báo hôm qua">
      <h3>Chênh lệch theo giờ hôm qua · {date} · {station.station_name}</h3>
      {!rows.length ? (
        <Empty title="Chưa có bản dự báo đã lưu cho ngày hôm qua" />
      ) : (
        <Table headers={["Giờ New York", "Xe dự báo", "Xe thực tế TB", "Chênh lệch (thực tế − dự báo)"]}>
          {rows.map((row) => {
            const predicted = Number.isFinite(row.predicted_bikes) ? Math.round(row.predicted_bikes) : null;
            const actual = row.status === "available" && Number.isFinite(row.actual_bikes)
              ? Math.round(row.actual_bikes) : null;
            const difference = actual !== null && predicted !== null ? actual - predicted : null;
            return (
              <tr key={`${row.publication_id}-${row.target_start_utc}`}>
                <td>{time(row.target_start_utc)}</td>
                <td>{number(predicted)}</td>
                <td>{number(actual)}</td>
                <td>{difference > 0 ? "+" : ""}{number(difference)}</td>
              </tr>
            );
          })}
        </Table>
      )}
    </section>
  );
}

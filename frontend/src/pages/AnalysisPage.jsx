import { useState } from "react";
import { useApp, RefreshButton } from "../App.jsx";
import { allPages } from "../lib/api.js";
import {
  analysisPoints,
  analysisWindows,
  defaultAnalysisRange,
  rangeBounds,
} from "../lib/analysisRange.js";
import { useResource } from "../lib/useResource.js";
import { Empty, Feedback, PageTitle, Panel } from "../components/UI.jsx";
import LineChart from "../components/LineChart.jsx";
import EdaPanel from "../components/EdaPanel.jsx";

const metrics = {
  available_bikes_mean: "Số xe trung bình",
  available_bikes_stddev: "Độ lệch chuẩn số xe",
  mean_absolute_change: "Biến động giữa hai mẫu liền kề",
  empty_ratio: "Tỷ lệ hết xe",
  missing_weather_ratio: "Tỷ lệ thiếu thời tiết",
  missing_slot_ratio: "Tỷ lệ thiếu mẫu",
  temperature_bikes_correlation: "Tương quan nhiệt độ – số xe",
};
const periods = {
  hour: { label: "Giờ", input: "datetime-local", gapMinutes: 90 },
  day: { label: "Ngày", input: "date", gapMinutes: 25 * 60 },
  week: { label: "Tuần", input: "week", gapMinutes: 8 * 24 * 60 },
  month: { label: "Tháng", input: "month", gapMinutes: 32 * 24 * 60 },
};

export default function AnalysisPage() {
  const { stations, refresh } = useApp();
  return (
    <Feedback resource={stations} retry={refresh}>
      {(page) =>
        !page.items.length ? (
          <Empty />
        ) : (
          <AnalysisContent stations={page.items} />
        )
      }
    </Feedback>
  );
}

function AnalysisContent({ stations }) {
  const { revision, refresh } = useApp();
  const [stationId, setStationId] = useState(stations[0].station_id);
  const [aggregation, setAggregation] = useState("day");
  const [range, setRange] = useState(() => defaultAnalysisRange("day"));
  const [metric, setMetric] = useState("available_bikes_mean");
  const { first, last, error } = rangeBounds(aggregation, range);
  const resourceKey = `analysis:${stationId}:${aggregation}:${metric}:${range.start}:${range.end}`;
  const period = periods[aggregation];
  const grouped = aggregation === "week" || aggregation === "month";
  const analysis = useResource(
    async (signal) => {
      if (error) return [];
      const items = [];
      for (const window of analysisWindows(first, last)) {
        const page = await allPages(
          "/analysis",
          {
            station_id: stationId,
            aggregation: aggregation === "hour" ? "hour" : "day",
            metric_name: metric,
            ...window,
          },
          signal,
        );
        items.push(...page.items);
      }
      return analysisPoints(items, aggregation);
    },
    resourceKey,
    revision,
  );
  return (
    <>
      <PageTitle
        eyebrow="TỪ DỮ LIỆU ĐẾN GÓC NHÌN"
        title="Phân tích dữ liệu"
        description="Xem thống kê theo giờ và khám phá dữ liệu theo ngày, tuần, tháng tại New York."
      >
        <RefreshButton />
      </PageTitle>
      <EdaPanel stations={stations} />
      <div className="toolbar">
        <label>
          Trạm
          <select
            aria-label="Trạm phân tích"
            value={stationId}
            onChange={(e) => setStationId(e.target.value)}
          >
            {stations.map((s) => (
              <option key={s.station_id} value={s.station_id}>
                {s.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Tổng hợp
          <select
            aria-label="Tổng hợp"
            value={aggregation}
            onChange={(e) => {
              const next = e.target.value;
              setAggregation(next);
              setRange(defaultAnalysisRange(next));
            }}
          >
            {Object.entries(periods).map(([value, { label }]) => (
              <option key={value} value={value}>
                Theo {label.toLowerCase()}
              </option>
            ))}
          </select>
        </label>
        <label>
          Chỉ số
          <select
            aria-label="Chỉ số phân tích"
            value={metric}
            onChange={(e) => setMetric(e.target.value)}
          >
            {Object.entries(metrics).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </select>
        </label>
        {["start", "end"].map((edge) => (
          <label key={edge}>
            {edge === "start" ? "Từ" : "Đến"} {period.label.toLowerCase()}
            <input
              type={period.input}
              step={aggregation === "hour" ? 3600 : undefined}
              max={defaultAnalysisRange(aggregation).end}
              value={range[edge]}
              onChange={(event) => {
                const value = event.target.value;
                setRange((previous) => ({ ...previous, [edge]: value }));
              }}
            />
          </label>
        ))}
      </div>
      <Panel
        title={metrics[metric]}
        subtitle={
          grouped
            ? "Trung bình các chỉ số theo ngày đủ chất lượng trong từng kỳ · Giờ New York"
            : "Khoảng đã chọn bao gồm cả mốc kết thúc · Giờ New York"
        }
      >
        {error ? (
          <Empty title={error} />
        ) : (
          <Feedback resource={analysis} retry={refresh}>
            {(points) =>
              !points.length ? (
                <Empty title="Chưa có thống kê phù hợp" />
              ) : (
                <>
                  <LineChart
                    key={resourceKey}
                    label={metrics[metric]}
                    inspect
                    expandable
                    unit={metric === "available_bikes_mean" ? " xe" : ""}
                    gapMinutes={period.gapMinutes}
                    points={points}
                  />
                </>
              )
            }
          </Feedback>
        )}
      </Panel>
    </>
  );
}

import { useState } from "react";
import { useApp, RefreshButton } from "../App.jsx";
import { allPages, get } from "../lib/api.js";
import { number, reasons } from "../lib/data.js";
import { useResource } from "../lib/useResource.js";
import {
  Badge,
  Empty,
  Feedback,
  PageTitle,
  Panel,
} from "../components/UI.jsx";
import LineChart from "../components/LineChart.jsx";
import EdaPanel from "../components/EdaPanel.jsx";
import { ClusterVisual } from "../components/ClusterExplorer.jsx";

const metrics = {
  available_bikes_mean: "Số xe trung bình",
  available_bikes_stddev: "Độ lệch chuẩn số xe",
  mean_absolute_change: "Biến động giữa hai mẫu liền kề",
  empty_ratio: "Tỷ lệ hết xe",
  missing_weather_ratio: "Tỷ lệ thiếu thời tiết",
  missing_slot_ratio: "Tỷ lệ thiếu mẫu",
  temperature_bikes_correlation: "Tương quan nhiệt độ – số xe",
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
  const [metric, setMetric] = useState("available_bikes_mean");
  const analysis = useResource(
    (signal) =>
      allPages(
        "/analysis",
        { station_id: stationId, aggregation, metric_name: metric },
        signal,
      ),
    `analysis:${stationId}:${aggregation}:${metric}`,
    revision,
  );
  const clusters = useResource(
    (signal) => get("/clusters", signal),
    "clusters",
    revision,
  );
  return (
    <>
      <PageTitle
        eyebrow="TỪ DỮ LIỆU ĐẾN GÓC NHÌN"
        title="Hiểu nhịp vận hành."
        description="Thống kê theo giờ, ngày New York và nhóm trạm có hành vi tương đồng."
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
            onChange={(e) => setAggregation(e.target.value)}
          >
            <option value="day">Theo ngày</option>
            <option value="hour">Theo giờ</option>
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
      </div>
      <Panel
        title={metrics[metric]}
      >
        <Feedback resource={analysis} retry={refresh}>
          {(page) =>
            !page.items.length ? (
              <Empty title="Chưa có thống kê phù hợp" />
            ) : (
              <>
                <LineChart
                  label={metrics[metric]}
                  gapMinutes={aggregation === "day" ? 25 * 60 : 90}
                  points={page.items
                    .slice()
                    .reverse()
                    .map((r) => ({
                      at: r.window_start.utc,
                      value: r.quality_status === "ok" ? r.metric_value : null,
                      estimated: Boolean(r.dimensions?.uses_estimated_data),
                    }))}
                />

              </>
            )
          }
        </Feedback>
      </Panel>
      <Panel
        title="Nhóm trạm tương đồng"
      >
        <Feedback resource={clusters} retry={refresh}>
          {(data) => (
            <>
              {data.latest_attempt && (
                <div className="cluster-meta">
                  <Badge value={data.latest_attempt.status} />
                  <span>
                    Lượt mới nhất: {data.latest_attempt.run_date} ·{" "}
                    {number(data.latest_attempt.eligible_stations)} trạm đủ điều
                    kiện
                  </span>
                </div>
              )}
              {!data.latest_success ? (
                <Empty title="Chưa có nhóm trạm được công bố">
                  Lượt chạy hiện chưa tạo được nhóm hợp lệ. Cần đủ ngày, số mẫu
                  và độ phủ theo cấu hình; đủ số ngày chưa bảo đảm đạt chất
                  lượng.
                  {data.latest_attempt?.reason && (
                    <span className="reason-code">
                      Lý do:{" "}
                      {reasons[data.latest_attempt.reason] ||
                        "Chưa đủ điều kiện phân nhóm"}
                    </span>
                  )}
                </Empty>
              ) : (
                <ClusterMembers
                  run={data.latest_success}
                  stations={stations}
                  previous={data.latest_attempt?.id !== data.latest_success.id}
                />
              )}
            </>
          )}
        </Feedback>
      </Panel>
    </>
  );
}

function ClusterMembers({ run, stations, previous }) {
  const { revision, refresh } = useApp();
  const members = useResource(
    (signal) => allPages(`/clusters/${run.id}/stations`, {}, signal),
    `cluster-members:${run.id}`,
    revision,
  );
  return (
    <>
      {previous && (
        <div className="notice">
          Lượt mới nhất chưa có nhóm hợp lệ. Đang hiển thị kết quả thành công
          trước đó ngày {run.run_date}.
        </div>
      )}
      <div className="cluster-summary">
        <strong>{number(run.selected_k)} nhóm</strong>
        <span>Điểm tách nhóm: {number(run.silhouette, 3)}</span>
      </div>
      <Feedback resource={members} retry={refresh}>
        {(page) => (
          <>
            <ClusterVisual run={run} members={page.items} stations={stations} />

          </>
        )}
      </Feedback>
    </>
  );
}

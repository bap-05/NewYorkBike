import DynamicEda from "./DynamicEda.jsx";
import { useEffect, useState } from "react";
import { useApp } from "../App.jsx";
import { get } from "../lib/api.js";
import { number } from "../lib/data.js";
import { useResource } from "../lib/useResource.js";
import { Empty, Feedback, Panel } from "./UI.jsx";
import { requiredCharts } from "../lib/requiredCharts.js";
import CalendarExplorer from "./CalendarExplorer.jsx";

const figures = {
  "resampled_trend.png": "Xu hướng sau tổng hợp tuần/tháng",
  "weekly_seasonality.png": "Đường mùa vụ theo tuần",
  "correlation_all.png": "Ma trận tương quan giữa các biến",
};

function figureLabel(figure) {
  const match = /^(line|scatter|histogram)_(day|week|month)\.png$/.exec(
    figure.filename,
  );
  if (!match) return figures[figure.filename] || figure.title;
  const kind = {
    line: "Đường thời gian",
    scatter: "Phân tán",
    histogram: "Phân phối",
  };
  const period = { day: "ngày", week: "tuần", month: "tháng" };
  return `${kind[match[1]]} · Chọn ${period[match[2]]} cụ thể`;
}

export default function EdaPanel({ stations }) {
  const { revision, refresh } = useApp();
  const [tick, setTick] = useState(0);
  useEffect(() => {
    const timer = setInterval(() => setTick((value) => value + 1), 60000);
    return () => clearInterval(timer);
  }, []);
  const report = useResource(
    (signal) => get("/eda", signal),
    "eda",
    `${revision}:${tick}`,
  );
  const [selectedFigure, setSelectedFigure] = useState("line_day.png");
  const [decompositionStation, setDecompositionStation] = useState("");
  return (
    <Panel title="Khám phá dữ liệu (EDA)">
      <Feedback resource={report} retry={refresh}>
        {(data) => {
          if (!data.item)
            return (
              <Empty title="Chưa có báo cáo EDA trên máy chủ API">
                Báo cáo được tạo nền khi API chạy. Trang tự kiểm tra báo cáo mới
                mỗi phút; lần tạo đầu tiên có thể mất vài phút.
              </Empty>
            );
          const item = data.item;
          const visibleFigures = requiredCharts(item.figures);
          const decompositions = visibleFigures.filter((f) =>
            f.filename.startsWith("decomposition_"),
          );
          const isDecomposition = selectedFigure === "decomposition";
          const figure =
            (isDecomposition
              ? decompositions.find(
                  (f) => f.station_id === decompositionStation,
                ) || decompositions[0]
              : null) ||
            visibleFigures.find((f) => f.filename === selectedFigure) ||
            visibleFigures[0];
          const calendarFigure =
            /^(line|scatter|histogram)_(day|week|month)\.png$/.exec(
              figure?.filename || "",
            );
          return (
            <div className="eda-content">
              <div className="eda-counts">
                <span>
                  <strong>{number(item.raw_rows)}</strong> quan sát
                </span>
                <span>
                  <strong>{number(item.station_count)}</strong> trạm
                </span>
                <span>
                  <strong>
                    {number(item.usable_bikes_without_usable_weather)}
                  </strong>{" "}
                  mẫu xe thiếu thời tiết hợp lệ
                </span>
                <span>
                  <strong>{number(item.outlier_flag_count)}</strong> cờ cần xem
                  xét
                </span>
              </div>
              <div className="toolbar">
                <label>
                  Biểu đồ EDA
                  <select
                    aria-label="Biểu đồ EDA"
                    value={
                      isDecomposition && decompositions.length
                        ? "decomposition"
                        : figure?.filename || ""
                    }
                    onChange={(e) => setSelectedFigure(e.target.value)}
                  >
                    {visibleFigures
                      .filter((f) => !f.filename.startsWith("decomposition_"))
                      .map((f) => (
                        <option key={f.filename} value={f.filename}>
                          {figureLabel(f)}
                        </option>
                      ))}
                    {decompositions.length > 0 && (
                      <option value="decomposition">
                        Phân rã xu hướng – mùa vụ – phần dư
                      </option>
                    )}
                  </select>
                </label>
                {isDecomposition && decompositions.length > 0 && (
                  <label>
                    Trạm phân rã chuỗi thời gian
                    <select
                      aria-label="Trạm phân rã chuỗi thời gian"
                      value={figure?.station_id || ""}
                      onChange={(event) =>
                        setDecompositionStation(event.target.value)
                      }
                    >
                      {decompositions.map((f) => (
                        <option key={f.filename} value={f.station_id}>
                          {stations.find((s) => s.station_id === f.station_id)
                            ?.name ||
                            f.title.replace("Phân rã chuỗi thời gian · ", "")}
                        </option>
                      ))}
                    </select>
                  </label>
                )}

              </div>
              {calendarFigure ? (
                <CalendarExplorer
                  key={calendarFigure[2]}
                  kind={calendarFigure[1]}
                  period={calendarFigure[2]}
                  stations={stations}
                />
              ) : figure ? (
                <DynamicEda key={`${item.report_id}:${figure.filename}`} reportId={item.report_id} figure={figure} stations={stations} revision={revision} refresh={refresh} />
              ) : (
                <Empty title="Báo cáo chưa có hình được công bố" />
              )}
            </div>
          );
        }}
      </Feedback>
    </Panel>
  );
}

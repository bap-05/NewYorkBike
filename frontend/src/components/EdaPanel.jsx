import DynamicEda from "./DynamicEda.jsx";
import { useState } from "react";
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

export default function EdaPanel({ stations }) {
  const { revision, refresh } = useApp();
  const report = useResource(
    (signal) => get("/eda", signal),
    "eda",
    revision,
  );
  const [selectedFigure, setSelectedFigure] = useState("series");
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
            visibleFigures.find((f) => f.filename === selectedFigure);
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
                    value={figure ? selectedFigure : "series"}
                    onChange={(e) => setSelectedFigure(e.target.value)}
                  >
                    <option value="series">Biểu đồ theo thời gian</option>
                    {visibleFigures
                      .filter((f) => Object.hasOwn(figures, f.filename))
                      .map((f) => (
                        <option key={f.filename} value={f.filename}>
                          {figures[f.filename]}
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
              {figure ? (
                <DynamicEda key={`${item.report_id}:${figure.filename}`} reportId={item.report_id} figure={figure} stations={stations} revision={revision} refresh={refresh} />
              ) : (
                <CalendarExplorer stations={stations} />
              )}
            </div>
          );
        }}
      </Feedback>
    </Panel>
  );
}

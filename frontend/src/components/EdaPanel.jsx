import DynamicEda from "./DynamicEda.jsx";
import { useState } from "react";
import { useApp } from "../App.jsx";
import { number } from "../lib/data.js";
import { Panel } from "./UI.jsx";
import CalendarExplorer from "./CalendarExplorer.jsx";

const figures = {
  "resampled_trend.png": "Xu hướng sau tổng hợp tuần/tháng",
  "weekly_seasonality.png": "Đường mùa vụ theo tuần",
  "correlation_all.png": "Ma trận tương quan giữa các biến",
};

export default function EdaPanel({ stations }) {
  const { revision, refresh } = useApp();
  const [selectedFigure, setSelectedFigure] = useState("series");
  const [decompositionStation, setDecompositionStation] = useState("");
  const [days, setDays] = useState(28);
  const isDecomposition = selectedFigure === "decomposition";
  const stationId = stations.some((row) => row.station_id === decompositionStation)
    ? decompositionStation : stations[0]?.station_id;
  const figure = isDecomposition
    ? { filename: "decomposition_live", station_id: stationId }
    : { filename: selectedFigure };

  return (
    <Panel title="Khám phá dữ liệu (EDA)">
      <div className="eda-content">
        <div className="eda-counts">
          <span><strong>{number(stations.length)}</strong> trạm</span>
        </div>
        <div className="toolbar">
          <label>
            Biểu đồ EDA
            <select aria-label="Biểu đồ EDA" value={selectedFigure}
              onChange={(event) => setSelectedFigure(event.target.value)}>
              <option value="series">Biểu đồ theo thời gian</option>
              {Object.entries(figures).map(([filename, title]) => (
                <option key={filename} value={filename}>{title}</option>
              ))}
              <option value="decomposition">Phân rã xu hướng – mùa vụ – phần dư</option>
            </select>
          </label>
          {selectedFigure !== "series" && (
            <label>
              Khoảng dữ liệu
              <select aria-label="Khoảng dữ liệu EDA" value={days}
                onChange={(event) => setDays(Number(event.target.value))}>
                <option value={28}>28 ngày gần nhất</option>
                <option value={60}>60 ngày gần nhất</option>
                <option value={90}>90 ngày gần nhất</option>
              </select>
            </label>
          )}
          {isDecomposition && (
            <label>
              Trạm phân rã chuỗi thời gian
              <select aria-label="Trạm phân rã chuỗi thời gian" value={stationId || ""}
                onChange={(event) => setDecompositionStation(event.target.value)}>
                {stations.map((station) => (
                  <option key={station.station_id} value={station.station_id}>{station.name}</option>
                ))}
              </select>
            </label>
          )}
        </div>
        {selectedFigure === "series" ? (
          <CalendarExplorer stations={stations} />
        ) : (
          <DynamicEda key={`${figure.filename}:${stationId}:${days}`}
            figure={figure} days={days} stations={stations} revision={revision} refresh={refresh} />
        )}
      </div>
    </Panel>
  );
}

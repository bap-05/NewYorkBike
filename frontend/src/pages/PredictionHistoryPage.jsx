import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useApp, RefreshButton } from "../App.jsx";
import { get, query } from "../lib/api.js";
import { number, servedError } from "../lib/data.js";
import { useResource } from "../lib/useResource.js";
import {
  Badge,
  Empty,
  Feedback,
  PageTitle,
  Panel,
  Table,
  Time,
} from "../components/UI.jsx";

export default function PredictionHistoryPage() {
  const { stationId } = useParams();
  const { stations, refresh } = useApp();
  return (
    <Feedback resource={stations} retry={refresh}>
      {(data) => {
        const station = data.items.find((s) => s.station_id === stationId);
        return station ? (
          <StationHistory key={stationId} station={station} />
        ) : (
          <Empty />
        );
      }}
    </Feedback>
  );
}

function StationHistory({ station }) {
  const { revision, refresh } = useApp();
  const [offset, setOffset] = useState(0);
  const stationId = station.station_id;
  const history = useResource(
    (signal) =>
      get(
        `/stations/${encodeURIComponent(stationId)}/predictions?${query({ limit: 20, offset })}`,
        signal,
      ),
    `prediction-history:${stationId}:${offset}`,
    revision,
  );
  return (
    <>
      <PageTitle title="Lịch sử dự báo 30 phút">
        <RefreshButton />
      </PageTitle>
      <Link className="button secondary" to="/predictions">
        ← Quay lại dự báo
      </Link>
      <Panel title={station.name}>
        <Feedback resource={history} retry={refresh}>
          {(page) => (
            <>
              {!page.items.length ? (
                <Empty title="Chưa có dự đoán trong 24 giờ gần nhất" />
              ) : (
                <Table
                  headers={[
                    "Phát hành",
                    "Loại",
                    "Mẫu đầu vào",
                    "Mục tiêu",
                    "Dự đoán",
                    "Thực tế",
                    "Sai số trước làm tròn",
                    "Trạng thái",
                  ]}
                >
                  {page.items.map((p) => (
                    <tr key={p.id}>
                      <td>
                        <Time value={p.issued_at} />
                      </td>
                      <td>
                        <Badge value={p.status} />
                      </td>
                      <td>
                        <Time value={p.input_time} />
                      </td>
                      <td>
                        <Time value={p.target_at} />
                      </td>
                      <td className="number-cell">
                        {number(p.predicted_bikes)}
                      </td>
                      <td>{number(p.actual_bikes)}</td>
                      <td>{number(servedError(p), 2)}</td>
                      <td>
                        {p.evaluated_at
                          ? "Đã đối chiếu"
                          : p.status === "unavailable"
                            ? "Không có dự đoán hợp lệ"
                            : "Chưa có mẫu đối chiếu"}
                      </td>
                    </tr>
                  ))}
                </Table>
              )}
              <div className="pagination">
                <span>
                  {number(page.pagination.total)} bản ghi trong 24 giờ gần nhất
                </span>
                <button
                  className="button secondary"
                  disabled={offset === 0 || history.loading}
                  onClick={() => setOffset(Math.max(0, offset - 20))}
                >
                  Trước
                </button>
                <button
                  className="button secondary"
                  disabled={!page.pagination.has_more || history.loading}
                  onClick={() => setOffset(offset + 20)}
                >
                  Sau
                </button>
              </div>
            </>
          )}
        </Feedback>
      </Panel>
    </>
  );
}

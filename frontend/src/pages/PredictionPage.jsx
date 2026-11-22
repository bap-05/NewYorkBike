import DayAheadPanel from "../components/DayAheadPanel.jsx";
import { Link } from "react-router-dom";
import { ArrowRight, Bike } from "lucide-react";
import { useApp, RefreshButton } from "../App.jsx";
import { get } from "../lib/api.js";
import { number, reasons, time, servedError } from "../lib/data.js";
import { useResource } from "../lib/useResource.js";
import { Badge, Empty, Feedback, PageTitle } from "../components/UI.jsx";

export default function PredictionPage() {
  const { stations, refresh } = useApp();
  return (
    <Feedback resource={stations} retry={refresh}>
      {(page) =>
        !page.items.length ? (
          <Empty />
        ) : (
          <PredictionContent stations={page.items} />
        )
      }
    </Feedback>
  );
}

function PredictionContent({ stations }) {
  const { revision, refresh } = useApp();
  const forecasts = useResource(
    async (signal) => {
      const results = await Promise.allSettled(
        stations.map((s) =>
          get(
            `/stations/${encodeURIComponent(s.station_id)}/predictions/latest`,
            signal,
          ),
        ),
      );
      return stations.map((station, i) => ({
        station,
        result: results[i].status === "fulfilled" ? results[i].value : null,
      }));
    },
    `forecasts:${stations.map((s) => s.station_id).join(",")}`,
    revision,
  );
  return (
    <>
      <PageTitle
        eyebrow="ĐÓN TRƯỚC HÀNH TRÌNH"
        title="Dự báo số xe tại các trạm"
        description="Dự báo theo giờ ngày mai và số xe trong 30 phút tiếp theo."
      >
        <RefreshButton />
      </PageTitle>
      <DayAheadPanel stations={stations} />
      <section className="prediction-next" aria-labelledby="prediction-next-heading">
      <h2 id="prediction-next-heading">Dự báo 30 phút tiếp theo</h2>
      <Feedback resource={forecasts} retry={refresh}>
        {(rows) => {
          return (
            <>
              <div className="prediction-grid">
                {rows.map(({ station: s, result }) => {
                  const p = result?.item;
                  return (
                    <article className="prediction-card" key={s.station_id}>
                      <div className="prediction-card-top">
                        <span className="station-symbol">
                          <Bike size={21} />
                        </span>
                        <Badge value={p?.status} />
                      </div>
                      <h2>
                        <Link
                          className="prediction-card-link"
                          to={`/predictions/${encodeURIComponent(s.station_id)}/history`}
                        >
                          {s.name}
                        </Link>
                      </h2>
                      {!result ? (
                        <p role="alert">
                          Không tải được dự đoán trạm này.{" "}
                          <button className="text-button" onClick={refresh}>
                            Thử lại
                          </button>
                        </p>
                      ) : !p ? (
                        <p>Chưa có dự đoán được công bố.</p>
                      ) : (
                        <>
                          <div
                            className={`forecast-number ${!p.is_current ? "forecast-muted" : ""}`}
                          >
                            {number(p.predicted_bikes)}
                            <span>xe dự đoán</span>
                          </div>
                          <div className="forecast-state">
                            {p.is_current ? (
                              <span className="current-label">
                                Còn hiệu lực
                              </span>
                            ) : (
                              <span className="outdated-label">
                                {p.status === "unavailable"
                                  ? "Chưa có kết quả hợp lệ"
                                  : "Kết quả cũ · không dùng cho hiện tại"}
                              </span>
                            )}
                          </div>
                          <div className="prediction-times">
                            <span>
                              Mẫu đầu vào<strong>{time(p.input_time)}</strong>
                            </span>
                            <ArrowRight size={16} />
                            <span>
                              Mục tiêu<strong>{time(p.target_at)}</strong>
                            </span>
                          </div>
                          <p className="subtle">
                            Phát hành: {time(p.issued_at)}
                          </p>
                          {p.model?.experimental && (
                            <p className="subtle">
                              Mô hình thời tiết thử nghiệm
                            </p>
                          )}
                          {p.weather_inputs && (
                            <p className="subtle">
                              Nhiệt độ {number(p.weather_inputs.temperature, 1)}{" "}
                              °C · Độ ẩm {number(p.weather_inputs.humidity, 0)}%
                              {" · "}Mưa {number(p.weather_inputs.rain, 2)}{" "}
                              mm/kỳ nguồn · Gió{" "}
                              {number(p.weather_inputs.wind_speed, 1)} m/s
                            </p>
                          )}
                          <p className="prediction-reason">
                            {p.is_current
                              ? reasons[p.reason] || ""
                              : reasons[p.display_reason] ||
                                reasons[p.reason] ||
                                "Mẫu hoặc thời điểm mục tiêu không còn mới."}
                          </p>
                          <details className="forecast-details">
                            <summary>Nguồn & mô hình</summary>
                            <p>
                              Nguồn báo: {time(p.input_source_observed_at)}
                              <br />
                              Mốc đọc dữ liệu: {time(p.input_cutoff_at)}
                              <br />
                              Mô hình:{" "}
                              {p.model
                                ? `${p.status === "baseline" ? "Mô hình cơ sở" : "Mô hình học máy"} · #${p.model.id}`
                                : "Chưa có"}
                              <br />
                              Mẫu thực tế: {time(p.actual_time)}
                              <br />
                              Sai số mô hình trước giới hạn:{" "}
                              {number(p.absolute_error, 2)}
                            </p>
                          </details>
                          <div className="forecast-evaluation">
                            {p.actual_bikes != null ? (
                              <>
                                Thực tế:{" "}
                                <strong>{number(p.actual_bikes)}</strong> xe ·
                                Sai số trước làm tròn:{" "}
                                <strong>{number(servedError(p), 2)}</strong>
                              </>
                            ) : (
                              "Chưa có mẫu thực tế để đối chiếu"
                            )}
                          </div>
                        </>
                      )}
                    </article>
                  );
                })}
              </div>
            </>
          );
        }}
      </Feedback>
      </section>
    </>
  );
}

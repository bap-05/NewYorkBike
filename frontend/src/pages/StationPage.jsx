import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  Bike,
  CloudSun,
  Droplets,
  MapPin,
  ParkingCircle,
  Thermometer,
  Wind,
} from "lucide-react";
import { useApp, RefreshButton } from "../App.jsx";
import { allPages, get } from "../lib/api.js";
import { number, observationPoints, stationPath, time } from "../lib/data.js";
import { useResource } from "../lib/useResource.js";
import {
  Badge,
  Empty,
  Feedback,
  PageTitle,
  Panel,
  Stat,
  Table,
  Time,
  Value,
} from "../components/UI.jsx";
import LineChart from "../components/LineChart.jsx";

export default function StationPage() {
  const { stations, refresh } = useApp();
  return (
    <Feedback resource={stations} retry={refresh}>
      {(page) =>
        !page.items.length ? (
          <Empty title="Chưa có trạm được theo dõi" />
        ) : (
          <StationContent stations={page.items} />
        )
      }
    </Feedback>
  );
}

function StationContent({ stations }) {
  const { stationId } = useParams();
  const navigate = useNavigate();
  const id = stationId || stations[0].station_id;
  const { revision, refresh } = useApp();
  const [hours, setHours] = useState(24);
  const detail = useResource(
    (signal) => get(`/stations/${encodeURIComponent(id)}`, signal),
    `detail:${id}`,
    revision,
  );
  const history = useResource(
    (signal) =>
      allPages(
        `/stations/${encodeURIComponent(id)}/history`,
        {
          from: new Date(Date.now() - hours * 3600000).toISOString(),
          to: new Date().toISOString(),
          include_estimated: true,
        },
        signal,
      ),
    `history:${id}:${hours}`,
    revision,
  );
  return (
    <>
      <PageTitle
        eyebrow="MỖI TRẠM, MỘT NHỊP RIÊNG"
        title="Chi tiết trạm xe"
        description="Quan sát gần nhất, thời tiết tại đúng tọa độ trạm và lịch sử số xe."
      >
        <RefreshButton />
      </PageTitle>
      <div className="toolbar">
        <label>
          Trạm đang xem
          <select
            value={id}
            onChange={(e) => navigate(stationPath(e.target.value))}
          >
            {!stations.some((s) => s.station_id === id) && (
              <option value={id}>{id}</option>
            )}
            {stations.map((s) => (
              <option key={s.station_id} value={s.station_id}>
                {s.name}
              </option>
            ))}
          </select>
        </label>
        <Link className="text-button" to="/map">
          <MapPin size={16} />
          Xem bản đồ
        </Link>
      </div>
      <Feedback resource={detail} retry={refresh}>
        {({ item: s }) => {
          const b = s.latest_observation,
            w = s.latest_weather;
          return (
            <>
              <div className="station-heading">
                <div>
                  <h2>{s.name}</h2>
                  <p>
                    {number(s.latitude, 6)}, {number(s.longitude, 6)} · Sức chứa{" "}
                    {number(s.capacity)} xe
                  </p>
                </div>
                <Badge value={s.availability_status} />
              </div>
              {s.availability_status !== "fresh" && (
                <div className="notice">
                  Số xe bên dưới thuộc mẫu gần nhất, không đại diện chắc chắn
                  cho tình trạng hiện tại. Mẫu thu lúc {time(b?.sampled_at)}.
                </div>
              )}
              <div className="stats-grid three">
                <Stat
                  icon={Bike}
                  label="Xe trong mẫu gần nhất"
                  value={number(b?.available_bikes)}
                  detail={`Nguồn báo lúc ${time(b?.source_observed_at)}`}
                  accent
                />
                <Stat
                  icon={ParkingCircle}
                  label="Chỗ trả xe"
                  value={number(b?.available_docks)}
                  detail={`Thu thập lúc ${time(b?.collected_at)}`}
                />
                <Stat
                  icon={MapPin}
                  label="Trạng thái cho thuê / trả xe"
                  value={`${booleanLabel(b?.is_renting)} / ${booleanLabel(b?.is_returning)}`}
                  detail="Có / không theo trạng thái nguồn"
                />
              </div>
              <Panel
                title="Thời tiết tại trạm"
                subtitle="Open-Meteo · Theo tọa độ riêng của trạm"
                action={<Badge value={w?.status} />}
              >
                {!w ? (
                  <Empty title="Mẫu xe chưa có thời tiết phù hợp" />
                ) : (
                  <>
                    <div className="weather-grid">
                      {[
                        [
                          Thermometer,
                          "Nhiệt độ",
                          w.temperature,
                          w.units.temperature_2m,
                        ],
                        [
                          Droplets,
                          "Độ ẩm",
                          w.humidity,
                          w.units.relative_humidity_2m,
                        ],
                        [CloudSun, "Mưa", w.rain, w.units.rain],
                        [
                          Wind,
                          "Tốc độ gió",
                          w.wind_speed,
                          w.units.wind_speed_10m,
                        ],
                      ].map(([Icon, label, value, unit]) => (
                        <div className="weather-item" key={label}>
                          <Icon size={21} />
                          <span>{label}</span>
                          <strong>
                            <Value value={value} unit={unit} />
                          </strong>
                        </div>
                      ))}
                    </div>
                    <div className="weather-meta">
                      Thời điểm thời tiết: {time(w.weather_time)} · Kỳ đo:{" "}
                      {number(w.interval_seconds)} giây · Tọa độ yêu cầu:{" "}
                      {number(w.requested_latitude, 6)},{" "}
                      {number(w.requested_longitude, 6)}
                    </div>
                  </>
                )}
              </Panel>
            </>
          );
        }}
      </Feedback>
      <Panel
        title="Lịch sử số xe có thể thuê"
        subtitle="Hiển thị dữ liệu thực tế; di chuột vào điểm để xem thời gian và số xe."
        action={
          <select
            aria-label="Khoảng lịch sử"
            value={hours}
            onChange={(e) => setHours(Number(e.target.value))}
          >
            <option value={24}>24 giờ gần nhất</option>
            <option value={72}>3 ngày gần nhất</option>
            <option value={168}>7 ngày gần nhất</option>
          </select>
        }
      >
        <Feedback resource={history} retry={refresh}>
          {(page) => (
            <>
              <LineChart points={observationPoints(page.items)} />
              <details className="data-details">
                <summary>Xem {number(page.items.length)} mẫu dữ liệu</summary>
                <Table
                  headers={[
                    "Thời điểm mẫu",
                    "Xe",
                    "Chỗ trả",
                    "Chất lượng nguồn",
                    "Thời tiết",
                  ]}
                >
                  {page.items
                    .slice()
                    .reverse()
                    .map(({ observation: b, weather: w, is_estimated }) => (
                      <tr key={b.id}>
                        <td>
                          <Time value={b.sampled_at} />
                        </td>
                        <td>{number(b.available_bikes)}</td>
                        <td>{number(b.available_docks)}</td>
                        <td>
                          <Badge
                            value={
                              is_estimated
                                ? "estimated"
                                : b.quality_status === "valid"
                                  ? "ok"
                                  : b.quality_status
                            }
                          />
                        </td>
                        <td>
                          {w ? (
                            <Value
                              value={w.temperature}
                              unit={w.units.temperature_2m}
                            />
                          ) : (
                            "Thiếu thời tiết"
                          )}
                        </td>
                      </tr>
                    ))}
                </Table>
              </details>
            </>
          )}
        </Feedback>
      </Panel>
    </>
  );
}
function booleanLabel(value) {
  return value === true ? "Có" : value === false ? "Không" : "—";
}

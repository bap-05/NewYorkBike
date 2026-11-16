import { createContext, useContext, useEffect, useState } from "react";
import { Link, NavLink, Route, Routes } from "react-router-dom";
import {
  Activity,
  ArrowRight,
  Bike,
  ChartNoAxesCombined,
  Clock3,
  Layers3,
  Map,
  MapPin,
  RefreshCw,
  Search,
  Sparkles,
  TriangleAlert,
} from "lucide-react";
import { allPages, get } from "./lib/api.js";
import { latestSample, number, stationPath, time } from "./lib/data.js";
import { useResource } from "./lib/useResource.js";
import {
  Badge,
  DetailLink,
  Empty,
  Feedback,
  PageTitle,
  Panel,
  Stat,
  Table,
  Time,
} from "./components/UI.jsx";
import StationMap from "./components/StationMap.jsx";
import ClusterExplorer from "./components/ClusterExplorer.jsx";
import StationPage from "./pages/StationPage.jsx";
import AnalysisPage from "./pages/AnalysisPage.jsx";
import PredictionPage from "./pages/PredictionPage.jsx";
import PredictionHistoryPage from "./pages/PredictionHistoryPage.jsx";

const Context = createContext(null);
export const useApp = () => useContext(Context);

export default function App() {
  const [revision, setRevision] = useState(0);
  const [now, setNow] = useState(new Date().toISOString());
  useEffect(() => {
    const interval = setInterval(() => {
      setNow(new Date().toISOString());
      setRevision((x) => x + 1);
    }, 60000);
    return () => clearInterval(interval);
  }, []);
  const refresh = () => {
    setNow(new Date().toISOString());
    setRevision((x) => x + 1);
  };
  const stations = useResource(
    (signal) => allPages("/stations", {}, signal),
    "stations",
    revision,
  );
  return (
    <Context.Provider value={{ revision, refresh, stations }}>
      <a className="skip-link" href="#main">
        Chuyển đến nội dung
      </a>
      <header className="header">
        <div className="header-inner">
          <Link className="brand" to="/">
            <span className="brand-mark">
              <Bike size={25} />
            </span>
            <span>
              NewYork<span className="brand-light">Bike</span>
              <small>THEO DÕI XE ĐẠP THÀNH PHỐ</small>
            </span>
          </Link>
          <div className="header-location">
            <span className="live-dot" />
            <span>
              NEW YORK, MỸ<small>{time(now)}</small>
            </span>
          </div>
        </div>
      </header>
        <div className="nav-line">
          <nav aria-label="Điều hướng chính">
            <NavLink to="/" end>
              <Activity size={17} />
              Tổng quan
            </NavLink>
            <NavLink to="/map">
              <Map size={17} />
              Bản đồ trạm
            </NavLink>
            <NavLink to="/stations">
              <MapPin size={17} />
              Chi tiết trạm
            </NavLink>
            <NavLink to="/analysis">
              <Layers3 size={17} />
              Phân tích & phân nhóm
            </NavLink>
            <NavLink to="/predictions">
              <Sparkles size={17} />
              Dự đoán
            </NavLink>
          </nav>
        </div>
      <main id="main">
        <Routes>
          <Route path="/" element={<OverviewPage />} />
          <Route path="/map" element={<MapPage />} />
          <Route path="/stations" element={<StationPage />} />
          <Route path="/stations/:stationId" element={<StationPage />} />
          <Route path="/analysis" element={<AnalysisPage />} />
          <Route path="/predictions" element={<PredictionPage />} />
          <Route path="/predictions/:stationId/history" element={<PredictionHistoryPage />} />
          <Route
            path="*"
            element={
              <div className="panel">
                <Empty title="Không tìm thấy trang">
                  <Link to="/">Quay về tổng quan</Link>
                </Empty>
              </div>
            }
          />
        </Routes>
      </main>
      <footer>
        <span>
          <Bike size={17} /> NewYorkBike{" "}
          <span className="footer-divider">/</span> Dữ liệu thật, góc nhìn rõ
          hơn.
        </span>
        <span>
          Citi Bike GBFS · Open-Meteo <span className="footer-divider">/</span>{" "}
          Giờ New York
        </span>
      </footer>
    </Context.Provider>
  );
}

export function RefreshButton() {
  const { refresh } = useApp();
  return (
    <button className="button secondary" onClick={refresh}>
      <RefreshCw size={16} />
      Làm mới
    </button>
  );
}

function OverviewPage() {
  const { revision, refresh, stations } = useApp();
  const overview = useResource(
    (signal) => get("/overview", signal),
    "overview",
    revision,
  );
  return (
    <>
      <PageTitle
        eyebrow="THÀNH PHỐ TRÊN HAI BÁNH XE"
        title="Một nhịp nhìn New York."
        description="Theo dõi trạm xe, hiểu nhịp di chuyển và đón trước 30 phút tiếp theo."
      >
        <RefreshButton />
      </PageTitle>
      <Feedback resource={overview} retry={refresh}>
        {(data) => (
          <>
            <div className="stats-grid">
              <Stat
                icon={MapPin}
                label="Trạm đang theo dõi"
                value={number(data.station_count)}
                detail="Trong phạm vi nghiên cứu"
              />
              <Stat
                icon={Bike}
                label="Xe có thể thuê"
                value={number(data.fresh_available_bikes)}
                detail="Chỉ cộng các trạm có dữ liệu mới"
                accent
              />
              <Stat
                icon={TriangleAlert}
                label="Trạm hết / ít xe"
                value={
                  data.fresh_available_bikes === null
                    ? "—"
                    : `${number(data.fresh_empty_station_count)} / ${number(data.fresh_low_bike_station_count)}`
                }
                detail="Hết xe / còn từ 1 đến 3 xe · mẫu mới"
              />
              <Stat
                icon={Clock3}
                label="Trạm có dữ liệu mới"
                value={number(data.observation_status_counts.fresh ?? 0)}
                detail="Mẫu xe trong ngưỡng độ mới của API"
              />
            </div>
            <Feedback resource={stations} retry={refresh}>
              {(page) => (
                <>
                  <div className="update-line">
                    <span className="live-dot" />
                    Mẫu thu thập gần nhất:{" "}
                    <Time value={latestSample(page.items)} />
                    <span className="push-right">
                      Tự cập nhật trang mỗi phút
                    </span>
                  </div>
                  <div className="overview-grid">
                    <Panel
                      title="Nhịp xe trên bản đồ"
                      subtitle="Vị trí thực tế của các trạm đang theo dõi"
                      action={<DetailLink to="/map" children="Mở bản đồ" />}
                    >
                      <StationMap stations={page.items} compact />
                    </Panel>
                    <section className="story-card">
                      <span className="eyebrow">NHÌN XA HƠN HIỆN TẠI</span>
                      <Sparkles size={33} />
                      <h2>
                        Trạm bạn chọn.
                        <br />
                        30 phút tiếp theo.
                      </h2>
                      <p>
                        Xem dự đoán cùng mốc dữ liệu, thời điểm mục tiêu và kết
                        quả đối chiếu thực tế.
                      </p>
                      <Link className="button cream" to="/predictions">
                        Khám phá dự đoán
                        <ArrowRight size={17} />
                      </Link>
                      <div className="story-rings" aria-hidden="true" />
                    </section>
                  </div>
                  <Panel
                    title="Các trạm đang theo dõi"
                    subtitle="Số xe từ mẫu gần nhất; kiểm tra trạng thái trước khi sử dụng."
                    action={
                      <DetailLink to="/stations" children="Khám phá trạm" />
                    }
                  >
                    {!page.items.length ? (
                      <Empty />
                    ) : (
                      <Table
                        headers={[
                          "Trạm xe",
                          "Xe có thể thuê",
                          "Chỗ trả xe",
                          "Trạng thái",
                          "Thời điểm mẫu",
                          "",
                        ]}
                      >
                        {page.items.map((s) => (
                          <tr key={s.station_id}>
                            <td>
                              <Link
                                className="station-name"
                                to={stationPath(s.station_id)}
                              >
                                {s.name}
                              </Link>
                              <small>Sức chứa {number(s.capacity)} xe</small>
                            </td>
                            <td className="number-cell">
                              {number(s.latest_observation?.available_bikes)}
                            </td>
                            <td>
                              {number(s.latest_observation?.available_docks)}
                            </td>
                            <td>
                              <Badge value={s.availability_status} />
                            </td>
                            <td>
                              <Time value={s.latest_observation?.sampled_at} />
                            </td>
                            <td>
                              <DetailLink to={stationPath(s.station_id)} />
                            </td>
                          </tr>
                        ))}
                      </Table>
                    )}
                  </Panel>
                </>
              )}
            </Feedback>
            <Panel
              title="Trạng thái xử lý dữ liệu"
              subtitle="Các dịch vụ chạy độc lập; mở website không kích hoạt thu thập hay huấn luyện."
            >
              <div className="service-grid">
                {data.services.map((s) => (
                  <div className="service" key={s.service_name}>
                    <span className="service-icon">
                      <ChartNoAxesCombined size={19} />
                    </span>
                    <div>
                      <strong>
                        {{
                          ingestion: "Thu thập",
                          analysis: "Phân tích",
                          clustering: "Phân nhóm",
                          prediction: "Dự đoán",
                        }[s.service_name] || "Dịch vụ khác"}
                      </strong>
                      <Badge value={s.last_attempt_status} />
                      <small>
                        Hoàn tất gần nhất: {time(s.last_completed_at)}
                      </small>
                    </div>
                  </div>
                ))}
              </div>
            </Panel>
          </>
        )}
      </Feedback>
    </>
  );
}

function MapPage() {
  const { stations, refresh } = useApp();
  const [mapMode, setMapMode] = useState("availability");
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("all");
  const [selectedId, setSelectedId] = useState(null);
  return (
    <>
      <PageTitle
        eyebrow="KHÁM PHÁ THÀNH PHỐ"
        title="Tìm trạm, chọn hành trình."
        description="Bấm vào vị trí trên bản đồ hoặc chọn một trạm trong danh sách."
      >
        <RefreshButton />
      </PageTitle>
      <div className="toolbar">
        <label>
          Màu trên bản đồ
          <select
            aria-label="Chế độ bản đồ"
            value={mapMode}
            onChange={(e) => setMapMode(e.target.value)}
          >
            <option value="availability">Theo tình trạng xe</option>
            <option value="clusters">Theo nhóm hành vi</option>
          </select>
        </label>
      </div>
      <Feedback resource={stations} retry={refresh}>
        {(page) => {
          if (mapMode === "clusters")
            return <ClusterExplorer stations={page.items} />;
          const visible = page.items.filter(
            (s) =>
              s.name
                .toLocaleLowerCase("vi")
                .includes(search.toLocaleLowerCase("vi")) &&
              (filter === "all" || s.availability_status === filter),
          );
          const selected = visible.find((s) => s.station_id === selectedId);
          return (
            <>
              <div className="map-layout">
                <aside className="panel station-sidebar">
                  <div className="sidebar-controls">
                    <label className="search-box">
                      <Search size={17} />
                      <input
                        aria-label="Tìm trạm theo tên"
                        placeholder="Tìm tên trạm…"
                        value={search}
                        onChange={(e) => setSearch(e.target.value)}
                      />
                    </label>
                    <select
                      aria-label="Lọc trạng thái trạm"
                      value={filter}
                      onChange={(e) => setFilter(e.target.value)}
                    >
                      <option value="all">Tất cả trạng thái</option>
                      <option value="fresh">Dữ liệu mới</option>
                      <option value="stale">Dữ liệu cũ</option>
                      <option value="inactive">Ngừng cho thuê</option>
                    </select>
                    <p className="subtle">
                      {visible.length} / {page.items.length} trạm
                    </p>
                  </div>
                  <div className="station-list">
                    {!visible.length && <Empty title="Không tìm thấy trạm" />}
                    {visible.map((s) => (
                      <div
                        className={`station-list-item ${selectedId === s.station_id ? "selected" : ""}`}
                        key={s.station_id}
                      >
                        <button
                          className="station-select"
                          onClick={() => setSelectedId(s.station_id)}
                        >
                          <MapPin size={17} />
                          <strong>{s.name}</strong>
                        </button>
                        <Badge value={s.availability_status} />
                        <p>
                          <strong>
                            {number(s.latest_observation?.available_bikes)}
                          </strong>{" "}
                          xe · {number(s.latest_observation?.available_docks)}{" "}
                          chỗ trả
                        </p>
                        <DetailLink to={stationPath(s.station_id)} />
                      </div>
                    ))}
                  </div>
                </aside>
                <div className="panel map-panel">
                  <StationMap stations={visible} selected={selected} />
                </div>
              </div>
              <p className="subtle map-footnote">
                Xám: dữ liệu cũ hoặc trạm không hoạt động bình thường. Số xe cũ
                không bảo đảm số xe có thể thuê hiện tại.
              </p>
            </>
          );
        }}
      </Feedback>
    </>
  );
}

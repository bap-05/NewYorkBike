import { useEffect, useId, useState } from "react";
import {
  MapContainer,
  TileLayer,
  CircleMarker,
  Popup,
  Tooltip,
  useMap,
  ZoomControl,
} from "react-leaflet";
import { Link } from "react-router-dom";
import { number, stationPath } from "../lib/data.js";
import { Badge } from "./UI.jsx";
import ErrorBoundary from "./ErrorBoundary.jsx";
import {
  bikeLevel, clusterColor, clusterProfile, frequencyLevel, summarizeClusters, variabilityLevel,
} from "../lib/clusters.js";

function Focus({ station, reservePopupSpace }) {
  const map = useMap();
  const latitude = station?.latitude;
  const longitude = station?.longitude;
  useEffect(() => {
    if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) return;
    const zoom = 15;
    const location = [latitude, longitude];
    const center = reservePopupSpace
      ? map.unproject(map.project(location, zoom).subtract([0, map.getSize().y * 0.23]), zoom)
      : location;
    map.flyTo(center, zoom, { duration: 0.7 });
  }, [latitude, longitude, map, reservePopupSpace]);
  return null;
}
function FitStations({ stations }) {
  const map = useMap();
  const boundsKey = JSON.stringify(
    stations.map((s) => [s.latitude, s.longitude]),
  );
  useEffect(() => {
    const bounds = JSON.parse(boundsKey);
    if (bounds.length)
      map.fitBounds(bounds, { padding: [30, 30], maxZoom: 14 });
  }, [boundsKey, map]);
  return null;
}
function color(station) {
  if (station.availability_status !== "fresh") return "#8d969b";
  const n = station.latest_observation?.available_bikes;
  return n === 0 ? "#bb5250" : n <= 3 ? "#bc842f" : "#167c70";
}
export default function StationMap(props) {
  return (
    <ErrorBoundary fallback={(retry) => (
      <div className="notice error" role="alert">
        <span>Không thể hiển thị bản đồ.</span>
        <button className="text-button" onClick={retry}>Thử lại bản đồ</button>
      </div>
    )}>
      <StationMapContent {...props} />
    </ErrorBoundary>
  );
}

function StationMapContent({
  stations,
  selected,
  compact = false,
  clusterMembers = null,
  onSelect,
  focusSelected = true,
  selectionOnly = false,
}) {
  const [tileError, setTileError] = useState(false);
  const membership = new Map(
    (clusterMembers || []).map((m) => [m.station_id, m.cluster_label]),
  );
  const groups = summarizeClusters(clusterMembers || []);
  const groupByLabel = new Map(groups.map((group) => [group.label, group]));
  const located = stations.filter(
    (s) => Number.isFinite(s.latitude) && Number.isFinite(s.longitude),
  );
  return (
    <div className={`map-shell ${compact ? "compact-map" : ""}`}>
      <MapContainer
        center={[40.748, -73.986]}
        zoom={12}
        scrollWheelZoom
        zoomControl={false}
      >
        <ZoomControl zoomInTitle="Phóng to" zoomOutTitle="Thu nhỏ" />
        <TileLayer
          url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}"
          attribution='Tiles &copy; <a href="https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer">Esri</a> — Sources: Esri, HERE, Garmin, USGS, Intermap, INCREMENT P, NRCan, Esri Japan, METI, Esri China (Hong Kong), Esri Korea, Esri (Thailand), NGCC, &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>, GIS User Community'
          maxZoom={19}
          eventHandlers={{ tileerror: () => setTileError(true) }}
        />
        <FitStations stations={located} />
        <Focus station={focusSelected ? selected : null} reservePopupSpace={Boolean(onSelect)} />
        {located.map((s) => (
          <CircleMarker
            key={s.station_id}
            center={[s.latitude, s.longitude]}
            radius={selected?.station_id === s.station_id ? 11 : 8}
            eventHandlers={onSelect ? { click: () => onSelect(s.station_id) } : undefined}
            pathOptions={{
              color: onSelect && selected?.station_id === s.station_id ? "#183d5a" : "white",
              weight: 3,
              fillColor: clusterMembers
                ? clusterColor(membership.get(s.station_id))
                : selectionOnly ? "#167c70" : color(s),
              fillOpacity: 1,
            }}
          >
            {onSelect && <Tooltip>{s.name}</Tooltip>}
            <Popup {...(onSelect ? { keepInView: true, autoPanPadding: [12, 16] } : {})}>
              <div className="map-popup">
                <strong>{s.name}</strong>
                {clusterMembers && <ClusterPopupGroup group={groupByLabel.get(membership.get(s.station_id))} />}
                <Badge value={s.availability_status} />
                <p>
                  {number(s.latest_observation?.available_bikes)} xe ·{" "}
                  {number(s.latest_observation?.available_docks)} chỗ trả
                </p>
                <Link to={stationPath(s.station_id)}>Xem chi tiết trạm →</Link>
              </div>
            </Popup>
          </CircleMarker>
        ))}
      </MapContainer>
      {tileError && (
        <div className="tile-warning" role="status">
          Không tải được một số ô bản đồ. Danh sách trạm vẫn có thể sử dụng.
        </div>
      )}
      {clusterMembers ? (
        <ClusterLegend groups={groups} stations={stations} membership={membership} />
      ) : !selectionOnly && (
        <div className="map-legend">
            <span>
              <i className="dot teal" /> Có xe
            </span>
            <span>
              <i className="dot amber" /> Ít xe
            </span>
            <span>
              <i className="dot red" /> Hết xe
            </span>
            <span>
              <i className="dot gray" /> Cũ / ngừng hoạt động
            </span>
        </div>
      )}
    </div>
  );
}

function ClusterLegend({ groups, stations, membership }) {
  const detailId = useId();
  const [hovered, setHovered] = useState(null);
  const [focused, setFocused] = useState(null);
  const [pinned, setPinned] = useState(null);
  const active = hovered ?? focused ?? pinned;
  const group = groups.find(({ label }) => label === active);
  const ungrouped = stations.filter((station) => !membership.has(station.station_id));
  const names = new Map(stations.map((station) => [station.station_id, station.name]));
  const entries = [...groups.map(({ label, items }) => ({
    key: label,
    title: `Nhóm ${label + 1} · ${items.length} trạm`,
    color: clusterColor(label),
  })), { key: "ungrouped", title: "Chưa có nhóm", color: "#8d969b" }];
  const entry = entries.find(({ key }) => key === active);

  return (
    <div className="map-legend cluster-map-legend" onPointerLeave={() => setHovered(null)}
      onKeyDown={(event) => {
        if (event.key === "Escape") {
          setHovered(null);
          setFocused(null);
          setPinned(null);
        }
      }}>
      {entry && (
        <section id={detailId} className="cluster-legend-detail" aria-label={entry.title}>
          <h3><i className="dot" style={{ background: entry.color }} />{entry.title}</h3>
          {group ? (
            <>
              <p>{clusterProfile(group.values)}</p>
              <dl>
                <dt>Mức xe thường có</dt><dd>{bikeLevel(group.values.mean_availability_ratio)}</dd>
                <dt>Độ ổn định</dt><dd>{variabilityLevel(group.values.std_availability_ratio)}</dd>
                <dt>Tần suất hết xe</dt><dd>{frequencyLevel(group.values.empty_ratio)}</dd>
                <dt>Tần suất ít xe</dt><dd>{frequencyLevel(group.values.low_bikes_ratio)}</dd>
              </dl>
              <p><strong>Các trạm:</strong> {group.items.map((station) =>
                names.get(station.station_id) || station.metadata_snapshot?.name || station.station_id
              ).join("; ")}</p>
            </>
          ) : (
            <p>{ungrouped.length
              ? `Các trạm chưa được gán nhóm trong lượt này: ${ungrouped.map(({ name }) => name).join("; ")}.`
              : "Tất cả trạm trong danh sách đã được gán nhóm."}</p>
          )}
        </section>
      )}
      {entries.map(({ key, title, color }) => (
        <button key={key} type="button" aria-expanded={key === active}
          aria-controls={key === active ? detailId : undefined}
          onPointerEnter={(event) => { if (event.pointerType === "mouse") setHovered(key); }}
          onFocus={(event) => { if (event.currentTarget.matches(":focus-visible")) setFocused(key); }}
          onBlur={() => setFocused(null)}
          onClick={() => {
            setHovered(null);
            setFocused(null);
            setPinned((previous) => previous === key ? null : key);
          }}>
          <i className="dot" style={{ background: color }} aria-hidden="true" />
          {title}
        </button>
      ))}
    </div>
  );
}

function ClusterPopupGroup({ group }) {
  if (!group) return <p>Chưa có nhóm trong lượt này</p>;
  return <div className="map-popup-group">
    <strong>
      <i className="dot" style={{ background: clusterColor(group.label) }} />
      Nhóm {group.label + 1} · {group.items.length} trạm
    </strong>
    <p>{clusterProfile(group.values)}</p>
  </div>;
}

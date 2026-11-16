import { useEffect, useState } from "react";
import {
  MapContainer,
  TileLayer,
  CircleMarker,
  Popup,
  useMap,
  ZoomControl,
} from "react-leaflet";
import { Link } from "react-router-dom";
import { number, stationPath } from "../lib/data.js";
import { Badge } from "./UI.jsx";
import { clusterColor } from "../lib/clusters.js";

function Focus({ station }) {
  const map = useMap();
  useEffect(() => {
    if (station)
      map.flyTo([station.latitude, station.longitude], 15, { duration: 0.7 });
  }, [station, map]);
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
export default function StationMap({
  stations,
  selected,
  compact = false,
  clusterMembers = null,
}) {
  const [tileError, setTileError] = useState(false);
  const membership = new Map(
    (clusterMembers || []).map((m) => [m.station_id, m.cluster_label]),
  );
  const groups = [
    ...new Set((clusterMembers || []).map((m) => m.cluster_label)),
  ].sort((a, b) => a - b);
  const located = stations.filter(
    (s) => Number.isFinite(s.latitude) && Number.isFinite(s.longitude),
  );
  return (
    <div className={`map-shell ${compact ? "compact-map" : ""}`}>
      <MapContainer
        center={[40.748, -73.986]}
        zoom={12}
        scrollWheelZoom={false}
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
        <Focus station={selected} />
        {located.map((s) => (
          <CircleMarker
            key={s.station_id}
            center={[s.latitude, s.longitude]}
            radius={selected?.station_id === s.station_id ? 11 : 8}
            pathOptions={{
              color: "white",
              weight: 3,
              fillColor: clusterMembers
                ? clusterColor(membership.get(s.station_id))
                : color(s),
              fillOpacity: 1,
            }}
          >
            <Popup>
              <div className="map-popup">
                <strong>{s.name}</strong>
                {clusterMembers && (
                  <p>
                    {membership.has(s.station_id)
                      ? `Nhóm ${membership.get(s.station_id) + 1}`
                      : "Chưa có nhóm trong lượt này"}
                  </p>
                )}
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
      <div className="map-legend">
        {clusterMembers ? (
          <>
            {groups.map((label) => (
              <span key={label}>
                <i
                  className="dot"
                  style={{ background: clusterColor(label) }}
                />
                Nhóm {label + 1}
              </span>
            ))}
            <span>
              <i className="dot gray" />
              Chưa có nhóm
            </span>
          </>
        ) : (
          <>
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
          </>
        )}
      </div>
    </div>
  );
}

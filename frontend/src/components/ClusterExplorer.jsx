import { useApp } from "../App.jsx";
import { allPages, get } from "../lib/api.js";
import { useResource } from "../lib/useResource.js";
import { bikeLevel, changeLevel, clusterColor, clusterProfile, frequencyLevel,
  summarizeClusters, variabilityLevel } from "../lib/clusters.js";
import { Empty, Feedback, Panel } from "./UI.jsx";
import StationMap from "./StationMap.jsx";

export function ClusterVisual({ run, members, stations }) {
  const groups = summarizeClusters(members);
  return (
    <div className="cluster-explorer">
      <StationMap stations={stations} clusterMembers={members} />
      <div className="cluster-cards">
        {groups.map(({ label, items, values: v }) => (
          <article
            className="cluster-card"
            key={label}
            style={{ borderTopColor: clusterColor(label) }}
          >
            <h3>
              <i className="dot" style={{ background: clusterColor(label) }} />
              Nhóm {label + 1} · {items.length} trạm
            </h3>
            <h4>{clusterProfile(v)}</h4>
            <p>
              {items
                .map(
                  (m) =>
                    stations.find((s) => s.station_id === m.station_id)?.name ||
                    m.metadata_snapshot?.name ||
                    m.station_id,
                )
                .join("; ")}
            </p>
            <dl>
              <dt>Mức xe thường có</dt>
              <dd>{bikeLevel(v.mean_availability_ratio)}</dd>
              <dt>Độ ổn định số xe</dt>
              <dd>{variabilityLevel(v.std_availability_ratio)}</dd>
              <dt>Thay đổi giữa các lần ghi nhận</dt>
              <dd>{changeLevel(v.mean_abs_change_ratio)}</dd>
              <dt>Tình trạng hết xe</dt>
              <dd>{frequencyLevel(v.empty_ratio)}</dd>
              <dt>Tình trạng còn ít xe</dt>
              <dd>{frequencyLevel(v.low_bikes_ratio)}</dd>
            </dl>
            <h4>Nhịp xe theo giờ New York</h4>
            <dl>
              <dt>Đêm · 00–06 giờ</dt>
              <dd>{bikeLevel(v.night_ratio)}</dd>
              <dt>Sáng · 06–10 giờ</dt>
              <dd>{bikeLevel(v.morning_ratio)}</dd>
              <dt>Ban ngày · 10–16 giờ</dt>
              <dd>{bikeLevel(v.daytime_ratio)}</dd>
              <dt>Chiều tối · 16–24 giờ</dt>
              <dd>{bikeLevel(v.evening_ratio)}</dd>
            </dl>
          </article>
        ))}
      </div>
    </div>
  );
}

function PublishedMembers({ run, stations, previous }) {
  const { revision, refresh } = useApp();
  const members = useResource(
    (signal) => allPages(`/clusters/${run.id}/stations`, {}, signal),
    `map-cluster-members:${run.id}`,
    revision,
  );
  return (
    <>
      {previous && (
        <div className="notice">
          Lượt mới nhất chưa có nhóm hợp lệ. Đang dùng kết quả thành công trước
          đó ngày {run.run_date}.
        </div>
      )}
      <Feedback resource={members} retry={refresh}>
        {(page) => (
          <ClusterVisual run={run} stations={stations} members={page.items} />
        )}
      </Feedback>
    </>
  );
}

export default function ClusterExplorer({ stations }) {
  const { revision, refresh } = useApp();
  const clusters = useResource(
    (signal) => get("/clusters", signal),
    "map-clusters",
    revision,
  );
  return (
    <Panel
      title="Bản đồ nhóm hành vi trạm"
    >
      <Feedback resource={clusters} retry={refresh}>
        {(data) =>
          data.latest_success ? (
            <PublishedMembers
              run={data.latest_success}
              stations={stations}
              previous={data.latest_attempt?.id !== data.latest_success.id}
            />
          ) : (
            <Empty title="Chưa có nhóm trạm được công bố">
              Cần đủ số mẫu và độ phủ để phân cụm; chưa gán màu nhóm khi chưa có
              kết quả hợp lệ.
            </Empty>
          )
        }
      </Feedback>
    </Panel>
  );
}

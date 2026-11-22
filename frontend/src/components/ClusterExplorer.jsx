import { useApp } from "../App.jsx";
import { allPages, get } from "../lib/api.js";
import { useResource } from "../lib/useResource.js";
import { Empty, Feedback, Panel } from "./UI.jsx";
import StationMap from "./StationMap.jsx";

export function ClusterVisual({ members, stations }) {
  return (
    <div className="cluster-explorer">
      <p className="cluster-map-instruction">Bấm vào ghim để xem trạm thuộc nhóm nào.</p>
      <StationMap stations={stations} clusterMembers={members} />
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
          <ClusterVisual stations={stations} members={page.items} />
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

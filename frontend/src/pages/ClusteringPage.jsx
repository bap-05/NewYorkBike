import { useApp, RefreshButton } from "../App.jsx";
import { allPages, get } from "../lib/api.js";
import { number, reasons } from "../lib/data.js";
import { useResource } from "../lib/useResource.js";
import { Badge, Empty, Feedback, PageTitle, Panel } from "../components/UI.jsx";
import { ClusterVisual } from "../components/ClusterExplorer.jsx";

export default function ClusteringPage() {
  const { stations, revision, refresh } = useApp();
  const clusters = useResource(
    (signal) => get("/clusters", signal),
    "clusters",
    revision,
  );

  return (
    <>
      <PageTitle
        title="Phân nhóm trạm"
        description="Xem các trạm có hành vi sử dụng xe tương đồng."
      >
        <RefreshButton />
      </PageTitle>
      <Feedback resource={stations} retry={refresh}>
        {({ items }) => (
          <ClusterResults
            stations={items}
            clusters={clusters}
            retry={refresh}
          />
        )}
      </Feedback>
    </>
  );
}

function ClusterResults({ stations, clusters, retry }) {
  return (
    <Panel title="Nhóm trạm tương đồng">
      <Feedback resource={clusters} retry={retry}>
        {(data) => (
          <>
            {data.latest_attempt && (
              <div className="cluster-meta">
                <Badge value={data.latest_attempt.status} />
                <span>
                  Lượt mới nhất: {data.latest_attempt.run_date} ·{" "}
                  {number(data.latest_attempt.eligible_stations)} trạm đủ điều
                  kiện
                </span>
              </div>
            )}
            {!data.latest_success ? (
              <Empty title="Chưa có nhóm trạm được công bố">
                Lượt chạy hiện chưa tạo được nhóm hợp lệ. Cần đủ ngày, số mẫu và
                độ phủ theo cấu hình; đủ số ngày chưa bảo đảm đạt chất lượng.
                {data.latest_attempt?.reason && (
                  <span className="reason-code">
                    Lý do:{" "}
                    {reasons[data.latest_attempt.reason] ||
                      "Chưa đủ điều kiện phân nhóm"}
                  </span>
                )}
              </Empty>
            ) : (
              <ClusterMembers
                run={data.latest_success}
                stations={stations}
                previous={data.latest_attempt?.id !== data.latest_success.id}
              />
            )}
          </>
        )}
      </Feedback>
    </Panel>
  );
}

function ClusterMembers({ run, stations, previous }) {
  const { revision, refresh } = useApp();
  const members = useResource(
    (signal) => allPages(`/clusters/${run.id}/stations`, {}, signal),
    `cluster-members:${run.id}`,
    revision,
  );
  return (
    <>
      {previous && (
        <div className="notice">
          Lượt mới nhất chưa có nhóm hợp lệ. Đang hiển thị kết quả thành công
          trước đó ngày {run.run_date}.
        </div>
      )}
      <div className="cluster-summary">
        <strong>{number(run.selected_k)} nhóm</strong>
        <span>Điểm tách nhóm: {number(run.silhouette, 3)}</span>
      </div>
      <Feedback resource={members} retry={refresh}>
        {(page) => <ClusterVisual members={page.items} stations={stations} />}
      </Feedback>
    </>
  );
}

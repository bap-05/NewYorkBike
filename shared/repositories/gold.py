"""Only publish Gold rows belonging to a completed, successful analysis run."""
from sqlalchemy import select

from shared.models import AnalysisResult, ClusteringRun, Prediction, ServiceRun, StationCluster


def analysis_results(*, source="citibike", configuration_hash=None):
    query = select(AnalysisResult).join(ServiceRun,
        (ServiceRun.id == AnalysisResult.service_run_id) & (ServiceRun.source == AnalysisResult.source)).where(
        AnalysisResult.source == source, ServiceRun.service_name == "analysis",
        ServiceRun.status == "success", ServiceRun.finished_at.is_not(None))
    if configuration_hash is not None:
        query = query.where(AnalysisResult.configuration_hash == configuration_hash)
    return query


def latest_clustering_run(*, source="citibike", configuration_hash=None, available_at=None):
    """Latest completed success, retaining the previous snapshot after insufficient/failed runs.

    Prediction consumers MUST supply available_at to avoid using a future snapshot.
    """
    query = select(ClusteringRun).join(ServiceRun,
        (ServiceRun.source == ClusteringRun.source) & (ServiceRun.id == ClusteringRun.service_run_id)).where(
        ClusteringRun.source == source, ClusteringRun.status == "success", ClusteringRun.finished_at.is_not(None),
        ServiceRun.service_name == "clustering", ServiceRun.status == "success", ServiceRun.finished_at.is_not(None))
    if configuration_hash is not None:
        query = query.where(ClusteringRun.configuration_hash == configuration_hash)
    if available_at is not None:
        query = query.where(ClusteringRun.finished_at <= available_at, ServiceRun.finished_at <= available_at,
                            ClusteringRun.input_cutoff <= available_at)
    return query.order_by(ClusteringRun.run_date.desc(), ClusteringRun.finished_at.desc(), ClusteringRun.id.desc()).limit(1)


def station_clusters(*, source="citibike", configuration_hash=None, available_at=None):
    latest = latest_clustering_run(source=source, configuration_hash=configuration_hash,
        available_at=available_at).with_only_columns(ClusteringRun.id).scalar_subquery()
    return select(StationCluster).where(StationCluster.source == source,
        StationCluster.clustering_run_id == latest).order_by(StationCluster.station_id)


def predictions(*, source="citibike", available_at=None):
    query = select(Prediction).join(ServiceRun,
        (ServiceRun.source==Prediction.source)&(ServiceRun.id==Prediction.service_run_id)).where(
        Prediction.source==source,ServiceRun.service_name=="prediction",ServiceRun.status=="success",
        ServiceRun.finished_at.is_not(None))
    if available_at is not None:
        query = query.where(Prediction.issued_at<=available_at,ServiceRun.finished_at<=available_at)
    return query

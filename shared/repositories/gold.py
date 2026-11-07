"""Only publish Gold rows belonging to a completed, successful analysis run."""
from sqlalchemy import select

from shared.models import AnalysisResult, ServiceRun


def analysis_results(*, source="citibike", configuration_hash=None):
    query = select(AnalysisResult).join(ServiceRun,
        (ServiceRun.id == AnalysisResult.service_run_id) & (ServiceRun.source == AnalysisResult.source)).where(
        AnalysisResult.source == source, ServiceRun.service_name == "analysis",
        ServiceRun.status == "success", ServiceRun.finished_at.is_not(None))
    if configuration_hash is not None:
        query = query.where(AnalysisResult.configuration_hash == configuration_hash)
    return query

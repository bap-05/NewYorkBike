"""Read-only operational audit. Outputs aggregate evidence, never connection secrets."""
import json
from collections import Counter
from datetime import timedelta
from pathlib import Path
from statistics import median

from sqlalchemy import select
from sqlalchemy.orm import Session

from shared.config import Settings
from shared.database import make_engine
from shared.models import (BikeObservation, CollectionRun, ServiceRun, Station,
                           ClusteringRun, ModelVersion, Prediction, TrainingJob)
from shared.time import utcnow


def main():
    settings = Settings.load(outbound=False)
    engine = make_engine(settings)
    now = utcnow()
    report = {'checked_at_utc': now.isoformat(), 'database_written': False}
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql('SET SESSION TRANSACTION READ ONLY')
            with Session(bind=connection) as session:
                source = settings.bike_source
                report['read_only_verified'] = bool(connection.exec_driver_sql(
                    'SELECT @@session.transaction_read_only').scalar())
                report['services'] = {}
                collections = list(session.scalars(select(CollectionRun).where(
                    CollectionRun.source == source, CollectionRun.started_at >= now - timedelta(hours=4)
                ).order_by(CollectionRun.started_at)))
                report['services']['ingestion'] = summarize(collections, 'scheduled_at')
                for name in ('analysis', 'prediction', 'clustering'):
                    runs = list(session.scalars(select(ServiceRun).where(ServiceRun.source == source,
                        ServiceRun.service_name == name, ServiceRun.started_at >= now - timedelta(
                            days=4 if name == 'clustering' else 0, hours=0 if name == 'clustering' else 4)
                    ).order_by(ServiceRun.started_at)))
                    report['services'][name] = summarize(runs, 'scheduled_at')
                stations = list(session.scalars(select(Station).where(
                    Station.source == source, Station.is_monitored.is_(True))))
                report['stations'] = []
                for station in stations:
                    row = session.scalar(select(BikeObservation).where(BikeObservation.source == source,
                        BikeObservation.station_id == station.station_id).order_by(
                            BikeObservation.sampled_at.desc()).limit(1))
                    report['stations'].append({'station_id': station.station_id, 'name': station.name,
                        'sampled_at': row.sampled_at if row else None,
                        'source_observed_at': row.source_observed_at if row else None,
                        'collected_at': row.collected_at if row else None,
                        'age_seconds': (now - row.source_observed_at).total_seconds()
                            if row and row.source_observed_at else None,
                        'quality_status': row.quality_status if row else None})
                report['latest_clustering'] = [
                    {'id': r.id, 'run_date': r.run_date, 'status': r.status,
                     'version': r.calculation_version, 'summary': r.summary, 'parameters': r.parameters}
                    for r in session.scalars(select(ClusteringRun).where(ClusteringRun.source == source)
                        .order_by(ClusteringRun.started_at.desc()).limit(3))]
                report['models'] = [
                    {'id': m.id, 'kind': m.kind, 'active': m.is_active, 'trained_at': m.trained_at}
                    for m in session.scalars(select(ModelVersion).where(ModelVersion.source == source))]
                report['training_jobs'] = [
                    {'id': r.id, 'status': r.status, 'started_at': r.started_at}
                    for r in session.scalars(select(TrainingJob).where(TrainingJob.source == source)
                        .order_by(TrainingJob.id.desc()).limit(3))]
                report['prediction_evaluation'] = []
                for kind in ('baseline', 'ml'):
                    values = session.execute(select(Prediction.served_absolute_error,
                        Prediction.predicted_bikes, Prediction.actual_bikes).where(
                            Prediction.source == source, Prediction.status == kind,
                            Prediction.actual_bikes.is_not(None))).all()
                    errors = [float(abs(p - a)) for _, p, a in values if p is not None]
                    report['prediction_evaluation'].append({'status': kind, 'evaluated_rows': len(errors),
                        'mae': sum(errors) / len(errors) if errors else None,
                        'rmse': (sum(e * e for e in errors) / len(errors)) ** .5 if errors else None,
                        'note': 'Published forecasts; repeated targets may occur; not an independent test set.'})
                recent = list(session.scalars(select(Prediction).where(Prediction.source == source,
                    Prediction.issued_at >= now - timedelta(hours=1))))
                report['recent_prediction_statuses'] = dict(Counter(r.status for r in recent))
                report['recent_prediction_reasons'] = dict(Counter(r.reason for r in recent))
        path = Path('artifacts/service_audit/database.json')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
        print(json.dumps({'output': str(path), 'read_only_verified': report['read_only_verified'],
                          'services': report['services'], 'evaluation': report['prediction_evaluation']}, default=str))
    finally:
        engine.dispose()


def summarize(rows, logical_time):
    times = [getattr(r, logical_time) for r in rows]
    gaps = [(b - a).total_seconds() for a, b in zip(times, times[1:])]
    return {'count': len(rows), 'latest_started_at': rows[-1].started_at if rows else None,
        'latest_finished_at': rows[-1].finished_at if rows else None,
        'statuses': dict(Counter(r.status for r in rows)),
        'median_interval_seconds': median(gaps) if gaps else None,
        'multiple_configuration_slots': len(times) - len(set(times)),
        'calculation_versions': sorted({r.calculation_version for r in rows if hasattr(r, 'calculation_version')}),
        'recent_runs': [{'id': r.id, 'started_at': r.started_at, 'status': r.status,
                         'attempt_count': r.attempt_count} for r in rows[-5:]]}


if __name__ == '__main__':
    main()

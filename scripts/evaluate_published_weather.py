"""Read-only paired audit of already-issued weather forecasts on new observations."""
from collections import defaultdict
import argparse
from datetime import datetime
import json
from pathlib import Path
from statistics import fmean

from sqlalchemy import select
from sqlalchemy.orm import Session

from shared.config import Settings
from shared.database import make_engine
from shared.models import BikeObservation, ModelVersion, Prediction
from shared.time import utcnow


def metrics(rows):
    if not rows:
        return {'sample_count': 0, 'weather_mae': None, 'weather_rmse': None,
            'baseline_mae': None, 'baseline_rmse': None}
    values = {'sample_count': len(rows)}
    for name in ('weather', 'baseline'):
        errors = [row[name] - row['actual'] for row in rows]
        values[name + '_mae'] = fmean(abs(error) for error in errors)
        values[name + '_rmse'] = fmean(error * error for error in errors) ** .5
    return values


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--since-report', required=True)
    args = parser.parse_args()
    settings = Settings.load(outbound=False)
    cutoff = utcnow()
    # Compare only observations after the last saved offline experiment.
    previous = Path(args.since_report)
    since = datetime.fromisoformat(json.loads(previous.read_text(encoding='utf-8'))['cutoff'])
    engine = make_engine(settings)
    try:
        with engine.connect() as connection:
            if engine.dialect.name == 'mysql':
                connection.exec_driver_sql('SET SESSION TRANSACTION READ ONLY')
                connection.commit()
            with Session(bind=connection) as session:
                models = session.execute(select(ModelVersion.id, ModelVersion.created_at,
                    ModelVersion.is_active, ModelVersion.feature_config).where(
                    ModelVersion.source == settings.bike_source,
                    ModelVersion.kind == 'random_forest')).all()
                weather_models = [m for m in models if m.feature_config.get('with_weather') is True]
                ids = [m.id for m in weather_models]
                pairs = session.execute(select(Prediction.id, Prediction.station_id, Prediction.target_at,
                    Prediction.issued_at, Prediction.model_version_id, Prediction.predicted_bikes,
                    Prediction.actual_bikes, BikeObservation.available_bikes).join(BikeObservation,
                    BikeObservation.id == Prediction.input_observation_id).where(
                    Prediction.source == settings.bike_source, Prediction.status == 'ml',
                    Prediction.model_version_id.in_(ids), Prediction.issued_at >= since,
                    Prediction.issued_at <= cutoff, Prediction.target_at > Prediction.issued_at,
                    Prediction.actual_bikes.is_not(None), Prediction.evaluated_at <= cutoff)
                    .order_by(Prediction.issued_at, Prediction.id)).all()
    finally:
        engine.dispose()
    unique = {}
    for p in pairs:
        unique[(p.station_id, p.target_at)] = dict(prediction_id=p.id, station_id=p.station_id,
            target_at=p.target_at.isoformat(), issued_at=p.issued_at.isoformat(),
            model_id=p.model_version_id, weather=p.predicted_bikes,
            baseline=p.available_bikes, actual=p.actual_bikes)
    rows = list(unique.values())
    groups = defaultdict(list)
    for row in rows:
        groups[row['station_id']].append(row)
    report = dict(database_written=False, model_activated=False, since=since.isoformat(),
        cutoff=cutoff.isoformat(), previous_report=str(previous),
        policy='Same issued input and observed target; latest issuance per station/target; no retraining or backdating.',
        raw_evaluated_forecasts=len(pairs), unique_station_targets=len(rows),
        models=[dict(id=m.id, active=m.is_active, experimental=m.feature_config.get('experimental', False))
            for m in weather_models], metrics=metrics(rows),
        per_station={sid: metrics(values) for sid, values in groups.items()}, observations=rows)
    target = Path('artifacts/prediction_weather_live') / cutoff.strftime('%Y%m%dT%H%M%SZ')
    target.mkdir(parents=True, exist_ok=True)
    (target / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(dict(report=str(target / 'report.json'), metrics=report['metrics'],
        raw_forecasts=len(pairs), since=since.isoformat())))


if __name__ == '__main__':
    main()

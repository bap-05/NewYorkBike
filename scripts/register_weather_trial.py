"""Register an evaluated weather-only trial; activation requires an explicit CLI flag."""
import argparse
from contextlib import ExitStack
from datetime import datetime
import hashlib
import json
from pathlib import Path

from sqlalchemy import select

from prediction.config import PredictionOptions
from prediction.registry import feature_policy
from shared.config import Settings
from shared.database import make_engine, service_session
from shared.models import ModelVersion, Station
from shared.time import utcnow


def candidate(report, artifact, settings, options):
    if report['source']!=settings.bike_source or artifact.get('with_weather') is not True:
        raise ValueError('A weather-enabled model for the current source is required')
    if report.get('status') not in ('experimental','evaluated'):
        raise ValueError('The trial evaluation has not completed')
    if report['local_days']<7 or report['split']['test_samples']<options.min_holdout_samples:
        raise ValueError('Insufficient experimental chronological evaluation')
    metrics=report['models']['with_weather']['test']
    if metrics['sample_count']!=report['baseline']['test']['sample_count']:
        raise ValueError('Weather and baseline evaluation cohorts must match')
    names=set(artifact['feature_names'])
    if not {'temperature','humidity','rain','wind_speed'}.issubset(names):
        raise ValueError('All four weather features are required')
    policy=feature_policy(settings,options)
    identity=hashlib.sha256(json.dumps({'trial':True,'dataset':report['dataset_hash'],
        'artifact':artifact,'policy':policy},sort_keys=True).encode()).hexdigest()
    evaluation={'mae':metrics['mae'],'rmse':metrics['rmse'],'sample_count':metrics['sample_count'],
        'baseline_mae':report['baseline']['test']['mae'],
        'validation_mae':report['models']['with_weather']['validation']['mae']}
    return identity,policy,evaluation


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--report',required=True)
    p.add_argument('--activate',action='store_true')
    args=p.parse_args()
    root=Path(args.report).resolve()
    report=json.loads((root/'report.json').read_text(encoding='utf-8'))
    artifact=json.loads((root/'with_weather.json').read_text(encoding='utf-8'))
    settings,options=Settings.load(outbound=False),PredictionOptions.load()
    identity,policy,evaluation=candidate(report,artifact,settings,options)
    engine=make_engine(settings)
    with ExitStack() as stack:
        session=stack.enter_context(service_session(engine,'training'))
        # Match normal training publication: activate atomically under the training lock.
        # An already-running prediction may finish with its previous model snapshot.
        stations=set(session.scalars(select(Station.station_id).where(Station.source==settings.bike_source,
            Station.is_monitored==True)))
        if stations-set(artifact['station_ids']):
            raise ValueError('The candidate does not cover every monitored station')
        now=utcnow()
        model=session.scalar(select(ModelVersion).where(ModelVersion.source==settings.bike_source,
            ModelVersion.identity_hash==identity))
        if model is None:
            model=ModelVersion(source=settings.bike_source,name='Random Forest thời tiết +30 phút (thử nghiệm)',
                kind='random_forest',identity_hash=identity,created_at=now,trained_at=now,
                # Train-only artifact: validation_start is an exclusive upper bound, not a fabricated last sample time.
                train_end=datetime.fromisoformat(report['split']['validation_start']),
                feature_config={'policy':policy,'with_weather':True,'experimental':True,
                    'feature_names':artifact['feature_names'],'training_end_is_exclusive_bound':True},
                metrics={**report,'deployment_mode':'experimental','trial_evaluation':evaluation,
                    'evaluation_report_path':str(root),'activation_does_not_waive_production_readiness':True},
                artifact=artifact,is_active=False)
            session.add(model)
            session.flush()
        previous=[]
        if args.activate:
            for old in session.scalars(select(ModelVersion).where(ModelVersion.source==settings.bike_source,
                ModelVersion.kind=='random_forest',ModelVersion.is_active==True)):
                previous.append(old.id)
                old.is_active=False
            model.is_active=True
        session.commit()
        receipt={'model_id':model.id,'active':model.is_active,'experimental':True,
            'with_weather':True,'evaluation':evaluation,'previous_active_models':previous,
            'created_at':now.isoformat(),'report_path':str(root)}
        (root/'registration.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
        print(json.dumps(receipt,indent=2),flush=True)
    engine.dispose()


if __name__=='__main__':
    main()

"""Back up and remove only explicitly marked synthetic observations and derived statistics."""
import argparse
from contextlib import ExitStack
import gzip
import json
from pathlib import Path

from sqlalchemy import delete, event, func, or_, select

from shared.config import Settings
from shared.database import ingestion_session, make_engine, service_session
from shared.models import AnalysisResult, Base, BikeObservation, CollectionRun, ObservationWeatherLink, Station, WeatherObservation
from shared.time import utcnow

SOURCE='citibike_estimated'


def contaminated():
    return or_(AnalysisResult.source==SOURCE,AnalysisResult.dimensions['uses_estimated_data'].as_boolean()==True)


def counts(session):
    return {'real_bikes':session.scalar(select(func.count()).select_from(BikeObservation).where(BikeObservation.source!=SOURCE)),
        'weather':session.scalar(select(func.count()).select_from(WeatherObservation)),
        'links':session.scalar(select(func.count()).select_from(ObservationWeatherLink)),
        'real_stations':session.scalar(select(func.count()).select_from(Station).where(Station.source!=SOURCE)),
        'real_runs':session.scalar(select(func.count()).select_from(CollectionRun).where(CollectionRun.source!=SOURCE))}


def remove(session, folder):
    folder.mkdir(parents=True,exist_ok=False)
    before=counts(session)
    ids=select(BikeObservation.id).where(BikeObservation.source==SOURCE)
    queries=[(ObservationWeatherLink,ObservationWeatherLink.bike_observation_id.in_(ids)),
        (AnalysisResult,contaminated()),(BikeObservation,BikeObservation.source==SOURCE),
        (CollectionRun,CollectionRun.source==SOURCE),(Station,Station.source==SOURCE)]
    owned={model.__table__.name for model,_ in queries}
    for table in Base.metadata.sorted_tables:
        if 'source' in table.c and table.name not in owned:
            if session.scalar(select(func.count()).select_from(table).where(table.c.source==SOURCE)):
                raise ValueError('Unexpected dependent estimated data in '+table.name)
    deleted={}
    for model,predicate in queries:
        rows=list(session.scalars(select(model).where(predicate)))
        columns=[c.key for c in model.__table__.columns]
        with gzip.open(folder/(model.__table__.name+'.jsonl.gz'),'wt',encoding='utf-8') as f:
            for row in rows:
                f.write(json.dumps({k:getattr(row,k) for k in columns},default=str,ensure_ascii=False)+'\n')
        deleted[model.__table__.name]=len(rows)
    (folder/'backup_complete.json').write_text(json.dumps({'source':SOURCE,'before':before,'to_delete':deleted},indent=2),encoding='utf-8')
    print('Backup complete:',json.dumps(deleted),flush=True)
    for model,predicate in queries:
        result=session.execute(delete(model).where(predicate).execution_options(synchronize_session=False))
        if result.rowcount!=deleted[model.__table__.name]:
            raise RuntimeError('Deletion count mismatch')
    after=counts(session)
    expected={**before,'links':before['links']-deleted[ObservationWeatherLink.__table__.name]}
    if after!=expected:
        raise RuntimeError('Protected data counts changed; rolling back')
    if session.scalar(select(func.count()).select_from(BikeObservation).where(BikeObservation.source==SOURCE)):
        raise RuntimeError('Estimated observations remain')
    receipt={'deleted':deleted,'before':before,'after':after,'protected_data_preserved':True,'committed':False}
    (folder/'prepared.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    return receipt


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--apply',action='store_true')
    args=p.parse_args()
    if not args.apply:
        p.error('--apply is required for the authorized cleanup')
    engine=make_engine(Settings.load(outbound=False))
    @event.listens_for(engine,'do_connect')
    def timeouts(dialect,record,cargs,params):
        params.update(read_timeout=180,write_timeout=180)
    folder=Path('artifacts/data_cleanup')/utcnow().strftime('%Y%m%dT%H%M%SZ')
    with ExitStack() as stack:
        session=stack.enter_context(ingestion_session(engine))
        for name in ('analysis','prediction','clustering','training'):
            stack.enter_context(service_session(engine,name))
        receipt=remove(session,folder)
        session.commit()
        receipt['committed']=True
        (folder/'receipt.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
        print(json.dumps(receipt,indent=2),flush=True)
        print('Receipt:',folder/'receipt.json',flush=True)
    engine.dispose()


if __name__=='__main__':
    main()

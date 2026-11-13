"""Back up all business rows, hold worker locks, rename, and verify every row checksum."""
import argparse
from collections import Counter
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import time

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import event,inspect,text

from shared.config import ROOT,Settings
from shared.database import make_engine
from shared.time import utcnow


def migration():
    path=ROOT/'database/migrations/versions/0007_vietnamese_names.py'
    spec=importlib.util.spec_from_file_location('rename_names',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def checksum(connection,table,definition,folder=None,order=None):
    names=list(definition['columns'])
    columns=','.join('`'+c+'`' for c in names)
    pk=order or inspect(connection).get_pk_constraint(table).get('constrained_columns') or []
    # Views have no reflected PK. Use the same canonical order as the original tables.
    if not pk:
        pk=['source','station_id'] if table=='stations' else ['source','clustering_run_id','station_id'] if table=='station_clusters' else ['bike_observation_id'] if table=='observation_weather_links' else ['id']
    sql='SELECT '+columns+' FROM `'+table+'` ORDER BY '+','.join('`'+c+'`' for c in pk)
    hasher=hashlib.sha256();count=0
    output=gzip.open(folder/(table+'.jsonl.gz'),'wb') if folder else None
    try:
        result=connection.execution_options(stream_results=True).exec_driver_sql(sql)
        for row in result:
            raw=(json.dumps(list(row),default=str,ensure_ascii=False,separators=(',',':'))+'\n').encode('utf-8')
            hasher.update(raw);count+=1
            if output:output.write(raw)
        result.close()
        connection.execution_options(stream_results=False)
    finally:
        if output:output.close()
    return {'rows':count,'sha256':hasher.hexdigest(),'columns':names,'order':pk}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    module=migration()
    if not args.apply:
        print(json.dumps({old:p['name'] for old,p in module.PLAN.items()}));return
    engine=make_engine(Settings.load(outbound=False))
    @event.listens_for(engine,'do_connect')
    def timeouts(dialect,record,args,parameters):
        parameters['read_timeout']=180;parameters['write_timeout']=180
    folder=ROOT/'artifacts/schema_rename'/utcnow().strftime('%Y%m%dT%H%M%SZ')
    folder.mkdir(parents=True)
    state={'started_at':utcnow().isoformat(),'status':'preparing','backup_path':str(folder),'before':{},'after':{}}
    acquired=[]
    try:
        with engine.connect() as conn:
            try:
                head=conn.exec_driver_sql('SELECT version_num FROM alembic_version').scalar_one()
                if head!='0006_prediction':raise ValueError('Expected the pre-rename schema revision')
                dbhash=hashlib.sha256(str(engine.url.database).encode()).hexdigest()[:32]
                locks=['seoul_ingestion_'+dbhash]+['service_'+name+'_'+dbhash for name in ('analysis','prediction','clustering','training')]
                for lock in locks:
                    deadline=time.monotonic()+180
                    while conn.scalar(text('SELECT GET_LOCK(:name,0)'),{'name':lock})!=1:
                        conn.commit()
                        if time.monotonic()>deadline:raise RuntimeError('A worker did not finish before the maintenance deadline')
                        time.sleep(2)
                    acquired.append(lock);conn.commit()
                print('All worker locks acquired; making full data/schema backup',flush=True)
                inspector=inspect(conn)
                if not set(module.PLAN).issubset(set(inspector.get_table_names())):
                    raise ValueError('Expected the original English physical tables')
                schema={old:conn.exec_driver_sql('SHOW CREATE TABLE `'+old+'`').one()[1] for old in module.PLAN}
                (folder/'schema_before.json').write_text(json.dumps(schema,indent=2)+'\n',encoding='utf-8')
                for old,p in module.PLAN.items():
                    checks={c['name'] for c in inspect(conn).get_check_constraints(old)}
                    if checks!=set(p['checks']):raise ValueError('Unexpected check constraints: '+old)
                    state['before'][old]=checksum(conn,old,p,folder)
                    print('Backed up '+old+': '+str(state['before'][old]['rows'])+' rows',flush=True)
                conn.commit()
                state['status']='backup_complete'
                (folder/'verification.json').write_text(json.dumps(state,indent=2)+'\n',encoding='utf-8')
                print('Applying Vietnamese physical names and compatibility views',flush=True)
                with Operations.context(MigrationContext.configure(conn)):
                    module.upgrade()
                conn.commit()
                for old,p in module.PLAN.items():
                    state['after'][old]=checksum(conn,old,p,order=state['before'][old]['order'])
                    if state['before'][old]!=state['after'][old]:
                        raise ValueError('A data checksum differs after rename: '+old)
                    actual={c['name'] for c in inspect(conn).get_columns(p['name'])}
                    if actual!=set(p['columns'].values()):raise ValueError('Physical columns mismatch: '+p['name'])
                    print('Verified '+p['name']+': '+str(state['after'][old]['rows'])+' rows unchanged',flush=True)
                result=conn.exec_driver_sql("UPDATE alembic_version SET version_num='0007_vietnamese_names' WHERE version_num='0006_prediction'")
                if result.rowcount!=1:raise ValueError('Unexpected migration revision during publication')
                conn.commit()
                state.update(status='success',finished_at=utcnow().isoformat(),revision='0007_vietnamese_names')
                (folder/'verification.json').write_text(json.dumps(state,indent=2)+'\n',encoding='utf-8')
                print(json.dumps({'status':'success','tables':len(module.PLAN),'columns':sum(len(p['columns']) for p in module.PLAN.values()),'verification':str(folder/'verification.json')}),flush=True)
            except Exception as exc:
                state.update(status='failed',error_type=type(exc).__name__)
                (folder/'verification.json').write_text(json.dumps(state,indent=2)+'\n',encoding='utf-8')
                raise
            finally:
                conn.rollback()
                for lock in reversed(acquired):
                    conn.execute(text('SELECT RELEASE_LOCK(:name)'),{'name':lock})
                conn.commit()
    finally:
        engine.dispose()


if __name__=='__main__':main()

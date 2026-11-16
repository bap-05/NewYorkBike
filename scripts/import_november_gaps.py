"""Fill main Citi Bike gaps from real archived snapshots, without overwriting rows."""
import argparse
from collections import Counter, defaultdict
import gzip
import hashlib
import json
from pathlib import Path

import pandas as pd
from sqlalchemy import event, insert, select

from prediction.historical_dataset import normalize_bikes
from scripts.import_historical_prediction import chunks
from shared.config import Settings
from shared.database import ingestion_session, make_engine
from shared.models import BikeObservation, CollectionRun, Station
from shared.time import utcnow


def slot(at):
    return int(at.timestamp()) // 300


def plan(frame, existing):
    occupied = {(r.station_id, slot(r.sampled_at)) for r in existing if r.quality_status == 'valid'}
    exact = {(r.station_id, r.sampled_at) for r in existing}
    return frame.loc[[bool(r.valid) and (r.station_id, slot(r.input_time)) not in occupied
                     and (r.station_id, r.input_time.to_pydatetime()) not in exact
                     for r in frame.itertuples()]].copy()


def snapshot(rows):
    fields = [c.key for c in BikeObservation.__table__.columns]
    return [{k: getattr(r, k) for k in fields} for r in sorted(rows, key=lambda r: r.id)]


def encoded(value):
    return json.dumps(value, default=str, sort_keys=True, ensure_ascii=False).encode('utf-8')


def persist(session, frame, manifest, now):
    # Keep both sources identical so existing Silver/API readers publish these observations.
    groups = defaultdict(list)
    for r in frame.itertuples():
        groups[r.polled_at.to_pydatetime()].append(r)
    run_rows = []
    for at, rows in sorted(groups.items()):
        run = dict(source='citibike', scheduled_at=at, started_at=now,
            finished_at=now, status='success', success_count=len(rows), error_count=0, attempt_count=1,
            feed_metadata={'is_historical': True, 'is_estimated': False, 'original_source': 'citibike',
                'import_type': 'november_archive_gap_fill',
                'imported_at': now.isoformat(), 'dataset_sha256': manifest['sha256'],
                'manifest_path': manifest['path'], 'archive_polled_at': at.isoformat()})
        run_rows.append(run)
    for batch in chunks(run_rows,200):
        session.execute(insert(CollectionRun),batch)
    if not groups:
        return []
    run_ids = dict(session.execute(select(CollectionRun.scheduled_at,CollectionRun.id).where(
        CollectionRun.source=='citibike',CollectionRun.scheduled_at>=min(groups),
        CollectionRun.scheduled_at<=max(groups))).all())
    pending = []
    for at, rows in sorted(groups.items()):
        pending = [dict(source='citibike', station_id=r.station_id, collection_run_id=run_ids[at],
            sampled_at=at, collected_at=at, source_observed_at=r.last_reported.to_pydatetime(),
            available_bikes=int(r.num_bikes_available), available_docks=int(r.num_docks_available),
            is_installed=bool(r.is_installed), is_renting=bool(r.is_renting), is_returning=bool(r.is_returning),
            feed_last_updated=r.ts.to_pydatetime(), quality_status='valid', gbfs_version=None) for r in rows]
        for row in pending:
            row['collection_run_id'] = run_ids[at]
        # Accumulate bounded batches below.
        groups[at] = pending
    all_rows = [row for rows in groups.values() for row in rows]
    for batch in chunks(all_rows,1000):
        session.execute(insert(BikeObservation),batch)
    print('Archive rows prepared:',len(all_rows),flush=True)
    return [run_ids[at] for at in groups]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--directory', required=True)
    p.add_argument('--apply', action='store_true')
    args = p.parse_args()
    paths = sorted(Path(args.directory).glob('2026-11*.parquet'))
    if len(paths) != 10:
        raise ValueError('Expected exactly ten November station files')
    files = {str(path.resolve()): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
    digest = hashlib.sha256(encoded(files)).hexdigest()
    root = Path('artifacts/data_imports') / (utcnow().strftime('%Y%m%dT%H%M%SZ') + '-november-gaps')
    root.mkdir(parents=True)
    manifest = {'files': files, 'sha256': digest, 'path': str((root/'manifest.json').resolve())}
    (root/'manifest.json').write_bytes(encoded(manifest))
    raw = pd.concat([pd.read_parquet(path) for path in paths], ignore_index=True)
    engine = make_engine(Settings.load(outbound=False))
    @event.listens_for(engine, 'do_connect')
    def timeouts(dialect, connection, cargs, params):
        params.update(read_timeout=180, write_timeout=180)
    with ingestion_session(engine) as session:
        ids = set(session.scalars(select(Station.station_id).where(Station.source=='citibike', Station.is_monitored==True)))
        frame, stats = normalize_bikes(raw, start=pd.Timestamp('2026-11-01',tz='UTC'),
            end=min(pd.Timestamp('2026-12-01',tz='UTC'),pd.Timestamp(utcnow())), known_ids=ids)
        first, last = frame.input_time.min().floor('5min').to_pydatetime(), frame.input_time.max().ceil('5min').to_pydatetime()
        query = select(BikeObservation).where(BikeObservation.source=='citibike',
            BikeObservation.sampled_at>=first, BikeObservation.sampled_at<=last)
        old = list(session.scalars(query))
        before = snapshot(old)
        with gzip.open(root/'main_before.json.gz','wb') as f:
            f.write(encoded(before))
        pending = plan(frame, old)
        pending.to_parquet(root/'pending.parquet',index=False)
        counts = Counter(r.input_time.tz_convert('America/New_York').strftime('%Y-%m-%d') for r in pending.itertuples())
        result = {'mode':'apply' if args.apply else 'preview', 'input':stats,
            'existing_main_rows':len(old),'inserted_bikes':len(pending),'by_new_york_day':dict(sorted(counts.items())),
            'first_input_utc':str(frame.input_time.min()),'last_input_utc':str(frame.input_time.max()),
            'manifest':manifest,'weather_added':0}
        print(json.dumps(result,indent=2),flush=True)
        if args.apply and len(pending):
            runs = persist(session,pending,manifest,utcnow())
            session.flush()
            session.expire_all()
            old_ids = {r['id'] for r in before}
            after = list(session.scalars(query))
            if encoded(snapshot([r for r in after if r.id in old_ids])) != encoded(before):
                raise RuntimeError('Original observations changed; transaction must roll back')
            if len(after)-len(before)!=len(pending) or len(plan(frame,after))!=0:
                raise RuntimeError('Import count/idempotence verification failed')
            result.update(inserted_runs=len(runs),original_rows_unchanged=True,idempotence_verified=True)
            # Receipt intent is durable before commit; final receipt confirms successful commit.
            (root/'prepared.json').write_bytes(encoded(result))
            session.commit()
            result['committed']=True
        else:
            session.rollback()
        (root/'receipt.json').write_bytes(encoded(result))
        print('Receipt:',root/'receipt.json',flush=True)
    engine.dispose()


if __name__=='__main__':
    main()

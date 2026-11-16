from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select

from scripts.remove_estimated_data import remove
from shared.models import BikeObservation, CollectionRun, Station


def test_cleanup_only_removes_estimates_is_backed_up_and_can_roll_back(session,tmp_path):
    at=datetime(2026,11,1,tzinfo=timezone.utc)
    for source in ('citibike','citibike_estimated','citibike_historical'):
        session.add(Station(source=source,station_id='TEST',name='Isolated test',
            latitude=Decimal('40.75'),longitude=Decimal('-73.99'),capacity=30,
            is_monitored=source=='citibike',updated_at=at))
        run=CollectionRun(source=source,scheduled_at=at,started_at=at,finished_at=at,
            status='success',success_count=1,error_count=0,attempt_count=1)
        session.add(run)
        session.flush()
        session.add(BikeObservation(source=source,station_id='TEST',collection_run_id=run.id,
            sampled_at=at,collected_at=at,source_observed_at=at,available_bikes=8,
            quality_status='valid' if source!='citibike_estimated' else 'missing'))
    session.commit()
    receipt=remove(session,tmp_path/'backup')
    assert receipt['protected_data_preserved']
    assert receipt['deleted'][BikeObservation.__tablename__]==1
    assert set(session.scalars(select(BikeObservation.source)))=={'citibike','citibike_historical'}
    assert (tmp_path/'backup'/f'{BikeObservation.__tablename__}.jsonl.gz').is_file()
    session.rollback()
    assert session.scalar(select(func.count()).select_from(BikeObservation))==3

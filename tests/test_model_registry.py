from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from sqlalchemy import event

from prediction.config import PredictionOptions
from prediction.registry import active_model, feature_policy
from shared.models import ModelVersion


def test_registry_sorts_ids_without_large_json_and_retains_eligibility_checks(session):
    now=datetime(2026,11,13,tzinfo=timezone.utc)
    settings=SimpleNamespace(weather_max_age_seconds=1800)
    options=PredictionOptions()
    expected=None
    for i,(created,policy) in enumerate(((now-timedelta(days=2),feature_policy(settings,options)),
        (now-timedelta(days=1),{'version':'incompatible'}),(now+timedelta(days=1),feature_policy(settings,options)))):
        row=ModelVersion(source='citibike',name='Isolated registry test',kind='random_forest',
            identity_hash=str(i).zfill(64),created_at=created,train_end=now-timedelta(days=3),
            feature_config={'policy':policy},metrics={},artifact={'large_payload':'x'*400000},is_active=True)
        session.add(row)
        if expected is None:expected=row
    session.commit()
    expected_id=expected.id
    session.expunge_all()
    queries=[]
    def capture(connection,cursor,statement,parameters,context,executemany):
        queries.append(statement)
    engine=session.get_bind()
    event.listen(engine,'before_cursor_execute',capture)
    try:
        selected=active_model(session,'citibike',now,settings,options)
    finally:
        event.remove(engine,'before_cursor_execute',capture)
    assert selected.id==expected_id and len(selected.artifact['large_payload'])==400000
    ordered=[q for q in queries if 'ORDER BY' in q and ModelVersion.__tablename__ in q]
    assert ordered
    assert all(ModelVersion.__table__.c.artifact.name not in q.split('FROM')[0] for q in ordered)

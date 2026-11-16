"""Only the explicit Vietnamese-name successor may use the legacy-view bridge."""
import pytest
from sqlalchemy import create_engine,text
from shared.models import Base,Station
from shared import schema


@pytest.mark.parametrize('head,accepted', [('0006_prediction',True),('0007_vietnamese_names',True),('unknown-future-head',False)])
def test_explicit_successor_and_legacy_columns_are_required(monkeypatch,head,accepted):
    engine=create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text('CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)'))
        conn.execute(text('INSERT INTO alembic_version VALUES (:head)'),{'head':head})
    monkeypatch.setattr(schema,'make_engine',lambda _:engine)
    monkeypatch.setattr(engine,'dispose',lambda:None)
    if accepted:
        schema.check_schema(None,required_revision='0003_bronze',models=(Station,))
    else:
        with pytest.raises(Exception):
            schema.check_schema(None,required_revision='0003_bronze',models=(Station,))

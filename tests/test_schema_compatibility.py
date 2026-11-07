import pytest
from sqlalchemy import create_engine, text

from shared import schema
from shared.models import Base, Station, BikeObservation, CollectionRun, WeatherObservation, ObservationWeatherLink


@pytest.mark.parametrize("revision,required,allowed", [
    ("0003_bronze","0003_bronze",True),
    ("0004_analysis","0003_bronze",True),
    ("0003_bronze","0004_analysis",False),
    ("0004_analysis","0004_analysis",True),
    ("0002_citibike","0003_bronze",False),
])
def test_service_requires_its_own_minimum_revision(monkeypatch,revision,required,allowed):
    engine=create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)"))
        connection.execute(text("INSERT INTO alembic_version VALUES (:revision)"),{"revision":revision})
    monkeypatch.setattr(schema,"make_engine",lambda settings:engine)
    models=(Station,BikeObservation,CollectionRun,WeatherObservation,ObservationWeatherLink)
    if allowed:
        schema.check_schema(None,required_revision=required,models=models)
    else:
        with pytest.raises(ValueError,match="minimum revision"):
            schema.check_schema(None,required_revision=required,models=models)

"""Lightweight identities shared by the EDA publisher and read-only API."""
import hashlib
import json

VERSION = 'eda-db-v1'
SNAPSHOT_SERVICE = 'eda_snapshot'
PUBLISHER_SERVICE = 'eda'
WINDOWS = (28, 60, 90)
KINDS = ('trend', 'seasonality', 'correlation', 'decomposition')


def snapshot_key(source, kind, days, station_id=None):
    config = dict(source=source, kind=kind, days=days, station_id=station_id)
    return hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()


def empty_chart(source, kind):
    return dict(source=source, data_source='database', storage='precomputed', chart=kind,
        status='missing', stations=[], raw_rows=0, daily=[], weekly=[], monthly=[],
        correlation=[], decomposition=[], decomposition_status=[])

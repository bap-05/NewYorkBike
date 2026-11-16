from decimal import Decimal
from types import SimpleNamespace

import pandas as pd
import pytest

from scripts.link_november_weather import weather_values


def test_archive_weather_keeps_product_retrieval_time_units_and_location():
    station=SimpleNamespace(latitude=Decimal('40.75'),longitude=Decimal('-73.99'))
    row=SimpleNamespace(temperature=10.,humidity=60.,rain=0.,wind_speed=2.,weather_time=pd.Timestamp('2026-11-01',tz='UTC'))
    cache={'endpoint':'https://archive-api.open-meteo.com/v1/archive',
        'request':{'models':'era5','latitude':'40.75','longitude':'-73.99'},'retrieved_at':'2026-11-13T16:00:00Z',
        'payload':{'latitude':40.75,'longitude':-73.99,'hourly_units':{'temperature_2m':'\u00b0C',
            'relative_humidity_2m':'%','rain':'mm','wind_speed_10m':'m/s'}}}
    r=weather_values(row,station,cache)
    assert r['source']=='open-meteo-era5' and r['collected_at']>r['weather_time']
    assert r['interval_seconds']==3600 and r['collection_run_id'] is None
    cache['endpoint']='https://historical-forecast-api.open-meteo.com/v1/forecast'
    cache['request']['models']='ecmwf_ifs'
    assert weather_values(row,station,cache)['source']=='open-meteo-historical-forecast'
    row.rain=float('nan')
    assert weather_values(row,station,cache) is None
    row.rain=-1
    with pytest.raises(ValueError,match='physical ranges'):
        weather_values(row,station,cache)
    cache['request']['latitude']='40.0'
    with pytest.raises(ValueError,match='location'):
        weather_values(row,station,cache)

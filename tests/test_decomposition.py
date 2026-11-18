"""Isolated signals validate decomposition and missing-data/DST quality gates."""
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from eda.decomposition import decompose, generate_decomposition_plots, MIN_HOURS
from shared.cadence import SamplingCadence

STATION = SimpleNamespace(station_id='test-station', name='Test station')


def signal(hours=240, start='2026-11-03T00:00:00Z'):
    begin = pd.Timestamp(start)
    at = pd.date_range(begin, periods=hours, freq='h')
    values = 20 + .02*np.arange(hours) + 4*np.sin(2*np.pi*np.arange(hours)/24)
    frame = pd.DataFrame(dict(station_id=STATION.station_id, source='citibike',
        sampled_at=at+pd.Timedelta(minutes=5), available_bikes=values,
        slot_latest=True, bike_usable=True))
    return frame, begin, begin+pd.Timedelta(hours=hours)


def test_stl_recovers_signal_and_reconstructs_observations_without_writes(tmp_path):
    frame, start, end = signal()
    original = frame.copy(deep=True)
    results, values = decompose(frame, [STATION], SamplingCadence(3600), start, end)
    item = results[0]
    assert item['status'] == 'available' and item['selected_hours'] == 240
    assert item['imputed_hours'] == 0 and item['retrospective_only']
    np.testing.assert_allclose(values.observed, values.trend+values.seasonal+values.residual, atol=1e-10)
    assert np.corrcoef(values.seasonal, 4*np.sin(2*np.pi*np.arange(240)/24))[0,1] > .99
    pd.testing.assert_frame_equal(frame, original)
    figures = generate_decomposition_plots(results, values, tmp_path)
    assert figures[0]['station_id'] == STATION.station_id
    assert (tmp_path / figures[0]['file'].split('/')[-1]).read_bytes().startswith(b'\x89PNG')


def test_gap_is_not_interpolated_and_short_recent_tail_does_not_hide_covered_history():
    frame, start, end = signal(hours=MIN_HOURS+1+80)
    frame.loc[MIN_HOURS, 'bike_usable'] = False
    results, values = decompose(frame, [STATION], SamplingCadence(3600), start, end)
    assert results[0]['selected_hours'] == MIN_HOURS
    assert values.hour_utc.max() == start+pd.Timedelta(hours=MIN_HOURS-1)
    assert results[0]['imputed_hours'] == 0
    frame.loc[80, 'bike_usable'] = False
    results, values = decompose(frame, [STATION], SamplingCadence(3600), start, end)
    assert results[0]['status'] == 'insufficient_data' and values.empty


@pytest.mark.parametrize('samples,available', [(9, False), (10, True)])
def test_hour_requires_eighty_percent_of_declared_samples(samples, available):
    frame, start, end = signal(hours=168)
    at = pd.date_range(start, end, freq='5min', inclusive='left')
    expanded = pd.DataFrame(dict(station_id=STATION.station_id, source='citibike',
        sampled_at=at, available_bikes=0., slot_latest=True, bike_usable=True))
    hour = expanded.sampled_at.dt.floor('h') == start+pd.Timedelta(hours=80)
    expanded.loc[expanded.index[hour][samples:], 'bike_usable'] = False
    results, values = decompose(expanded, [STATION], SamplingCadence(300), start, end)
    assert (results[0]['status'] == 'available') == available
    if available:
        assert np.isfinite(values.residual).all()
        np.testing.assert_allclose(values.observed, 0)


def test_dst_is_a_segment_boundary_and_estimates_cannot_repair_missing_real_hours():
    frame, start, end = signal(hours=240, start='2026-10-31T00:00:00Z')
    results, values = decompose(frame, [STATION], SamplingCadence(3600), start, end)
    assert results[0]['status'] == 'available'
    assert values.hour_utc.min() == pd.Timestamp('2026-11-01T06:00:00Z')
    offsets = values.hour_utc.map(lambda at: at.tz_convert('America/New_York').utcoffset())
    assert offsets.nunique() == 1
    frame.loc[frame.index >= 40, 'source'] = 'citibike_estimated'
    results, values = decompose(frame, [STATION], SamplingCadence(3600), start, end)
    assert results[0]['status'] == 'insufficient_data' and values.empty

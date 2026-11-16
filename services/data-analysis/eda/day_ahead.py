"""Pure read-only day-ahead calculation, shared with the publishing worker."""
from datetime import timedelta
from zoneinfo import ZoneInfo

from analysis.config import AnalysisOptions
from eda.dataset import load_frame, mark_latest_slots
from eda.patterns import calendar_patterns
from eda.report import json_safe
from eda.statistics import daily_coverage
from eda.weekday_forecast import update_forecasts
from shared.cadence import SamplingCadence

ZONE = ZoneInfo('America/New_York')


def build_report(session, settings, cutoff, options=None):
    options = options or AnalysisOptions.load()
    cadence = SamplingCadence(options.expected_interval_seconds, options.sampling_schedule)
    start = cutoff - timedelta(days=28)
    frame, stations, firsts = load_frame(session, settings, options, start, cutoff,
        200000, include_weather=False)
    frame = mark_latest_slots(frame, cadence)
    coverage = daily_coverage(frame, stations, firsts, cadence, options, start, cutoff)
    patterns = calendar_patterns(frame, coverage, stations, cutoff, cadence)
    forecasts = update_forecasts(frame, patterns['daily'], stations, cutoff, cadence,
        patterns['day_ahead']['items'])
    return json_safe({'source': settings.bike_source,
        'generated_at': {'utc': cutoff.isoformat(), 'local': cutoff.astimezone(ZONE).isoformat()},
        'target_date': (cutoff.astimezone(ZONE).date() + timedelta(days=1)).isoformat(),
        'day_ahead': forecasts})

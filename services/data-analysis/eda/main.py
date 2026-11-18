"""Read-only EDA generation, manually or through the API background worker."""
import argparse
from datetime import datetime, timedelta
import json
import logging
from pathlib import Path

from sqlalchemy.orm import Session

from analysis.config import AnalysisOptions
from eda.dataset import load_frame, mark_latest_slots
from eda.plots import generate_plots
from eda.decomposition import decompose, generate_decomposition_plots
from eda.patterns import calendar_patterns, generate_pattern_plots
from eda.report import json_safe, write_report
from eda.forecast_inputs import load_forecast_estimates
from eda.statistics import (correlation_tables, daily_coverage, descriptive_statistics,
    missingness, outlier_flags, scaling_comparison, temporal_profiles)
from shared.cadence import SamplingCadence
from shared.config import Settings
from shared.database import make_engine
from shared.logging_config import configure_logging
from shared.time import as_utc, display_time, utcnow

logger = logging.getLogger('eda')


def create_report(settings, options, *, start, cutoff, output, max_rows=100000):
    output = Path(output).resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError('EDA output must be a new or empty directory; previous reports are preserved')
    cadence = SamplingCadence(options.expected_interval_seconds, options.sampling_schedule)
    engine = make_engine(settings)
    read_only_enforced = False
    try:
        with engine.connect() as connection:
            if engine.dialect.name == 'mysql':
                connection.exec_driver_sql('SET SESSION TRANSACTION READ ONLY')
                connection.commit()
                read_only_enforced = connection.exec_driver_sql('SELECT @@session.transaction_read_only').scalar() == 1
                if not read_only_enforced:
                    raise RuntimeError('MySQL did not enforce read-only access')
            with Session(bind=connection) as session:
                frame, stations, firsts = load_frame(session, settings, options, start, cutoff, max_rows)
                forecast_estimates = load_forecast_estimates(session, stations, start, cutoff)
        # Close the database before any plotting/scaling/file export.
    finally:
        engine.dispose()
    frame = mark_latest_slots(frame, cadence)
    coverage = daily_coverage(frame, stations, firsts, cadence, options, start, cutoff)
    quality = missingness(frame, stations)
    scaled, scaling_info = scaling_comparison(frame)
    tables = {'coverage': coverage, 'missingness': quality,
        'descriptive': descriptive_statistics(frame), 'outliers': outlier_flags(frame, cadence),
        'correlations': correlation_tables(frame), 'scaled': scaled, 'scaling_info': scaling_info,
        **temporal_profiles(frame)}
    tables.update(calendar_patterns(frame, coverage, stations, cutoff, cadence, forecast_estimates))
    decomposition, components = decompose(frame, stations, cadence, start, cutoff, options.timezone_name)
    tables['decomposition'] = components
    usable = frame.loc[frame.slot_latest & frame.bike_usable]
    summary = {'version': 'eda-v1', 'generated_at_utc': utcnow().isoformat(),
        'source': settings.bike_source, 'timezone': options.timezone_name,
        'window_start_utc': start.isoformat(), 'cutoff_utc': cutoff.isoformat(),
        'window_start_local': display_time(start), 'cutoff_local': display_time(cutoff),
        'database_written': False, 'model_trained': False, 'station_count': len(stations),
        'mysql_read_only_enforced': read_only_enforced,
        'raw_rows': len(frame), 'deduplicated_rows': int(frame.slot_latest.sum()),
        'input_sources': {str(source):int(count) for source,count in frame.source.value_counts().items()},
        'historical_import_policy': 'Real citibike_historical observations included for retrospective EDA; current source wins overlapping slots; estimates excluded.',
        'usable_bike_rows': len(usable),
        'usable_bikes_without_usable_weather': int((~usable.weather_usable).sum()),
        'outlier_flag_count': len(tables['outliers']),
        'outlier_observation_count': int(tables['outliers'].observation_id.nunique()),
        'analysis_quality_configuration': options.as_dict(),
        'unavailable_requested_station_ids': sorted(set(settings.station_ids) - {s.station_id for s in stations}),
        'aggregation_policy': 'sample_weighted_after_slot_deduplication',
        'statistical_units': {'available_bikes': 'bikes', 'available_docks': 'docks',
            'temperature': 'C', 'humidity': '%', 'rain': 'mm per source interval', 'wind_speed': 'm/s'},
        'capacity_policy': 'current_metadata_snapshot_not_historical_capacity',
        'scaling': scaling_info, 'day_ahead': tables['day_ahead'], 'decomposition': decomposition}
    output.mkdir(parents=True, exist_ok=True)
    figures = generate_plots(frame, stations, tables, cadence, output / 'figures')
    figures += generate_pattern_plots(frame, stations, tables, cadence, cutoff, output / 'figures')
    figures += generate_decomposition_plots(decomposition, components, output / 'figures', options.timezone_name)
    write_report(output, frame, tables, summary, figures)
    logger.info('EDA complete: stations=%s raw_rows=%s usable_bike_rows=%s flags=%s',
        len(stations), len(frame), len(usable), len(tables['outliers']))
    logger.info('Read-only report=%s', output / 'report.html')
    return json_safe(summary)


def main():
    parser = argparse.ArgumentParser(description='Read-only Citi Bike EDA; no source API calls or database writes')
    parser.add_argument('--days', type=int, default=28, help='Look back this many elapsed days, from 1 to 90')
    parser.add_argument('--from', dest='start', help='Optional ISO start with explicit timezone offset')
    parser.add_argument('--to', dest='cutoff', help='Optional ISO cutoff with explicit timezone offset')
    parser.add_argument('--output', help='New/empty output directory; default artifacts/eda/<UTC timestamp>')
    parser.add_argument('--max-rows', type=int, default=100000)
    parser.add_argument('--auto-once', action='store_true', help='Refresh only if inputs changed; --output is the report root')
    args = parser.parse_args()
    configure_logging('America/New_York')
    try:
        if not 1 <= args.days <= 90 or not 1 <= args.max_rows <= 1000000:
            raise ValueError('Days must be in [1,90] and max-rows in [1,1000000]')
        now = utcnow()
        cutoff = as_utc(datetime.fromisoformat(args.cutoff.replace('Z', '+00:00'))) if args.cutoff else now
        start = as_utc(datetime.fromisoformat(args.start.replace('Z', '+00:00'))) if args.start else cutoff - timedelta(days=args.days)
        if not start < cutoff <= now or cutoff - start > timedelta(days=90):
            raise ValueError('EDA requires a past range no longer than 90 days')
        settings = Settings.load(outbound=False)
        options = AnalysisOptions.load()
        if args.auto_once:
            if args.start or args.cutoff:
                raise ValueError('Automatic EDA uses a rolling window')
            from eda.automatic import refresh_report
            refresh_report(settings, options, root=args.output or 'artifacts/eda',
                days=args.days, max_rows=args.max_rows)
            return 0
        output = args.output or f'artifacts/eda/{now.strftime("%Y%m%dT%H%M%S%fZ")}'
        create_report(settings, options, start=start, cutoff=cutoff, output=output, max_rows=args.max_rows)
        return 0
    except Exception as exc:
        # Never emit SQLAlchemy exceptions, settings or connection strings.
        logger.error('EDA failed (%s). Check dependencies, MySQL/TLS, date range, row limit and empty output directory.', type(exc).__name__)
        return 1
    except KeyboardInterrupt:
        logger.info('EDA stopped')
        return 130


if __name__ == '__main__':
    raise SystemExit(main())

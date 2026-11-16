"""Explicit response contracts: never serialize ORM internals or model payloads."""
from datetime import date
from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict


class Contract(BaseModel):
    model_config=ConfigDict(extra='forbid')


class TimeValue(Contract):
    utc: AwareDatetime
    local: AwareDatetime


class Meta(Contract):
    source: str
    timezone: Literal['America/New_York']='America/New_York'
    as_of: TimeValue


class Pagination(Contract):
    total: int
    limit: int
    offset: int
    has_more: bool


class BikeView(Contract):
    id: int
    sampled_at: TimeValue
    collected_at: TimeValue
    source_observed_at: TimeValue|None
    available_bikes: int|None
    available_docks: int|None
    is_installed: bool|None
    is_renting: bool|None
    is_returning: bool|None
    quality_status: str
    availability_status: Literal['fresh','stale','inactive','missing','invalid','unknown']
    is_current: bool
    age_seconds: float|None


class WeatherView(Contract):
    id: int
    source: str
    weather_time: TimeValue
    collected_at: TimeValue
    interval_seconds: int
    units: dict[str,Any]
    requested_latitude: float
    requested_longitude: float
    temperature: float|None
    humidity: float|None
    rain: float|None
    wind_speed: float|None
    status: Literal['fresh','stale','partial','invalid']
    age_seconds: float


class ModelEvaluation(Contract):
    mae: float
    rmse: float
    sample_count: int
    baseline_mae: float
    validation_mae: float


class ModelView(Contract):
    id: int
    name: str
    kind: str
    trained_at: TimeValue|None
    experimental: bool = False
    with_weather: bool = False
    evaluation: ModelEvaluation|None = None


class PredictionView(Contract):
    id: int
    status: Literal['baseline','ml','unavailable']
    reason: str|None
    input_time: TimeValue|None
    input_source_observed_at: TimeValue|None
    input_cutoff_at: TimeValue
    target_at: TimeValue|None
    issued_at: TimeValue
    predicted_bikes: float|None
    raw_predicted_bikes: float|None
    model: ModelView|None
    weather_inputs: dict[str,float]|None = None
    is_current: bool
    display_reason: str|None
    actual_bikes: int|None
    actual_time: TimeValue|None
    target_offset_seconds: float|None
    evaluated_at: TimeValue|None
    absolute_error: float|None
    squared_error: float|None


class StationView(Contract):
    source: str
    station_id: str
    name: str
    latitude: float
    longitude: float
    capacity: int|None
    is_monitored: bool
    metadata_updated_at: TimeValue
    availability_status: str
    latest_observation: BikeView|None
    latest_weather: WeatherView|None


class StationDetail(StationView):
    latest_prediction: PredictionView|None


class StationPage(Contract):
    meta: Meta
    pagination: Pagination
    items: list[StationView]


class StationResponse(Contract):
    meta: Meta
    item: StationDetail


class HistoryItem(Contract):
    observation: BikeView
    weather: WeatherView|None
    is_estimated: bool = False
    estimation_method: Literal['linear_interpolation','same_hour_median']|None = None


class HistoryPage(Contract):
    meta: Meta
    pagination: Pagination
    items: list[HistoryItem]


class PredictionPage(Contract):
    meta: Meta
    pagination: Pagination
    items: list[PredictionView]


class LatestPredictionResponse(Contract):
    meta: Meta
    item: PredictionView|None
    status: Literal['available','unavailable','missing']


class AnalysisView(Contract):
    id: int
    station_id: str
    aggregation: str
    metric_name: str
    metric_value: float|None
    sample_count: int
    observed_sample_count: int
    expected_sample_count: int
    coverage: float|None
    quality_status: str
    dimensions: dict[str,Any]
    window_start: TimeValue
    window_end: TimeValue
    input_cutoff: TimeValue
    calculated_at: TimeValue
    configuration_hash: str
    calculation_version: str


class AnalysisPage(Contract):
    meta: Meta
    pagination: Pagination
    configuration_hash: str|None
    items: list[AnalysisView]


class ClusterRunView(Contract):
    id: int
    run_date: date
    status: str
    window_start: TimeValue
    window_end: TimeValue
    finished_at: TimeValue|None
    algorithm: str
    calculation_version: str
    configuration_hash: str
    selected_k: int|None
    silhouette: float|None
    feature_names: list[str]
    eligible_stations: int|None
    reason: str|None


class ClusterMember(Contract):
    station_id: str
    cluster_label: int
    distance_to_centroid: float
    feature_values: dict[str,Any]
    metadata_snapshot: dict[str,Any]
    sample_count: int
    expected_sample_count: int
    coverage: float


class ClusterResponse(Contract):
    meta: Meta
    status: str
    latest_attempt: ClusterRunView|None
    latest_success: ClusterRunView|None


class ClusterPage(Contract):
    meta: Meta
    pagination: Pagination
    run: ClusterRunView
    items: list[ClusterMember]


class ServiceState(Contract):
    service_name: str
    last_attempt_id: int|None
    last_attempt_status: str|None
    last_attempt_started_at: TimeValue|None
    last_completed_at: TimeValue|None


class Overview(Contract):
    meta: Meta
    station_count: int
    observation_status_counts: dict[str,int]
    fresh_available_bikes: int|None
    fresh_empty_station_count: int
    fresh_low_bike_station_count: int
    services: list[ServiceState]
    map_center: dict[str,float]


class EdaFigure(Contract):
    filename: str
    title: str
    url: str


class EdaStatistic(Contract):
    station_id: str
    column: str
    count: int
    mean: float|None
    median: float|None
    std_population: float|None
    mode_values: list[float]
    mode_count: int
    modes_truncated: bool


class HourAheadForecast(Contract):
    seasonal_bikes: float|None = None
    recent_adjustment: float|None = None
    forecast_method: str|None = None
    support_dates: list[str] = []
    target_start_utc: str
    target_end_utc: str
    local_hour: int
    hour_label: str
    status: Literal['available', 'insufficient_data']
    reason: str|None
    history_days: int
    predicted_mean_bikes: float|None
    availability_class: Literal['low', 'balanced', 'high']|None
    evaluation_samples: int
    evaluation_status: Literal['available', 'insufficient_data']
    mae: float|None
    rmse: float|None
    classification_accuracy: float|None
    uses_estimated_data: bool = False
    input_estimated_samples: int = 0
    input_actual_samples: int = 0


class RecentForecastInputs(Contract):
    latest_bikes: float
    latest_at: str
    recent_samples: int
    recent_coverage: float
    recent_mean_bikes: float|None
    latest_delta: float|None
    recent_delta: float|None
    hourly_trend: float|None
    daily_trend: float|None
    weekly_shift: float|None
    weekly_reference_days: int


class ForecastScore(Contract):
    samples: int
    mae: float|None
    rmse: float|None


class CandidateForecastScore(Contract):
    validation: ForecastScore
    test: ForecastScore


class ForecastSelection(Contract):
    target_date: str
    model: str
    validation_dates: list[str]


class IssuedHourEvaluation(Contract):
    publication_id: int
    issued_at: str|None
    station_id: str
    target_start_utc: str
    target_end_utc: str
    hour_label: str
    status: Literal['pending','awaiting_data','not_forecast','available']
    predicted_bikes: float|None
    actual_bikes: float|None
    absolute_error: float|None
    squared_error: float|None
    classification_correct: bool|None
    coverage: float|None
    evaluated_at: str|None


class IssuedEvaluation(Contract):
    scored_hours: int
    pending_hours: int
    awaiting_data_hours: int
    not_forecast_hours: int
    mae: float|None
    rmse: float|None
    classification_accuracy: float|None
    items: list[IssuedHourEvaluation]


class DayAheadForecast(Contract):
    issued_evaluation: IssuedEvaluation|None = None
    confidence: Literal['low','limited']|None = None
    confidence_reasons: list[str] = []
    selection_history: list[ForecastSelection] = []
    recent_inputs: RecentForecastInputs|None = None
    candidate_scores: dict[str,CandidateForecastScore] = {}
    persistence_test_mae: float|None = None
    persistence_test_rmse: float|None = None
    selected_model: str|None = None
    model_label: str|None = None
    selection_status: str|None = None
    validation_days: int = 0
    test_days: int = 0
    validation_mae: float|None = None
    baseline_validation_mae: float|None = None
    test_mae: float|None = None
    test_rmse: float|None = None
    baseline_test_mae: float|None = None
    baseline_test_rmse: float|None = None
    station_id: str
    station_name: str
    status: Literal['available', 'insufficient_data']
    reason: str|None
    target_date: str
    target_start_utc: str
    target_end_utc: str
    input_cutoff_utc: str
    capacity: int|None
    qualified_days: int
    predicted_mean_bikes: float|None
    availability_class: Literal['low', 'balanced', 'high']|None
    evaluation_samples: int
    evaluation_status: Literal['available', 'insufficient_data']
    mae: float|None
    rmse: float|None
    classification_accuracy: float|None
    hourly_forecasts: list[HourAheadForecast] = []
    low_bike_hours: list[str] = []
    actual_qualified_days: int|None = None
    uses_estimated_data: bool = False
    input_estimated_samples: int = 0
    input_actual_samples: int = 0


class DayAheadReport(Contract):
    publication_id: int|None = None
    persisted: bool = False
    issued_at: TimeValue|None = None
    source: str
    generated_at: TimeValue
    target_date: str
    day_ahead: list[DayAheadForecast]


class DayAheadHistory(Contract):
    station_id: str
    station_name: str
    issued_evaluation: IssuedEvaluation


class DayAheadResponse(Contract):
    status: Literal['available','missing']
    item: DayAheadReport|None
    history: list[DayAheadHistory] = []


class EdaReport(Contract):
    report_id: str
    source: str
    input_sources: dict[str,int] = {}
    generated_at: TimeValue
    window_start: TimeValue
    cutoff: TimeValue
    station_count: int
    raw_rows: int
    deduplicated_rows: int
    usable_bike_rows: int
    usable_bikes_without_usable_weather: int
    outlier_flag_count: int
    outlier_observation_count: int
    figures: list[EdaFigure]
    statistics: list[EdaStatistic]
    day_ahead: list[DayAheadForecast] = []


class EdaResponse(Contract):
    status: Literal['available','missing']
    item: EdaReport|None


class CalendarPoint(Contract):
    at: AwareDatetime
    value: int|None
    gap_before: bool


class CalendarStation(Contract):
    station_id: str
    name: str
    capacity: int|None
    points: list[CalendarPoint]


class CalendarSeries(Contract):
    source: str
    period: Literal['day', 'week', 'month']
    anchor: str
    timezone: str
    range_start_utc: AwareDatetime
    range_end_utc: AwareDatetime
    available_until_utc: AwareDatetime
    partial_period: bool
    raw_rows: int
    items: list[CalendarStation]

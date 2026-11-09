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


class ModelView(Contract):
    id: int
    name: str
    kind: str
    trained_at: TimeValue|None


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

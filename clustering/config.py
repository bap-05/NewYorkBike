from dataclasses import asdict, dataclass
import math
import os

from shared.config import integer


@dataclass(frozen=True)
class ClusteringOptions:
    window_days: int = 7
    expected_interval_seconds: int = 1800
    min_samples: int = 200
    min_daily_coverage: float = 0.8
    min_stations: int = 6
    max_clusters: int = 4
    low_bike_threshold: int = 3
    timezone_name: str = "America/New_York"

    def __post_init__(self):
        if not 7 <= self.window_days <= 31:
            raise ValueError("Clustering requires 7 to 31 completed calendar days")
        if not 60 <= self.expected_interval_seconds <= 3600 or 3600 % self.expected_interval_seconds:
            raise ValueError("Clustering collection interval must divide 3600, in [60,3600]")
        if not math.isfinite(self.min_daily_coverage) or not 0.5 <= self.min_daily_coverage <= 1:
            raise ValueError("Clustering daily coverage must be in [0.5,1]")
        if not 2 <= self.min_samples <= 50000 or not 4 <= self.min_stations <= 10000:
            raise ValueError("Invalid clustering sample/station minimum")
        if not 2 <= self.max_clusters <= 20 or not 0 <= self.low_bike_threshold <= 1000:
            raise ValueError("Invalid clustering maximum groups/low-bike threshold")
        if self.timezone_name != "America/New_York":
            raise ValueError("Clustering calendar timezone must be America/New_York")

    @classmethod
    def load(cls):
        return cls(
            window_days=integer("CLUSTERING_WINDOW_DAYS", 7, 7, 31),
            expected_interval_seconds=integer("CLUSTERING_EXPECTED_INTERVAL_SECONDS", 1800, 60, 3600),
            min_samples=integer("CLUSTERING_MIN_SAMPLES", 200, 2, 50000),
            min_daily_coverage=float(os.getenv("CLUSTERING_MIN_DAILY_COVERAGE", "0.8")),
            min_stations=integer("CLUSTERING_MIN_STATIONS", 6, 4, 10000),
            max_clusters=integer("CLUSTERING_MAX_CLUSTERS", 4, 2, 20),
            low_bike_threshold=integer("CLUSTERING_LOW_BIKE_THRESHOLD", 3, 0, 1000))

    def as_dict(self):
        return asdict(self)

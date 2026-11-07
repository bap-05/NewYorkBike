from dataclasses import asdict, dataclass
import os

from shared.config import integer


@dataclass(frozen=True)
class AnalysisOptions:
    window_days: int = 7
    expected_interval_seconds: int = 1800
    low_bike_threshold: int = 3
    min_samples: int = 2
    min_coverage: float = 0.8
    ingestion_grace_seconds: int = 120
    timezone_name: str = "America/New_York"

    def __post_init__(self):
        if not 1 <= self.window_days <= 31:
            raise ValueError("ANALYSIS_WINDOW_DAYS must be in [1,31]")
        if not 60 <= self.expected_interval_seconds <= 3600 or 3600 % self.expected_interval_seconds:
            raise ValueError("ANALYSIS_EXPECTED_INTERVAL_SECONDS must divide 3600 and be in [60,3600]")
        if not 0 <= self.low_bike_threshold <= 1000 or not 1 <= self.min_samples <= 10000:
            raise ValueError("Invalid analysis threshold or minimum sample count")
        if not 0 <= self.min_coverage <= 1:
            raise ValueError("ANALYSIS_MIN_COVERAGE must be in [0,1]")
        if not 0 <= self.ingestion_grace_seconds < self.expected_interval_seconds:
            raise ValueError("ANALYSIS_INGESTION_GRACE_SECONDS must be smaller than the expected interval")

    @classmethod
    def load(cls):
        try:
            coverage = float(os.getenv("ANALYSIS_MIN_COVERAGE", "0.8"))
        except ValueError:
            raise ValueError("ANALYSIS_MIN_COVERAGE must be a number") from None
        return cls(
            window_days=integer("ANALYSIS_WINDOW_DAYS", 7, 1, 31),
            expected_interval_seconds=integer("ANALYSIS_EXPECTED_INTERVAL_SECONDS", 1800, 60, 3600),
            low_bike_threshold=integer("ANALYSIS_LOW_BIKE_THRESHOLD", 3, 0, 1000),
            min_samples=integer("ANALYSIS_MIN_SAMPLES", 2, 1, 10000),
            min_coverage=coverage,
            ingestion_grace_seconds=integer("ANALYSIS_INGESTION_GRACE_SECONDS", 120, 0, 3599))

    def as_dict(self):
        return asdict(self)

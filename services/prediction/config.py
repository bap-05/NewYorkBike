from dataclasses import asdict, dataclass

from shared.config import integer


@dataclass(frozen=True)
class PredictionOptions:
    horizon_seconds: int = 1800
    max_bike_age_seconds: int = 600
    timestamp_tolerance_seconds: int = 120
    history_days: int = 28
    min_training_days: int = 14
    min_training_samples: int = 1000
    min_station_samples: int = 100
    min_holdout_samples: int = 50

    def __post_init__(self):
        if self.horizon_seconds != 1800:
            raise ValueError("Prediction horizon must be 30 minutes")
        if not 60 <= self.max_bike_age_seconds <= 900:
            raise ValueError("Prediction maximum bike age must be in [60,900]")
        if not 0 <= self.timestamp_tolerance_seconds <= 300:
            raise ValueError("Prediction timestamp tolerance must be in [0,300]")
        if not 14 <= self.history_days <= 90 or not 7 <= self.min_training_days <= self.history_days:
            raise ValueError("Invalid prediction history/training days")
        if min(self.min_training_samples, self.min_station_samples, self.min_holdout_samples) < 2:
            raise ValueError("Prediction sample minimums must be >=2")

    @classmethod
    def load(cls):
        return cls(max_bike_age_seconds=integer("PREDICTION_MAX_BIKE_AGE_SECONDS",600,60,900),
            timestamp_tolerance_seconds=integer("PREDICTION_TIMESTAMP_TOLERANCE_SECONDS",120,0,300),
            history_days=integer("PREDICTION_HISTORY_DAYS",28,14,90),
            min_training_days=integer("PREDICTION_MIN_TRAINING_DAYS",14,7,90),
            min_training_samples=integer("PREDICTION_MIN_TRAINING_SAMPLES",1000,2,1000000),
            min_station_samples=integer("PREDICTION_MIN_STATION_SAMPLES",100,2,100000),
            min_holdout_samples=integer("PREDICTION_MIN_HOLDOUT_SAMPLES",50,2,100000))

    def as_dict(self):
        return asdict(self)

from dataclasses import dataclass
import json
import os
from urllib.parse import urlsplit

from shared.config import integer


@dataclass(frozen=True)
class ApiOptions:
    cors_origins: tuple[str,...] = ("http://localhost:5173","http://127.0.0.1:5173")
    bike_max_age_seconds: int = 600
    prediction_max_age_seconds: int = 900
    max_range_days: int = 31

    def __post_init__(self):
        if not 60 <= self.bike_max_age_seconds <= 900 or not 60 <= self.prediction_max_age_seconds <= 3600:
            raise ValueError("Invalid API freshness thresholds")
        if not 1 <= self.max_range_days <= 90:
            raise ValueError("Invalid API date range limit")
        for origin in self.cors_origins:
            p=urlsplit(origin)
            if p.scheme not in ('http','https') or not p.hostname or p.username or p.password or p.path or p.query or p.fragment:
                raise ValueError("API_CORS_ORIGINS must contain exact http(s) origins without paths")

    @classmethod
    def load(cls):
        values=json.loads(os.getenv('API_CORS_ORIGINS','["http://localhost:5173","http://127.0.0.1:5173"]'))
        if not isinstance(values,list) or not all(isinstance(v,str) for v in values) or len(values)>20:
            raise ValueError('API_CORS_ORIGINS must be an array of at most 20 origins')
        return cls(cors_origins=tuple(values),
            bike_max_age_seconds=integer('API_BIKE_MAX_AGE_SECONDS',600,60,900),
            prediction_max_age_seconds=integer('API_PREDICTION_MAX_AGE_SECONDS',900,60,3600),
            max_range_days=integer('API_MAX_RANGE_DAYS',31,1,90))

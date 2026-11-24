"""Recognized historical products for retrospective displays and analysis.

Forecast feature eligibility remains governed by prediction.data's stricter
availability-time policy; adding a historical product never backdates retrieval.
"""
RETROSPECTIVE_WEATHER_SOURCES = frozenset({
    'open-meteo', 'open-meteo-era5', 'open-meteo-historical-forecast',
})

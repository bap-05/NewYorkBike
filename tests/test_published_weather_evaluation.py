from scripts.evaluate_published_weather import metrics


def test_paired_forecasts_use_same_actuals_and_preserve_zero_errors():
    result = metrics([
        {'weather': 3, 'baseline': 5, 'actual': 3},
        {'weather': 6, 'baseline': 4, 'actual': 4},
    ])
    assert result['sample_count'] == 2
    assert result['weather_mae'] == result['baseline_mae'] == 1
    assert result['weather_rmse'] == result['baseline_rmse'] == 2 ** .5


def test_no_observed_targets_does_not_report_perfect_accuracy():
    result = metrics([])
    assert result['sample_count'] == 0
    assert result['weather_mae'] is None
    assert result['baseline_rmse'] is None

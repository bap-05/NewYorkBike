from types import SimpleNamespace

import pytest

from prediction.config import PredictionOptions
from scripts.register_weather_trial import candidate


def test_weather_trial_requires_honest_matching_evaluation_and_weather_features():
    report={'source':'citibike','status':'experimental','local_days':12,
        'split':{'test_samples':100},'dataset_hash':'test',
        'models':{'with_weather':{'test':{'mae':1.5,'rmse':2.,'sample_count':100},'validation':{'mae':1.4}}},
        'baseline':{'test':{'mae':.9,'sample_count':100}}}
    artifact={'with_weather':True,'feature_names':['temperature','humidity','rain','wind_speed']}
    settings=SimpleNamespace(bike_source='citibike',weather_max_age_seconds=1800)
    _,_,evaluation=candidate(report,artifact,settings,PredictionOptions())
    assert evaluation['mae']==1.5 and evaluation['baseline_mae']==.9
    artifact['with_weather']=False
    with pytest.raises(ValueError,match='weather-enabled'):
        candidate(report,artifact,settings,PredictionOptions())
    artifact['with_weather']=True
    report['baseline']['test']['sample_count']=90
    with pytest.raises(ValueError,match='cohorts'):
        candidate(report,artifact,settings,PredictionOptions())

"""Chronological evaluation and portable Random Forest model payloads."""
from collections import Counter
import hashlib
import json
import math
import struct
from statistics import fmean
from zoneinfo import ZoneInfo

from prediction.data import training_examples

MODEL_FORMAT = "citibike-rf-json-v1"


def scores(rows, predictions):
    if not rows:
        return {"sample_count":0,"mae":None,"rmse":None,"per_station":{}}
    errors = [float(pred)-row["actual_bikes"] for row,pred in zip(rows,predictions)]
    def values(indices):
        return {"sample_count":len(indices),"mae":fmean(abs(errors[i]) for i in indices),
            "rmse":math.sqrt(fmean(errors[i]**2 for i in indices))}
    return {**values(list(range(len(rows)))),"per_station":{
        station:values([i for i,r in enumerate(rows) if r["station_id"]==station])
        for station in sorted({r["station_id"] for r in rows})}}


def split_by_time(rows):
    times = sorted({r["input_time"] for r in rows})
    if len(times) < 10:
        return [],[],[],{}
    validation_start = times[int(len(times)*.7)]
    test_start = times[int(len(times)*.85)]
    train = [r for r in rows if r["input_time"] < validation_start
             and r["label_available_at"] < validation_start]
    validation = [r for r in rows if validation_start <= r["input_time"] < test_start
                  and r["label_available_at"] < test_start]
    test = [r for r in rows if r["input_time"] >= test_start]
    return train,validation,test,{"validation_start":validation_start.isoformat(),
        "test_start":test_start.isoformat(),"train_samples":len(train),
        "validation_samples":len(validation),"test_samples":len(test),
        "purged_boundary_samples":len(rows)-len(train)-len(validation)-len(test)}


def encoded_features(features, with_weather):
    values = dict(features["base"])
    station = values.pop("station_id")
    values["station_id="+station] = 1.0
    if with_weather:
        if features["weather"] is None:
            raise ValueError("Weather required by model is unavailable")
        values.update(features["weather"])
    return values


def infer(artifact, features, station_id):
    if artifact.get("format") != MODEL_FORMAT or station_id not in artifact["station_ids"]:
        raise ValueError("Unsupported model format or unseen station")
    values = encoded_features(features,artifact["with_weather"])
    names = artifact["feature_names"]
    vector = [values.get(name,0.0) if name.startswith("station_id=") else values[name] for name in names]
    vector = [struct.unpack("f",struct.pack("f",value))[0] for value in vector]
    if not all(math.isfinite(v) for v in vector):
        raise ValueError("Nonfinite model features")
    predictions = []
    for tree in artifact["trees"]:
        node = 0
        steps = 0
        while tree["left"][node] != -1:
            node = tree["left"][node] if vector[tree["feature"][node]] <= tree["threshold"][node] else tree["right"][node]
            steps += 1
            if steps > len(tree["left"]):
                raise ValueError("Invalid tree topology")
        predictions.append(tree["value"][node])
    result = fmean(predictions)
    if not math.isfinite(result):
        raise ValueError("Nonfinite prediction")
    return result


def fit_forest(rows, *, with_weather, depth):
    # Training-only imports: no sklearn/pickle or local artifact dependency in CI inference.
    import numpy as np
    import sklearn
    from sklearn.ensemble import RandomForestRegressor
    values = [encoded_features(r["features"],with_weather) for r in rows]
    names = sorted({name for row in values for name in row})
    matrix = np.array([[v.get(name,0.0) if name.startswith("station_id=") else v[name] for name in names] for v in values],dtype=np.float32)
    forest = RandomForestRegressor(n_estimators=40,max_depth=depth,min_samples_leaf=5,random_state=42,n_jobs=1)
    forest.fit(matrix,[r["actual_bikes"] for r in rows])
    artifact = {"format":MODEL_FORMAT,"with_weather":with_weather,"feature_names":names,
        "station_ids":sorted({r["station_id"] for r in rows}),"sklearn_version":sklearn.__version__,
        "parameters":{"n_estimators":40,"max_depth":depth,"min_samples_leaf":5,"random_state":42},"trees":[]}
    for estimator in forest.estimators_:
        tree = estimator.tree_
        artifact["trees"].append({"left":tree.children_left.tolist(),"right":tree.children_right.tolist(),
            "feature":tree.feature.tolist(),"threshold":tree.threshold.tolist(),"value":tree.value[:,0,0].tolist()})
    # RF casts inputs to float32 internally. Mirror it without requiring numpy at serving time.
    return artifact


def build_report(stations, groups, settings, options):
    rows, excluded = training_examples(stations,groups,settings,options)
    train,val,test,split = split_by_time(rows)
    baseline = {name:scores(part,[r["baseline"] for r in part]) for name,part in (
        ("train",train),("validation",val),("test",test))}
    # Weather ablation uses exactly the same complete-feature cohort in both variants.
    complete = [r for r in rows if r["features"] is not None and r["features"]["weather"] is not None]
    ml_train,ml_val,ml_test,ml_split = split_by_time(complete)
    days = {r["input_time"].astimezone(ZoneInfo("America/New_York")).date() for r in complete}
    counts = Counter(r["station_id"] for r in complete)
    reasons = []
    if len(days) < options.min_training_days:
        reasons.append("too_few_local_days")
    if len(complete) < options.min_training_samples:
        reasons.append("too_few_complete_samples")
    if any(counts[s.station_id] < options.min_station_samples for s in stations) or not stations:
        reasons.append("too_few_samples_for_monitored_station")
    if min(len(ml_train),len(ml_val),len(ml_test)) < options.min_holdout_samples:
        reasons.append("too_small_temporal_split")
    if ml_train and ({r["station_id"] for r in complete}-{r["station_id"] for r in ml_train}):
        reasons.append("holdout_station_missing_from_train")
    report = {"status":"insufficient_data" if reasons else "ready", "readiness_reasons":reasons,
        "baseline_examples":len(rows),"complete_ml_examples":len(complete),"local_days":len(days),
        "per_station_samples":dict(counts),"excluded_examples":excluded,"baseline_temporal_split":split,
        "baseline_scores":baseline,"ml_temporal_split":ml_split,"candidates":[],
        "target_policy":"sampled_at + 1800 seconds; timestamp match with explicit tolerance",
        "timestamp_tolerance_seconds":options.timestamp_tolerance_seconds}
    if reasons:
        return report,None
    candidates = []
    for with_weather in (False,True):
        for depth in (4,8):
            artifact = fit_forest(ml_train,with_weather=with_weather,depth=depth)
            metrics = scores(ml_val,[infer(artifact,r["features"],r["station_id"]) for r in ml_val])
            candidates.append((metrics["mae"],with_weather,depth))
            report["candidates"].append({"with_weather":with_weather,"max_depth":depth,"validation":metrics})
    best_mae,with_weather,depth = min(candidates)
    report["ml_cohort_baseline"] = {name:scores(part,[r["baseline"] for r in part])
        for name,part in (("validation",ml_val),("test",ml_test))}
    if best_mae >= report["ml_cohort_baseline"]["validation"]["mae"]:
        report["status"] = "baseline_preferred"
        return report,None
    evaluated_artifact = fit_forest(ml_train,with_weather=with_weather,depth=depth)
    report["selected"] = {"with_weather":with_weather,"max_depth":depth,
        "selection":"validation MAE only, strictly better than persistence",
        "test":scores(ml_test,[infer(evaluated_artifact,r["features"],r["station_id"]) for r in ml_test])}
    # Test scores above belong to train-only estimator. Refit for future serving after evaluation.
    production = fit_forest(complete,with_weather=with_weather,depth=depth)
    digest_data = [{k:r[k] for k in ("input_observation_id","actual_observation_id","features","actual_bikes")} for r in complete]
    report["dataset_hash"] = hashlib.sha256(json.dumps(digest_data,sort_keys=True).encode()).hexdigest()
    report["production_training_range"] = {"start":complete[0]["input_time"].isoformat(),
        "end":max(r["label_available_at"] for r in complete).isoformat(),"samples":len(complete)}
    report["status"] = "success"
    return report,production

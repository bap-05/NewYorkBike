"""Portable, validated scaler and centroids. Loading and inference never fit a model."""
from collections import Counter
import hashlib
import json
import os
from pathlib import Path

import numpy as np
from sqlalchemy import select

from clustering.features import FEATURE_NAMES
from shared.models import ClusteringRun


def model_path():
    return Path(os.getenv("CLUSTERING_MODEL_FILE", "artifacts/clustering/model.json"))


def fingerprint(payload):
    body = {key: value for key, value in payload.items() if key != "model_id"}
    return hashlib.sha256(json.dumps(body, sort_keys=True, allow_nan=False).encode()).hexdigest()


def validate_model(payload, source=None):
    try:
        if payload["format_version"] != 1 or payload["feature_names"] != list(FEATURE_NAMES):
            raise ValueError()
        if source is not None and payload["source"] != source:
            raise ValueError()
        size = len(FEATURE_NAMES)
        mean = np.asarray(payload["scaler_mean"], dtype=float)
        scale = np.asarray(payload["scaler_scale"], dtype=float)
        centers = np.asarray(payload["centers_standardized"], dtype=float)
        original = np.asarray(payload["centers_original"], dtype=float)
        k = payload["selected_k"]
        if not isinstance(k, int) or not 2 <= k <= 20:
            raise ValueError()
        if mean.shape != (size,) or scale.shape != (size,) or centers.shape != (k, size) or original.shape != (k, size):
            raise ValueError()
        if not all(np.isfinite(a).all() for a in (mean, scale, centers, original)) or (scale <= 0).any():
            raise ValueError()
        if not isinstance(payload["feature_config"], dict) or not isinstance(payload["training_run_id"], int):
            raise ValueError()
        if payload["model_id"] != fingerprint(payload):
            raise ValueError()
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise ValueError("Invalid or incompatible saved clustering model") from exc
    return payload


def load_model(path=None, *, source=None):
    payload = json.loads(Path(path or model_path()).read_text(encoding="utf-8"))
    return validate_model(payload, source)


def export_model(session, source, path=None, *, run_id=None):
    query = select(ClusteringRun).where(ClusteringRun.source == source, ClusteringRun.status == "success")
    if run_id is not None:
        query = query.where(ClusteringRun.id == run_id)
    runs = session.scalars(query.order_by(ClusteringRun.finished_at.desc(), ClusteringRun.id.desc()))
    run = next((row for row in runs if row.parameters and not row.parameters.get("model_reused")), None)
    if run is None:
        raise ValueError("No successful trained clustering run to export")
    parameters = run.parameters
    payload = {"format_version": 1, "source": source, "training_run_id": run.id,
        "training_window_start": run.window_start.isoformat(),
        "training_window_end": run.window_end.isoformat(),
        "trained_at": run.finished_at.isoformat(), "feature_config": run.feature_config,
        **{key: parameters[key] for key in ("feature_names", "scaler_mean", "scaler_scale",
            "centers_standardized", "centers_original", "selected_k")}}
    payload = json.loads(json.dumps(payload, allow_nan=False))
    payload["model_id"] = fingerprint(payload)
    validate_model(payload, source)
    target = Path(path or model_path())
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(target)
    return payload


def assign_clusters(features, options, model):
    validate_model(model)
    # These options define the meaning of the trained features, not quality gates.
    for key in ("low_bike_threshold", "timezone_name", "window_days"):
        if model["feature_config"].get(key) != getattr(options, key):
            raise ValueError("Saved clustering feature configuration differs")
    parameters = {key: model[key] for key in ("feature_names", "scaler_mean", "scaler_scale",
        "centers_standardized", "centers_original", "selected_k")}
    parameters.update(model_id=model["model_id"], model_reused=True, trained=False,
        training_run_id=model["training_run_id"], algorithm="StandardScaler+KMeans (saved)")
    if len(features) < options.min_stations:
        return [], {**parameters, "status": "insufficient_data", "reason": "too_few_eligible_stations"}
    raw = np.asarray([[row["feature_values"][name] for name in FEATURE_NAMES] for row in features])
    if not np.isfinite(raw).all():
        raise ValueError("Nonfinite clustering features")
    matrix = (raw - np.asarray(model["scaler_mean"])) / np.asarray(model["scaler_scale"])
    distances = np.linalg.norm(matrix[:, None, :] - np.asarray(model["centers_standardized"])[None, :, :], axis=2)
    labels = distances.argmin(axis=1)
    members = [{**row, "cluster_label": int(label), "distance_to_centroid": float(distances[i, label])}
        for i, (row, label) in enumerate(zip(features, labels))]
    sizes = dict(Counter(str(int(label)) for label in labels))
    return members, {**parameters, "status": "success", "silhouette": None,
        "cluster_sizes": sizes, "observed_k": len(sizes)}

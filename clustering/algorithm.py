"""Deterministic K-means; choose k using silhouette, without invented group names."""
from collections import Counter

import numpy as np
import sklearn
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

from clustering.features import FEATURE_NAMES


def fit_clusters(features, options):
    if len(features) < options.min_stations:
        return [], {"status": "insufficient_data", "reason": "too_few_eligible_stations"}
    raw = np.array([[row["feature_values"][name] for name in FEATURE_NAMES] for row in features])
    if not np.isfinite(raw).all():
        raise ValueError("Nonfinite clustering features")
    scaler = StandardScaler()
    matrix = scaler.fit_transform(raw)
    distinct = len(np.unique(matrix, axis=0))
    candidates, best = [], None
    # Avoid singleton groups, which are poorly supported by a small station set.
    maximum = min(options.max_clusters, len(features) // 2, distinct)
    with threadpool_limits(limits=1):
        for k in range(2, maximum + 1):
            model = KMeans(n_clusters=k, random_state=42, n_init=20, algorithm="lloyd")
            labels = model.fit_predict(matrix)
            sizes = Counter(int(label) for label in labels)
            if len(sizes) != k or min(sizes.values()) < 2:
                candidates.append({"k": k, "accepted": False, "reason": "singleton_or_degenerate_group"})
                continue
            score = float(silhouette_score(matrix, labels))
            candidates.append({"k": k, "accepted": True, "silhouette": score, "sizes": dict(sizes)})
            if best is None or score > best[0] + 1e-12:
                best = (score, model, labels)
    if best is None:
        return [], {"status": "insufficient_data", "reason": "no_supported_separation", "candidates": candidates}
    score, model, labels = best
    if score <= 0:
        return [], {"status": "insufficient_data", "reason": "nonpositive_silhouette", "candidates": candidates}
    members = []
    for index, (row, label) in enumerate(zip(features, labels)):
        members.append({**row, "cluster_label": int(label),
            "distance_to_centroid": float(np.linalg.norm(matrix[index] - model.cluster_centers_[label]))})
    return members, {"status": "success", "algorithm": "StandardScaler+KMeans", "selected_k": model.n_clusters,
        "silhouette": score, "candidates": candidates, "random_state": 42, "n_init": 20,
        "sklearn_version": sklearn.__version__, "feature_names": FEATURE_NAMES,
        "scaler_mean": scaler.mean_.tolist(), "scaler_scale": scaler.scale_.tolist(),
        "centers_standardized": model.cluster_centers_.tolist(),
        "centers_original": scaler.inverse_transform(model.cluster_centers_).tolist(),
        "cluster_sizes": dict(Counter(str(int(label)) for label in labels))}

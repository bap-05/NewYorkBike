export function usableForecast(hour) {
  return (
    hour.status === "available" &&
    Number.isFinite(hour.predicted_mean_bikes) &&
    hour.predicted_mean_bikes >= 0
  );
}

export function summarizeHourlyEvaluation(hours) {
  // DST may repeat a target hour. Its historical statistics describe the same
  // local-hour cohort and must not be counted twice in the pooled metrics.
  const unique = new Map();
  for (const hour of hours) {
    if (
      hour.evaluation_status !== "available" ||
      !Number.isInteger(hour.evaluation_samples) ||
      hour.evaluation_samples < 3 ||
      !Number.isFinite(hour.mae) ||
      hour.mae < 0 ||
      !Number.isFinite(hour.rmse) ||
      hour.rmse < 0 ||
      !Number.isFinite(hour.classification_accuracy) ||
      hour.classification_accuracy < 0 ||
      hour.classification_accuracy > 1
    )
      continue;
    unique.set(hour.local_hour, hour);
  }
  const rows = [...unique.values()];
  const samples = rows.reduce((sum, hour) => sum + hour.evaluation_samples, 0);
  if (!samples) return null;
  const mean = (value) =>
    rows.reduce((sum, hour) => sum + hour.evaluation_samples * value(hour), 0) /
    samples;
  return {
    samples,
    hours: rows.length,
    mae: mean((hour) => hour.mae),
    rmse: Math.sqrt(mean((hour) => hour.rmse ** 2)),
    classificationAccuracy: mean((hour) => hour.classification_accuracy),
  };
}

// Keep gaps after filtering, missing forecasts and DST hours honest: adjacency
// uses the actual UTC instants, not the repeated/skipped local hour labels.
export function forecastSegments(hours) {
  const segments = [];
  let segment = [];
  for (const [index, hour] of hours.entries()) {
    if (!usableForecast(hour)) {
      if (segment.length) segments.push(segment);
      segment = [];
      continue;
    }
    const previous = segment.at(-1)?.hour;
    if (
      previous &&
      Date.parse(hour.target_start_utc) -
        Date.parse(previous.target_start_utc) !==
        3600000
    ) {
      segments.push(segment);
      segment = [];
    }
    segment.push({ hour, index });
  }
  if (segment.length) segments.push(segment);
  return segments;
}

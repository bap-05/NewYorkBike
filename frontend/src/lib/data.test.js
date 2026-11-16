import test from "node:test";
import assert from "node:assert/strict";
import { bikeLevel, clusterProfile, frequencyLevel, summarizeClusters } from "./clusters.js";
import { forecastSegments } from "./hourlyForecast.js";

test("cluster descriptions distinguish missing data, no recorded shortage and shortage-prone groups", () => {
  assert.equal(bikeLevel(null), "Chưa đủ dữ liệu");
  assert.equal(bikeLevel(0), "Ít xe");
  assert.equal(bikeLevel(0.76), "Khá nhiều xe");
  assert.equal(frequencyLevel(0), "Không ghi nhận");
  assert.equal(frequencyLevel(0.001), "Rất hiếm");
  assert.equal(clusterProfile({mean_availability_ratio:.418,std_availability_ratio:.317,
    empty_ratio:.055,low_bikes_ratio:.137}), "Hay thiếu xe · Biến động mạnh");
  assert.equal(clusterProfile({mean_availability_ratio:.76,std_availability_ratio:.117,
    empty_ratio:0,low_bikes_ratio:0}), "Khá nhiều xe · Khá ổn định");
});

test("forecast lines break at missing or filtered hours and preserve UTC adjacency across DST", () => {
  const hour = (at, value = 2) => ({
    target_start_utc: at,
    status: value === null ? "insufficient_data" : "available",
    predicted_mean_bikes: value,
  });
  const hours = [
    hour("2026-11-01T05:00:00Z", 0),
    hour("2026-11-01T06:00:00Z"),
    hour("2026-11-01T07:00:00Z", null),
    hour("2026-11-01T08:00:00Z"),
    hour("2026-11-01T10:00:00Z"),
  ];
  assert.deepEqual(
    forecastSegments(hours).map((segment) => segment.map((item) => item.index)),
    [[0, 1], [3], [4]],
  );
});

test("cluster summaries keep equal station weights, real zeros and missing features", () => {
  const groups = summarizeClusters([
    {
      cluster_label: 0,
      sample_count: 100,
      feature_values: { mean_availability_ratio: 0, empty_ratio: 0 },
    },
    {
      cluster_label: 0,
      sample_count: 900,
      feature_values: { mean_availability_ratio: 1 },
    },
    { cluster_label: 1, feature_values: { mean_availability_ratio: 0 } },
  ]);
  assert.equal(groups[0].values.mean_availability_ratio, 0.5);
  assert.equal(groups[0].values.empty_ratio, null);
  assert.equal(groups[1].values.mean_availability_ratio, 0);
  assert.deepEqual(summarizeClusters([]), []);
});
import { calendarDefault, chartSegments } from "./calendar.js";
import { summarizeHourlyEvaluation } from "./hourlyForecast.js";
import {
  number,
  time,
  splitSegments,
  observationPoints,
  servedError,
} from "./data.js";

test("calendar selectors use New York and the ISO week year", () => {
  assert.equal(
    calendarDefault("day", new Date("2026-11-10T02:00:00Z")),
    "2026-11-09",
  );
  assert.equal(
    calendarDefault("week", new Date("2021-01-01T15:00:00Z")),
    "2020-W53",
  );
  assert.equal(
    calendarDefault("month", new Date("2026-11-01T02:00:00Z")),
    "2026-10",
  );
});

test("calendar charts break both at missing scheduled samples and nulls", () => {
  const points = [
    { at: "a", value: 0, gap_before: false },
    { at: "b", value: 5, gap_before: true },
    { at: "c", value: null, gap_before: false },
    { at: "d", value: 3, gap_before: false },
  ];
  assert.deepEqual(
    chartSegments(points).map((s) => s.map((p) => p.value)),
    [[0], [5], [3]],
  );
});

test("displayed error compares the served forecast to evaluated actual bikes", () => {
  assert.equal(servedError({ predicted_bikes: 0, actual_bikes: 2 }), 2);
  assert.equal(servedError({ predicted_bikes: 0, actual_bikes: null }), null);
  assert.equal(servedError({ predicted_bikes: null, actual_bikes: 2 }), null);
});

test("day-ahead error pooling weights samples, preserves zero and deduplicates DST", () => {
  const zero = {
    local_hour: 1,
    evaluation_status: "available",
    evaluation_samples: 3,
    mae: 0,
    rmse: 0,
    classification_accuracy: 1,
  };
  const other = {
    ...zero,
    local_hour: 2,
    evaluation_samples: 6,
    mae: 3,
    rmse: 4,
    classification_accuracy: 0.5,
  };
  const summary = summarizeHourlyEvaluation([
    zero,
    { ...zero },
    other,
    {
      ...zero,
      local_hour: 3,
      evaluation_status: "insufficient_data",
      mae: null,
    },
  ]);
  assert.equal(summary.samples, 9);
  assert.equal(summary.hours, 2);
  assert.equal(summary.mae, 2);
  assert.equal(summary.rmse, Math.sqrt(96 / 9));
  assert.equal(summary.classificationAccuracy, 2 / 3);
  assert.equal(summarizeHourlyEvaluation([]), null);
  assert.equal(summarizeHourlyEvaluation([{ ...zero, mae: null }]), null);
});

test("missing values remain distinct from zero", () => {
  assert.equal(number(null), "—");
  assert.equal(number(undefined), "—");
  assert.equal(number(0), "0");
  assert.equal(number(NaN), "—");
});
test("New York timezone handles both DST offsets independently of browser timezone", () => {
  assert.match(time("2026-11-01T05:30:00Z"), /01:30/);
  assert.match(time("2026-11-01T06:30:00Z"), /01:30/);
  assert.notEqual(time("2026-11-01T05:30:00Z"), time("2026-11-01T06:30:00Z"));
  assert.equal(time(null), "—");
});
test("chart does not join a missing half-hour sample or null value", () => {
  const points = [
    { at: "2026-11-09T09:00:00Z", value: 0 },
    { at: "2026-11-09T09:30:00Z", value: 1 },
    { at: "2026-11-09T10:30:00Z", value: 2 },
    { at: "2026-11-09T11:00:00Z", value: null },
    { at: "2026-11-09T11:30:00Z", value: 3 },
  ];
  assert.deepEqual(
    splitSegments(points).map((s) => s.length),
    [2, 1, 1],
  );
});
test("inactive observations cannot be plotted as rentable bikes", () => {
  const observation = {
    sampled_at: { utc: "2026-11-09T09:00:00Z" },
    quality_status: "valid",
    available_bikes: 3,
    is_renting: false,
    is_installed: true,
  };
  assert.equal(observationPoints([{ observation }])[0].value, null);
  observation.is_renting = true;
  observation.available_bikes = 0;
  assert.equal(observationPoints([{ observation }])[0].value, 0);
});

test("marked historical estimates retain provenance and zero without treating invalid actuals as estimates", () => {
  const observation = {
    sampled_at: { utc: "2026-11-13T05:00:00Z" },
    available_bikes: 0,
    quality_status: "missing",
    is_renting: null,
    is_installed: null,
  };
  const estimate = observationPoints([{ observation, is_estimated: true }])[0];
  assert.equal(estimate.value, 0);
  assert.equal(estimate.estimated, true);
  const actual = observationPoints([{ observation }])[0];
  assert.equal(actual.value, null);
  assert.equal(actual.estimated, false);
});

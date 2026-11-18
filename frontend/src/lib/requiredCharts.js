// Only the chart families explicitly requested for the time-series exercise.
export const requiredChartNames = [
  "line_day.png",
  "line_week.png",
  "line_month.png",
  "scatter_day.png",
  "scatter_week.png",
  "scatter_month.png",
  "histogram_day.png",
  "histogram_week.png",
  "histogram_month.png",
  "resampled_trend.png",
  "weekly_seasonality.png",
  "correlation_all.png",
];

export function requiredCharts(figures) {
  return [
    ...requiredChartNames.flatMap((name) =>
      figures.filter((f) => f.filename === name),
    ),
    ...figures.filter((f) => /^decomposition_[a-p]{16}\.png$/.test(f.filename)),
  ];
}

export function clusterColor(label) {
  if (!Number.isInteger(label) || label < 0) return "#8d969b";
  return ["#167c70", "#7954b3", "#b66a23", "#3069ae", "#b34470", "#628229"][
    label % 6
  ];
}

// Descriptive labels for published feature values; group IDs have no fixed meaning.
export function bikeLevel(ratio) {
  if (!Number.isFinite(ratio)) return "Chưa đủ dữ liệu";
  return ratio <= 0.2 ? "Ít xe" : ratio >= 0.8 ? "Nhiều xe"
    : ratio >= 0.6 ? "Khá nhiều xe" : "Mức xe trung bình";
}

export function variabilityLevel(ratio) {
  if (!Number.isFinite(ratio)) return "Chưa đủ dữ liệu";
  return ratio < 0.15 ? "Khá ổn định" : ratio < 0.3 ? "Biến động vừa" : "Biến động mạnh";
}

export function changeLevel(ratio) {
  if (!Number.isFinite(ratio)) return "Chưa đủ dữ liệu";
  return ratio <= 0.02 ? "Thay đổi ít" : ratio <= 0.05 ? "Thay đổi vừa" : "Thay đổi nhiều";
}

export function frequencyLevel(ratio) {
  if (!Number.isFinite(ratio)) return "Chưa đủ dữ liệu";
  if (ratio === 0) return "Không ghi nhận";
  return ratio < 0.01 ? "Rất hiếm" : ratio < 0.05 ? "Thỉnh thoảng"
    : ratio < 0.15 ? "Khá thường gặp" : "Thường gặp";
}

export function clusterProfile(values) {
  const missing = !Number.isFinite(values.empty_ratio) || !Number.isFinite(values.low_bikes_ratio);
  const level = !missing && values.empty_ratio + values.low_bikes_ratio >= 0.1
    ? "Hay thiếu xe" : bikeLevel(values.mean_availability_ratio);
  return `${level} · ${variabilityLevel(values.std_availability_ratio)}`;
}

export function summarizeClusters(members) {
  const groups = new Map();
  for (const member of members) {
    if (!groups.has(member.cluster_label)) groups.set(member.cluster_label, []);
    groups.get(member.cluster_label).push(member);
  }
  return [...groups.entries()]
    .sort(([a], [b]) => a - b)
    .map(([label, items]) => {
      const values = {};
      for (const key of [
        "mean_availability_ratio",
        "std_availability_ratio",
        "mean_abs_change_ratio",
        "empty_ratio",
        "low_bikes_ratio",
        "night_ratio",
        "morning_ratio",
        "daytime_ratio",
        "evening_ratio",
      ]) {
        const present = items
          .map((item) => item.feature_values?.[key])
          .filter(Number.isFinite);
        // A group summary is only shown when every member has this feature.
        values[key] =
          present.length === items.length
            ? present.reduce((a, b) => a + b, 0) / present.length
            : null;
      }
      return { label, items, values };
    });
}

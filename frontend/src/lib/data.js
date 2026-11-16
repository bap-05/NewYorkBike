export const labels = {
  estimated: "Ước lượng bù thiếu",
  fresh: "Dữ liệu mới",
  stale: "Dữ liệu cũ",
  inactive: "Ngừng cho thuê",
  missing: "Chưa có dữ liệu",
  invalid: "Không hợp lệ",
  unknown: "Chưa xác định",
  partial: "Thiếu một phần",
  baseline: "Mô hình cơ sở",
  ml: "Mô hình học máy",
  unavailable: "Chưa thể dự đoán",
  ok: "Đạt chất lượng",
  low_coverage: "Độ phủ thấp",
  insufficient_data: "Chưa đủ dữ liệu",
  success: "Thành công",
  skipped: "Không có thay đổi",
  failed: "Thất bại",
  running: "Đang chạy",
};
export const reasons = {
  too_few_eligible_stations: "Chưa đủ trạm có dữ liệu đạt yêu cầu",
  no_supported_separation: "Chưa tìm được cách phân nhóm đủ tin cậy",
  nonpositive_silhouette: "Các nhóm chưa tách biệt đủ rõ",
  stale_observation: "Mẫu xe đã quá cũ",
  no_eligible_active_ml_model:
    "Chưa có mô hình học máy đủ điều kiện; dùng mô hình cơ sở",
  missing_observation: "Chưa có quan sát xe",
  inactive_station: "Trạm ngừng cho thuê",
  target_expired: "Đã qua thời điểm mục tiêu",
  expired_target: "Đã qua thời điểm mục tiêu",
  stale_prediction: "Dự đoán đã cũ",
  stale_input: "Dữ liệu đầu vào đã cũ",
  missing_lag30: "Chưa có mẫu đầu vào trước 30 phút",
  target_passed: "Đã qua thời điểm mục tiêu",
  prediction_stale: "Dự đoán đã cũ",
  input_observation_stale: "Mẫu đầu vào đã quá cũ",
  input_observation_unavailable: "Không có mẫu đầu vào phù hợp",
  input_observation_unusable: "Mẫu đầu vào không còn hợp lệ",
  latest_station_observation_unusable:
    "Quan sát mới nhất của trạm không còn hợp lệ",
};
export function number(value, digits = 0) {
  return typeof value === "number" && Number.isFinite(value)
    ? new Intl.NumberFormat("vi-VN", { maximumFractionDigits: digits }).format(
        value,
      )
    : "—";
}
export function servedError(prediction) {
  return Number.isFinite(prediction.predicted_bikes) &&
    Number.isFinite(prediction.actual_bikes)
    ? Math.abs(prediction.predicted_bikes - prediction.actual_bikes)
    : null;
}
export function percent(value) {
  return typeof value === "number" ? `${number(value * 100, 1)}%` : "—";
}
export function time(value, short = false) {
  const raw = typeof value === "object" && value !== null ? value.utc : value;
  if (!raw || !Number.isFinite(new Date(raw).getTime())) return "—";
  return new Intl.DateTimeFormat("vi-VN", {
    timeZone: "America/New_York",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
    ...(short
      ? {}
      : {
          day: "2-digit",
          month: "2-digit",
          year: "numeric",
          timeZoneName: "short",
        }),
  }).format(new Date(raw));
}
export function latestSample(stations) {
  return stations
    .map((s) => s.latest_observation?.collected_at?.utc)
    .filter(Boolean)
    .sort()
    .at(-1);
}
export function stationPath(id) {
  return `/stations/${encodeURIComponent(id)}`;
}
export function observationPoints(items) {
  return items
    .map(({ observation: o, is_estimated = false }) => ({
      at: o.sampled_at.utc,
      value: is_estimated
        ? o.available_bikes
        : o.quality_status === "valid" &&
            o.is_renting === true &&
            o.is_installed === true
          ? o.available_bikes
          : null,
      estimated: is_estimated,
    }))
    .sort((a, b) => Date.parse(a.at) - Date.parse(b.at));
}
export function splitSegments(points, maxGapMs = 45 * 60000) {
  const segments = [];
  let current = [];
  let last;
  for (const point of points) {
    const at = Date.parse(point.at);
    if (!Number.isFinite(at) || !Number.isFinite(point.value)) {
      if (current.length) segments.push(current);
      current = [];
      last = undefined;
      continue;
    }
    if (last !== undefined && at - last > maxGapMs) {
      if (current.length) segments.push(current);
      current = [];
    }
    current.push(point);
    last = at;
  }
  if (current.length) segments.push(current);
  return segments;
}

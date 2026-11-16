export function newYorkDate(now = new Date()) {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(now);
  const value = (type) => parts.find((p) => p.type === type).value;
  return `${value("year")}-${value("month")}-${value("day")}`;
}

export function calendarDefault(period, now = new Date()) {
  const today = newYorkDate(now);
  if (period === "day") return today;
  if (period === "month") return today.slice(0, 7);
  const day = new Date(`${today}T00:00:00Z`);
  day.setUTCDate(day.getUTCDate() + 4 - (day.getUTCDay() || 7));
  const year = day.getUTCFullYear();
  const week = Math.ceil(
    ((day - new Date(Date.UTC(year, 0, 1))) / 86400000 + 1) / 7,
  );
  return `${year}-W${String(week).padStart(2, "0")}`;
}

export function chartSegments(points) {
  const segments = [];
  let current = [];
  for (const point of points) {
    if (point.gap_before || !Number.isFinite(point.value)) {
      if (current.length) segments.push(current);
      current = [];
    }
    if (Number.isFinite(point.value)) current.push(point);
  }
  if (current.length) segments.push(current);
  return segments;
}

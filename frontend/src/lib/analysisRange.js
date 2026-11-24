import { calendarDefault, newYorkDate } from "./calendar.js";

const dayMs = 86400000;
const hourMs = 3600000;
const localHourFormat = new Intl.DateTimeFormat("sv-SE", {
  timeZone: "America/New_York",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
});

function localHour(date) {
  return localHourFormat.format(date).replace(" ", "T");
}

function newYorkInstant(local, latest = false) {
  const wallTime = Date.parse(`${local}Z`);
  // New York's two UTC offsets also identify skipped and repeated DST hours.
  const matches = [4, 5]
    .map((offset) => wallTime + offset * hourMs)
    .filter(
      (instant) =>
        Number.isFinite(instant) && localHour(new Date(instant)) === local,
    );
  return latest ? matches.at(-1) : matches[0];
}

function calendarBoundary(value, period, following) {
  let day;
  if (period === "month") {
    day = new Date(`${value}-01T00:00:00Z`);
    if (following) day.setUTCMonth(day.getUTCMonth() + 1);
  } else if (period === "week") {
    const [year, week] = value.split("-W").map(Number);
    day = new Date(Date.UTC(year, 0, 4));
    day.setUTCDate(
      4 - ((day.getUTCDay() + 6) % 7) + (week - 1 + Number(following)) * 7,
    );
  } else {
    day = new Date(`${value}T00:00:00Z`);
    if (following) day.setUTCDate(day.getUTCDate() + 1);
  }
  return Number.isFinite(+day)
    ? newYorkInstant(`${day.toISOString().slice(0, 10)}T00:00`)
    : undefined;
}

export function defaultAnalysisRange(period, now = new Date()) {
  if (period === "hour") {
    const current = Math.floor(+now / hourMs) * hourMs;
    return {
      start: localHour(new Date(current - 23 * hourMs)),
      end: localHour(new Date(current)),
    };
  }
  const earlier = new Date(+now - (period === "week" ? 21 : 6) * dayMs);
  if (period === "month") {
    const [year, month] = newYorkDate(now).split("-").map(Number);
    return {
      start: new Date(Date.UTC(year, month - 3, 1)).toISOString().slice(0, 7),
      end: calendarDefault(period, now),
    };
  }
  return {
    start: calendarDefault(period, earlier),
    end: calendarDefault(period, now),
  };
}

export function rangeBounds(period, { start, end }) {
  if (!start || !end) return { error: "Chọn cả mốc bắt đầu và kết thúc." };
  if (start > end)
    return { error: "Mốc bắt đầu phải trước hoặc bằng mốc kết thúc." };
  if (period === "hour" && (!start.endsWith(":00") || !end.endsWith(":00")))
    return { error: "Chọn mốc tròn giờ, ví dụ 08:00." };
  const first =
    period === "hour"
      ? newYorkInstant(start)
      : calendarBoundary(start, period, false);
  const last =
    period === "hour"
      ? newYorkInstant(end, true) + hourMs
      : calendarBoundary(end, period, true);
  if (!Number.isFinite(first) || !Number.isFinite(last))
    return {
      error: "Mốc này không tồn tại trong giờ New York. Hãy chọn mốc khác.",
    };
  if (first >= Date.now())
    return { error: "Mốc bắt đầu phải nằm trong thời gian đã qua." };
  if (last - first > 370 * dayMs)
    return { error: "Chọn khoảng thời gian tối đa 370 ngày." };
  return { first, last };
}

export function analysisWindows(first, last, now = Date.now()) {
  const windows = [];
  for (let start = first; start < Math.min(last, now); start += 30 * dayMs) {
    const end = Math.min(start + 30 * dayMs, last);
    windows.push({
      start: new Date(start).toISOString(),
      end: end < now ? new Date(end).toISOString() : undefined,
    });
  }
  return windows;
}

export function analysisPoints(rows, period) {
  const days = rows
    .map((row) => ({
      at: row.window_start.utc,
      value: row.quality_status === "ok" ? row.metric_value : null,
      estimated: Boolean(row.dimensions?.uses_estimated_data),
    }))
    .sort((a, b) => Date.parse(a.at) - Date.parse(b.at));
  if (period === "hour" || period === "day") return days;
  const groups = new Map();
  for (const point of days) {
    const key = calendarDefault(period, new Date(point.at));
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(point);
  }
  return Array.from(groups, ([key, points]) => {
    const valid = points.filter(({ value }) => Number.isFinite(value));
    return {
      at: new Date(calendarBoundary(key, period, false)).toISOString(),
      value: valid.length
        ? valid.reduce((sum, { value }) => sum + value, 0) / valid.length
        : null,
      estimated: valid.some(({ estimated }) => estimated),
    };
  });
}

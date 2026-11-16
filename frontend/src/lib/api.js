const base = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");

export function imageUrl(path) {
  // Only accept image routes issued by this API, including a separate API host.
  if (!path.startsWith("/api/eda/reports/")) return "";
  return `${base}${path}`;
}

export async function get(path, signal, timeoutMs = 20000) {
  const timeout = AbortSignal.timeout(timeoutMs);
  const combined = signal ? AbortSignal.any([signal, timeout]) : timeout;
  let response;
  try {
    response = await fetch(`${base}/api${path}`, {
      signal: combined,
      headers: { Accept: "application/json" },
    });
  } catch (error) {
    if (signal?.aborted) throw error;
    throw new Error(
      "Không kết nối được API. Kiểm tra FastAPI đang chạy và thử lại.",
    );
  }
  if (!response.ok) {
    if (response.status === 404)
      throw new Error("Không tìm thấy trạm hoặc kết quả yêu cầu.");
    if (response.status === 422)
      throw new Error("Bộ lọc không hợp lệ. Hãy chọn lại khoảng thời gian.");
    throw new Error("API chưa sẵn sàng. Vui lòng thử lại sau.");
  }
  try {
    return await response.json();
  } catch {
    throw new Error(
      "Phản hồi API không hợp lệ. Kiểm tra cấu hình đường dẫn API.",
    );
  }
}

export function query(values) {
  return new URLSearchParams(
    Object.entries(values).filter(
      ([, value]) => value !== undefined && value !== null && value !== "",
    ),
  ).toString();
}

export async function allPages(path, values = {}, signal) {
  const items = [];
  let page;
  for (let offset = 0; offset < 100000; offset += 500) {
    page = await get(
      `${path}?${query({ ...values, limit: 500, offset })}`,
      signal,
    );
    items.push(...page.items);
    if (!page.pagination.has_more) return { ...page, items };
  }
  throw new Error("Quá nhiều kết quả. Hãy thu hẹp khoảng thời gian.");
}

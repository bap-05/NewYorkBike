import { expect } from "@playwright/test";

export async function prepareEda(page, request) {
  const response = await request.get("/api/stations");
  expect(response.ok()).toBeTruthy();
  const stations = await response.json();
  expect(stations.items.length).toBeGreaterThan(1);
  const now = new Date(stations.meta.as_of.utc);
  await page.clock.install({ time: now });
  const requests = [];
  page.on("request", (request) => requests.push(request.url()));
  // A missing file report must never gate any of the DB charts.
  await page.route(/\/api\/eda(?:\?|$)/, (route) =>
    route.fulfill({ json: { status: "missing", item: null } }),
  );
  await page.route("**/api/eda/reports/**", (route) => route.abort());
  return { stations: stations.items, now, requests };
}

export function expectNoReportReads(requests) {
  expect(requests.some((url) => /\/api\/eda(?:\?|$|\/reports\/)/.test(url))).toBeFalsy();
}

import { test, expect } from "@playwright/test";

test("chart type and station selectors keep each station's published forecasts", async ({
  page,
  request,
}) => {
  const response = await request.get("/api/eda/day-ahead");
  expect(response.ok()).toBeTruthy();
  const { item } = await response.json();
  const stations = item.day_ahead
    .filter((row) =>
      row.hourly_forecasts?.some((hour) => hour.status === "available"),
    )
    .slice(0, 2);
  expect(stations).toHaveLength(2);
  await page.goto("/predictions");
  for (const type of ["bar", "line", "area"]) {
    await page.getByLabel("Dạng biểu đồ dự báo").selectOption(type);
    for (const station of stations) {
      await page
        .getByLabel("Trạm dự báo ngày mai")
        .selectOption(station.station_id);
      await expect(page.locator(".hourly-station-name")).toContainText(
        station.station_name,
      );
      await expect(page.locator(".hourly-forecast-svg")).toHaveAttribute(
        "data-chart-type",
        type,
      );
      const usable = station.hourly_forecasts.filter(
        (hour) =>
          hour.status === "available" &&
          Number.isFinite(hour.predicted_mean_bikes),
      );
      await expect(
        page.locator(
          type === "bar" ? ".hourly-value-bar" : ".hourly-value-point",
        ),
      ).toHaveCount(usable.length);
      if (type !== "bar")
        await expect(page.locator(".hourly-value-bar")).toHaveCount(0);
      if (type === "area")
        await expect(page.locator(".hourly-value-area")).not.toHaveCount(0);
      const index = station.hourly_forecasts.findIndex(
        (hour) => hour.status === "available",
      );
      await page.locator(".hourly-forecast-column").nth(index).click();
      await expect(page.locator(".hourly-selection")).toContainText(
        new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 0 }).format(
          station.hourly_forecasts[index].predicted_mean_bikes,
        ),
      );
    }
  }
  await page
    .locator(".hourly-forecast-chart")
    .screenshot({ path: "test-results/hourly-area-desktop.png" });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByLabel("Dạng biểu đồ dự báo")).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
});

test("hourly bars match the published forecast and expose evidence on selection", async ({
  page,
  request,
}) => {
  const response = await request.get("/api/eda/day-ahead");
  expect(response.ok()).toBeTruthy();
  const { item } = await response.json();
  const station = item.day_ahead.find((row) =>
    row.hourly_forecasts?.some((hour) => hour.status === "available"),
  );
  expect(station).toBeTruthy();
  await page.goto("/predictions");
  await page
    .getByLabel("Trạm dự báo ngày mai")
    .selectOption(station.station_id);
  const columns = page.locator(".hourly-forecast-column");
  await expect(columns).toHaveCount(station.hourly_forecasts.length);
  const index = station.hourly_forecasts.findIndex(
    (hour) => hour.status === "available",
  );
  const hour = station.hourly_forecasts[index];
  await columns.nth(index).click();
  const detail = page.locator(".hourly-selection");
  await expect(detail).toContainText(hour.hour_label);
  await expect(detail).toContainText(`${hour.history_days} ngày`);
  if (hour.support_dates?.length)
    await expect(detail).toContainText(hour.support_dates[0]);
  await expect(detail).toContainText(
    new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 0 }).format(
      hour.predicted_mean_bikes,
    ),
  );
  await columns.nth(index).focus();
  await page.keyboard.press("Enter");
  await expect(columns.nth(index)).toHaveAttribute("aria-pressed", "true");
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
  await page
    .locator(".hourly-forecast-chart")
    .screenshot({ path: "test-results/hourly-forecast-mobile.png" });
});

test("missing forecasts stay distinct from zero and repeated DST hours stay selectable", async ({
  page,
  request,
}) => {
  const response = await request.get("/api/eda/day-ahead");
  expect(response.ok()).toBeTruthy();
  const payload = await response.json();
  const station = payload.item.day_ahead[0];
  const template = station.hourly_forecasts[0];
  // Browser-only fixture: never written to Aiven or production artifacts.
  station.hourly_forecasts = [
    {
      ...template,
      target_start_utc: "2026-11-01T05:00:00Z",
      hour_label: "01:00 (-0400)",
      status: "available",
      predicted_mean_bikes: 0,
      availability_class: "low",
    },
    {
      ...template,
      target_start_utc: "2026-11-01T06:00:00Z",
      hour_label: "01:00 (-0500)",
      status: "insufficient_data",
      reason: "too_few_matching_hours",
      predicted_mean_bikes: null,
      availability_class: null,
    },
  ];
  payload.item.day_ahead = [station];
  await page.route("**/api/eda/day-ahead", (route) => route.fulfill({ json: payload }));
  await page.goto("/predictions");
  const columns = page.locator(".hourly-forecast-column");
  await expect(columns).toHaveCount(2);
  await expect(columns.nth(0)).toHaveAttribute("aria-label", /0 xe/);
  await expect(columns.nth(0).locator(".hourly-value-bar")).toHaveAttribute(
    "height",
    "0",
  );
  await expect(columns.nth(1)).toHaveAttribute("aria-label", /Chưa đủ dữ liệu/);
  await expect(columns.nth(1).locator(".hourly-value-bar")).toHaveCount(0);
  await columns.nth(1).click();
  await expect(page.locator(".hourly-selection")).toContainText(
    "01:00 (-0500)",
  );
  await expect(page.locator(".hourly-selection")).toContainText(
    "Chưa có ít nhất 5 ngày",
  );
});

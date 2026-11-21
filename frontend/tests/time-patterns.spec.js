import { test, expect } from "@playwright/test";

test("time-series requirements and next-day forecasts use the live snapshot", async ({
  page,
  request,
}) => {
  const response = await request.get("/api/eda");
  expect(response.ok()).toBeTruthy();
  const { item } = await response.json();
  expect(item.day_ahead.length).toBeGreaterThan(0);
  await page.goto("/analysis");
  const selector = page.getByRole("combobox", {
    name: "Biểu đồ EDA",
    exact: true,
  });
  await expect(selector.locator("option")).toHaveCount(12);
  await expect(selector.locator('option[value="boxplots.png"]')).toHaveCount(0);
  await expect(selector.locator('option[value="scaling.png"]')).toHaveCount(0);
  for (const file of [
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
  ]) {
    expect(item.figures.some((f) => f.filename === file)).toBeTruthy();
    await selector.selectOption(file);
    if (/^(line|scatter|histogram)_/.test(file)) {
      await expect(page.locator(".calendar-svg").first()).toBeVisible();
    } else
      await expect
        .poll(() =>
          page
            .locator(".eda-image")
            .evaluate((img) => img.complete && img.naturalWidth > 0),
        )
        .toBeTruthy();
  }
  await page.goto("/predictions");
  await expect(
    page.getByRole("heading", {
      name: "Dự báo và phân loại ngày mai",
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", {
      name: "Xe dự báo trung bình theo giờ",
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page.getByText("Đây là quy tắc phân loại mức xe sẵn có", { exact: false }),
  ).toBeVisible();
  const dayPanel = page.locator("section.panel").filter({
    has: page.getByRole("heading", {
      name: "Dự báo và phân loại ngày mai",
      exact: true,
    }),
  });
  const chosen =
    item.day_ahead.find((row) => row.low_bike_hours?.length) ||
    item.day_ahead[0];
  await page
    .getByRole("button", { name: chosen.station_name, exact: true })
    .click();
  const hourRows = dayPanel.locator(".hourly-forecast-column");
  await expect(hourRows).toHaveCount(chosen.hourly_forecasts.length);
  await page.getByRole("checkbox", { name: "Chỉ xem giờ ít xe" }).check();
  await expect(hourRows).toHaveCount(chosen.low_bike_hours.length);
  await page.getByRole("checkbox", { name: "Chỉ xem giờ ít xe" }).uncheck();
  await expect(hourRows).toHaveCount(chosen.hourly_forecasts.length);
  await page.screenshot({
    path: "../artifacts/frontend/day-ahead-desktop.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
});

import { test, expect } from "@playwright/test";
import { prepareEda, expectNoReportReads } from "./edaHelpers.js";

test("trend, seasonality and correlation use DB ranges and preserve QUAN previews", async ({ page, request }) => {
  const { requests } = await prepareEda(page, request);
  let busyOnce = true;
  await page.route("**/api/eda/chart-data?kind=trend&*", async (route) => {
    if (busyOnce) {
      busyOnce = false;
      await route.fulfill({ status: 429, json: { detail: "EDA is busy" } });
    } else {
      await route.continue();
    }
  });
  await page.goto("/analysis");
  const selector = page.getByLabel("Biểu đồ EDA", { exact: true });
  for (const [file, kind] of [["resampled_trend.png", "trend"], ["weekly_seasonality.png", "seasonality"], ["correlation_all.png", "correlation"]]) {
    await selector.selectOption(file);
    if (kind === "correlation") {
      await expect(page.getByRole("img", { name: "Ma trận tương quan Pearson" })).toBeVisible();
    } else {
      const preview = page.locator(".eda-content .calendar-chart-preview").first();
      await expect(preview).toBeVisible();
      await preview.click();
      const dialog = page.getByRole("dialog");
      await expect(dialog.getByRole("img", { name: "Biểu đồ tương tác" })).toBeVisible();
      await dialog.getByRole("button", { name: "Đóng", exact: true }).click();
    }
    expect(requests.some((url) => url.includes(`/api/eda/chart-data?kind=${kind}`))).toBeTruthy();
  }
  await page.getByLabel("Khoảng dữ liệu EDA").selectOption("60");
  await expect.poll(() => requests.some((url) => url.includes("kind=correlation") && url.includes("days=60"))).toBeTruthy();
  await expect(page.getByRole("img", { name: "Ma trận tương quan Pearson" })).toBeVisible();
  expectNoReportReads(requests);
  expect(busyOnce).toBeFalsy();
});

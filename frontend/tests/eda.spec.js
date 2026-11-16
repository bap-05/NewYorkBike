import { test, expect } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import { requiredCharts } from "../src/lib/requiredCharts.js";

test("EDA automatically loads a newly completed report after one minute", async ({ page, request }) => {
  const response = await request.get("/api/eda");
  const original = await response.json();
  expect(original.item).toBeTruthy();
  let calls = 0;
  let published = false;
  await page.route(/\/api\/eda(?:\?.*)?$/, async (route) => {
    calls += 1;
    const data = structuredClone(original);
    data.item.raw_rows = published ? 23456 : 12345;
    await route.fulfill({ json: data });
  });
  await page.clock.install();
  await page.goto("/analysis");
  await expect(page.locator(".eda-content")).toContainText("12.345");
  const initialCalls = calls;
  published = true;
  await page.clock.fastForward(60000);
  await expect(page.locator(".eda-content")).toContainText("23.456");
  expect(calls).toBeGreaterThan(initialCalls);
});

test("EDA charts and median/mode render from the real completed report", async ({
  page,
  request,
}) => {
  const response = await request.get("/api/eda");
  expect(response.ok()).toBeTruthy();
  const report = await response.json();
  expect(report.status).toBe("available");
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/analysis");
  await expect(
    page.getByRole("heading", { name: "Khám phá dữ liệu (EDA)" }),
  ).toBeVisible();
  const selector = page.getByRole("combobox", {
    name: "Biểu đồ EDA",
    exact: true,
  });
  await expect(selector.locator("option")).toHaveCount(
    requiredCharts(report.item.figures).length,
  );
  for (const name of [
    "line_day.png",
    "correlation_all.png",
    "scatter_week.png",
    "histogram_month.png",
  ]) {
    await selector.selectOption(name);
    if (/^(line|scatter|histogram)_/.test(name)) {
      await expect(page.locator(".calendar-svg").first()).toBeVisible();
    } else
      await expect
        .poll(() =>
          page
            .locator(".eda-image")
            .evaluate((image) => image.complete && image.naturalWidth > 0),
        )
        .toBeTruthy();
  }
  await selector.selectOption("line_day.png");
  await expect(page.locator(".calendar-svg").first()).toBeVisible();
  await expect(page.locator(".eda-content table")).toHaveCount(0);
  await mkdir("../artifacts/frontend", { recursive: true });
  await page
    .locator(".eda-content")
    .screenshot({ path: "../artifacts/frontend/eda-web.png" });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
  expect(errors).toEqual([]);
});

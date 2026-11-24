import { test, expect } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import { calendarDefault } from "../src/lib/calendar.js";
import { prepareEda, expectNoReportReads } from "./edaHelpers.js";

test("EDA reads fresh DB data each minute without requiring a file report", async ({ page, request }) => {
  const { requests } = await prepareEda(page, request);
  await page.goto("/analysis");
  await page.getByLabel("Biểu đồ EDA", { exact: true }).selectOption("correlation_all.png");
  await expect(page.getByRole("img", { name: "Ma trận tương quan Pearson" })).toBeVisible();
  const calls = () => requests.filter((url) => url.includes("/api/eda/chart-data?")).length;
  const before = calls();
  await page.clock.fastForward(60000);
  await expect.poll(calls).toBeGreaterThan(before);
  await expect(page.getByRole("img", { name: "Ma trận tương quan Pearson" })).toBeVisible();
  expectNoReportReads(requests);
});

test("QUAN calendar controls retain all nine charts, dialog and mobile layout", async ({ page, request }) => {
  const { now, requests } = await prepareEda(page, request);
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/analysis");
  await expect(page.getByRole("heading", { name: "Khám phá dữ liệu (EDA)" })).toBeVisible();
  const kind = page.getByRole("combobox", { name: "Loại biểu đồ", exact: true });
  const period = page.getByRole("combobox", { name: "Kỳ thời gian", exact: true });
  const previousDay = new Date(+now - 86400000);
  for (const selectedPeriod of ["day", "week", "month"]) {
    await period.selectOption(selectedPeriod);
    await page.getByLabel(`${{ day: "Ngày", week: "Tuần", month: "Tháng" }[selectedPeriod]} muốn xem`)
      .fill(calendarDefault(selectedPeriod, previousDay));
    for (const selectedKind of ["line", "scatter", "histogram"]) {
      await kind.selectOption(selectedKind);
      await expect(page.locator(".calendar-svg").first()).toBeVisible();
    }
  }
  await page.locator(".calendar-chart-preview").first().click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", { name: "Phóng to biểu đồ", exact: true }).click();
  await expect(dialog.locator(".chart-zoom-controls")).toContainText("120%");
  await dialog.getByRole("button", { name: "Đóng", exact: true }).click();
  await expect(dialog).toHaveCount(0);
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  expectNoReportReads(requests);
  expect(errors).toEqual([]);
  await mkdir("../artifacts/frontend", { recursive: true });
  await page.screenshot({ path: "../artifacts/frontend/quan-eda-mobile.png", fullPage: true });
});

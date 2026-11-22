import { test, expect } from "@playwright/test";

test("select a specific day, ISO week and calendar month using live history", async ({
  page,
}) => {
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/analysis");
  const chart = page.getByRole("combobox", {
    name: "Biểu đồ EDA",
    exact: true,
  });
  await chart.selectOption("series");
  const kind = page.getByLabel("Loại biểu đồ", { exact: true });
  const period = page.getByLabel("Kỳ thời gian", { exact: true });
  await page.getByLabel("Ngày muốn xem", { exact: true }).fill("2026-11-03");
  await expect(
    page.locator(".calendar-explorer .panel-footnote").first(),
  ).toContainText("2026-11-03");
  await expect(page.locator(".calendar-svg")).toHaveCount(10);
  await page.getByLabel("Ngày muốn xem", { exact: true }).fill("2026-01-01");
  await expect(
    page.getByRole("heading", { name: "Chưa có dữ liệu trong kỳ đã chọn" }),
  ).toBeVisible();
  await expect(page.locator(".calendar-svg")).toHaveCount(0);
  await kind.selectOption("scatter");
  await period.selectOption("week");
  await page.getByLabel("Tuần muốn xem", { exact: true }).fill("2026-W45");
  await expect(page.locator(".calendar-svg")).toHaveCount(10);
  await kind.selectOption("histogram");
  await period.selectOption("month");
  await page.getByLabel("Tháng muốn xem", { exact: true }).fill("2026-11");
  await expect(page.locator(".calendar-svg")).toHaveCount(10);
  const stations = page.getByRole("combobox", {
    name: "Trạm trên biểu đồ",
    exact: true,
  });
  const id = await stations.locator("option").nth(1).getAttribute("value");
  await stations.selectOption(id);
  await expect(page.locator(".calendar-svg")).toHaveCount(1);
  await page.screenshot({
    path: "../artifacts/frontend/calendar-month-selection.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
  expect(errors).toEqual([]);
});

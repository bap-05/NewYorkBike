import { test, expect } from "@playwright/test";

test("EDA decomposition changes station and renders four interactive components", async ({
  page,
}) => {
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/analysis");
  const chart = page.getByRole("combobox", {
    name: "Biểu đồ EDA",
    exact: true,
  });
  await expect(chart.locator('option[value="decomposition"]')).toHaveCount(1);
  await chart.selectOption("decomposition");
  const station = page.getByRole("combobox", {
    name: "Trạm phân rã chuỗi thời gian",
    exact: true,
  });
  await expect(station).toBeVisible();
  const options = await station
    .locator("option")
    .evaluateAll((nodes) =>
      nodes.map((node) => ({
        value: node.value,
        text: node.textContent.trim(),
      })),
    );
  expect(options.length).toBeGreaterThan(1);
  const charts = page.locator(".eda-content .dynamic-chart");
  await expect(charts).toHaveCount(4);
  for (const title of ["Chuỗi gốc", "Xu hướng", "Mùa vụ (24 giờ)", "Phần dư"]) {
    await expect(page.getByRole("heading", { name: title, exact: true })).toBeVisible();
  }
  const observed = charts.first();
  await expect(observed).toBeVisible();
  await expect.poll(() => observed.locator("circle").count()).toBeGreaterThan(0);
  const initial = await observed.innerHTML();
  await station.selectOption(options[1].value);
  await expect.poll(() => observed.innerHTML()).not.toBe(initial);
  const zoom = page.locator(".eda-content .chart-zoom").first();
  await zoom.getByRole("button", { name: "Phóng to biểu đồ" }).click();
  await expect(zoom.locator(".chart-zoom-controls")).toContainText("150%");
  await page.screenshot({
    path: "../artifacts/frontend/decomposition-desktop.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(station).toBeVisible();
  await expect(observed).toBeVisible();
  expect(errors).toEqual([]);
});

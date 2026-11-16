import { test, expect } from "@playwright/test";

test("daily deviation combines marked inputs and connects all seven days", async ({
  page,
}) => {
  await page.goto("/analysis");
  await page
    .getByLabel("Chỉ số phân tích")
    .selectOption("available_bikes_stddev");
  const chart = page
    .locator(".chart")
    .filter({ has: page.locator('svg[aria-label^="Độ lệch chuẩn số xe"]') });
  await expect(chart.locator("circle")).toHaveCount(7);
  await expect(
    chart.locator(".estimated-segment, .observed-segment"),
  ).toHaveCount(6);
  expect(await chart.locator("circle title").allTextContents()).toEqual(
    expect.arrayContaining([expect.stringContaining("Ước lượng bù thiếu")]),
  );
  await chart.screenshot({
    path: "../artifacts/frontend/analysis-with-estimates.png",
  });
});

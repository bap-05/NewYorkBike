import { test, expect } from "@playwright/test";

test("station history renders uniform green solid lines and retains estimate labels", async ({
  page,
  request,
}) => {
  const response = await request.get("/api/stations");
  expect(response.ok()).toBeTruthy();
  const { items } = await response.json();
  const station = items[0];
  const historyRequest = page.waitForResponse(
    (response) =>
      response.url().includes(`/stations/${station.station_id}/history`) &&
      response.url().includes("include_estimated=true"),
  );
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto(`/stations/${station.station_id}`);
  const history = await historyRequest;
  expect(history.ok()).toBeTruthy();
  const result = await history.json();
  expect(result.items.some((item) => item.is_estimated)).toBeTruthy();
  await expect(page.locator(".chart .estimated-segment").first()).toBeVisible();
  await expect(
    page.locator(".chart .estimated-segment").first(),
  ).toHaveAttribute("stroke", "#147d70");
  expect(
    await page
      .locator(".chart .estimated-segment")
      .first()
      .getAttribute("stroke-dasharray"),
  ).toBeNull();
  expect(await page.locator(".chart circle title").allTextContents()).toEqual(
    expect.arrayContaining([expect.stringContaining("Ước lượng bù thiếu")]),
  );
  await expect(page.locator(".chart .observed-segment").first()).toHaveAttribute("stroke", "#147d70");
  await page
    .locator(".chart")
    .screenshot({ path: "../artifacts/frontend/history-with-estimates.png" });
  expect(errors).toEqual([]);
});

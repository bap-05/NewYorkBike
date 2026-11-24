import { test, expect } from "@playwright/test";

for (const values of [[-0.8, -0.7, -0.6], [-1, 0, 1]]) {
  test(`correlation renders signed values ${values} in preview and dialog`, async ({ page }) => {
    await page.clock.install({ time: new Date("2026-11-24T18:40:00Z") });
    await page.route("**/api/**", async (route) => {
      const url = new URL(route.request().url());
      const pagination = { has_more: false };
      if (url.pathname === "/api/stations") {
        return route.fulfill({ json: {
          pagination,
          items: [{ station_id: "station-1", name: "Trạm kiểm thử", capacity: 50 }],
        } });
      }
      if (url.pathname === "/api/analysis") {
        const correlation = url.searchParams.get("metric_name") === "temperature_bikes_correlation";
        return route.fulfill({ json: {
          pagination,
          items: (correlation ? values : [32, 35, 43]).map((value, index) => ({
            window_start: { utc: `2026-11-${18 + index}T05:00:00Z` },
            metric_value: value,
            quality_status: "ok",
          })),
        } });
      }
      return route.fulfill({ status: 404, json: { detail: "No EDA fixture" } });
    });
    await page.goto("/analysis");
    await page.getByLabel("Chỉ số phân tích").selectOption("temperature_bikes_correlation");
    const preview = page.getByRole("button", { name: "Mở lớn biểu đồ Tương quan nhiệt độ – số xe" });
    await expect(preview.locator("circle")).toHaveCount(values.length);

    async function expectSignedChart(chart) {
      await expect(chart.locator('text[x="40"]')).toHaveText(["-1", "-0,5", "0", "0,5", "1"]);
      const positions = await chart.locator("circle").evaluateAll((points) =>
        points.map((point) => Number(point.getAttribute("cy"))),
      );
      expect(positions).toEqual(values.map((value) => 224 - ((value + 1) / 2) * 190));
      expect(positions.every((y) => y >= 34 && y <= 224)).toBeTruthy();
    }
    await expectSignedChart(preview);
    await preview.click();
    const dialog = page.getByRole("dialog", { name: "Tương quan nhiệt độ – số xe" });
    await expectSignedChart(dialog);
    await dialog.getByRole("button", { name: "Đóng", exact: true }).click();

    await page.getByLabel("Chỉ số phân tích").selectOption("available_bikes_mean");
    const bikes = page.getByRole("button", { name: "Mở lớn biểu đồ Số xe trung bình" });
    await expect(bikes.locator('text[x="40"]').first()).toHaveText("0");
    await expect(bikes.locator('text[x="40"]').last()).toHaveText("43");
  });
}

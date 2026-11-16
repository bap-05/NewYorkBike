import { test, expect } from "@playwright/test";

test("all missing forecasts show six qualified days without drawing fake bars", async ({
  page,
}) => {
  const hours = Array.from({ length: 24 }, (_, hour) => ({
    target_start_utc: new Date(Date.UTC(2026, 10, 14, 5 + hour)).toISOString(),
    target_end_utc: new Date(Date.UTC(2026, 10, 14, 6 + hour)).toISOString(),
    local_hour: hour,
    hour_label: `${String(hour).padStart(2, "0")}:00 (-0500)`,
    status: "insufficient_data",
    reason: "requires_seven_covered_completed_days",
    history_days: 6,
    predicted_mean_bikes: null,
    availability_class: null,
    evaluation_status: "insufficient_data",
    evaluation_samples: 2,
    mae: null,
    rmse: null,
    classification_accuracy: null,
  }));
  await page.route("**/api/eda/day-ahead", (route) =>
    route.fulfill({
      json: {
        status: "available",
        item: {
          generated_at: "2026-11-13T13:00:00Z",
          day_ahead: [
            {
              station_id: "isolated-missing",
              station_name: "Trạm thiếu một ngày",
              capacity: 45,
              target_date: "2026-11-14",
              reason: "requires_seven_covered_completed_days",
              qualified_days: 6,
              hourly_forecasts: hours,
            },
          ],
        },
      },
    }),
  );
  await page.goto("/predictions");
  await expect(
    page.getByText("Chưa thể xác định giờ có nguy cơ ít xe."),
  ).toBeVisible();
  await expect(
    page.getByText("Số ngày đạt yêu cầu của trạm:", { exact: false }),
  ).toContainText("6/7");
  await expect(page.locator(".hourly-forecast-svg")).toHaveCount(0);
  await expect(page.locator(".hourly-forecast-chart")).toContainText(
    "Chưa có giờ nào đủ điều kiện để vẽ dự báo.",
  );
  await expect(page.locator(".day-ahead-evaluation")).toHaveCount(0);
});

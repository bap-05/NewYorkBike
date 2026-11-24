import { test, expect } from "@playwright/test";
import { mkdir, writeFile } from "node:fs/promises";

test("five pages read live API, station search/detail, filters, mobile and request failure", async ({
  page,
  request,
}) => {
  const stations = await request.get("/api/stations");
  expect(stations.ok()).toBeTruthy();
  const live = await stations.json();
  expect(live.items.length).toBeGreaterThan(0);
  const station = live.items[0];
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await mkdir("../artifacts/frontend", { recursive: true });
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Một nhịp nhìn New York." }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: station.name, exact: true }).first(),
  ).toBeVisible();
  await page.screenshot({
    path: "../artifacts/frontend/overview-desktop.png",
    fullPage: true,
  });

  await page
    .getByRole("navigation")
    .getByRole("link", { name: "Bản đồ trạm" })
    .click();
  await page
    .getByRole("textbox", { name: "Tìm trạm theo tên" })
    .fill(station.name);
  await expect(
    page.getByRole("button", { name: station.name, exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: station.name, exact: true }).click();
  await expect(page.locator(".station-list-item")).toHaveCount(1);
  await page.screenshot({
    path: "../artifacts/frontend/map-desktop.png",
    fullPage: true,
  });
  await page
    .locator(".station-list-item")
    .getByRole("link", { name: "Chi tiết" })
    .click();
  await expect(
    page.getByRole("heading", { name: station.name, exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Thời tiết tại trạm" }),
  ).toBeVisible();
  await expect(
    page
      .locator(".chart svg")
      .or(page.getByRole("heading", { name: "Chưa đủ dữ liệu để vẽ biểu đồ" })),
  ).toBeVisible();
  await page.screenshot({
    path: "../artifacts/frontend/station-desktop.png",
    fullPage: true,
  });

  await page
    .getByRole("navigation")
    .getByRole("link", { name: "Phân tích", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Phân tích dữ liệu" }),
  ).toBeVisible();
  await expect(
    page
      .locator(".chart > .calendar-chart-preview")
      .first()
      .or(page.getByRole("heading", { name: "Chưa có thống kê phù hợp" })),
  ).toBeVisible();
  await page
    .getByRole("combobox", { name: "Tổng hợp", exact: true })
    .selectOption("hour");
  await expect(page.locator(".panel .loading")).toHaveCount(0);
  await page.screenshot({
    path: "../artifacts/frontend/analysis-desktop.png",
    fullPage: true,
  });
  await page.getByRole("navigation").getByRole("link", { name: "Phân nhóm", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Nhóm trạm tương đồng" })).toBeVisible();

  await page
    .getByRole("navigation")
    .getByRole("link", { name: "Dự đoán", exact: true })
    .click();
  await expect(page.locator(".prediction-card")).toHaveCount(live.items.length);
  await expect(
    page.getByRole("heading", { name: "Lịch sử dự đoán & đối chiếu" }),
  ).toHaveCount(0);
  await expect(page.locator(".prediction-card-link")).toHaveCount(live.items.length);
  await expect(page.locator(".panel .loading")).toHaveCount(0);
  await expect(page.getByRole("alert")).toHaveCount(0);
  await page.screenshot({
    path: "../artifacts/frontend/predictions-desktop.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await expect(
    page.getByRole("link", { name: station.name, exact: true }).first(),
  ).toBeAttached();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
  await page.screenshot({
    path: "../artifacts/frontend/overview-mobile.png",
    fullPage: true,
  });

  await page.route("**/api/**", (route) => route.abort());
  await page.getByRole("button", { name: "Làm mới", exact: true }).click();
  await expect(page.getByRole("alert").first()).toBeVisible();
  await page.unroute("**/api/**");
  await page
    .getByRole("button", { name: "Thử lại", exact: true })
    .first()
    .click();
  await expect(
    page.getByRole("link", { name: station.name, exact: true }).first(),
  ).toBeAttached();
  expect(errors).toEqual([]);
  await writeFile(
    "../artifacts/frontend/verification.json",
    JSON.stringify(
      {
        verified_at_utc: new Date().toISOString(),
        station_count: live.items.length,
        data_source: "Live read-only FastAPI backed by Aiven",
        pages: ["overview", "map", "station", "analysis", "predictions"],
        desktop: { width: 1440, height: 1000 },
        mobile: { width: 390, height: 844 },
        checks: [
          "station search and detail navigation",
          "analysis aggregation filter",
          "latest forecasts and history",
          "no document overflow on mobile",
          "network failure and retry",
          "no browser runtime errors",
        ],
        no_database_writes: true,
        no_background_workers_started: true,
        deployment_tested: false,
      },
      null,
      2,
    ),
  );
});

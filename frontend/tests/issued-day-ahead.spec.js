import { test, expect } from "@playwright/test";

const row = {publication_id:99,issued_at:"2026-11-15T15:00:00Z",
  target_start_utc:"2026-11-16T05:00:00Z",status:"available",predicted_bikes:5,actual_bikes:3};
const station = {station_id:"test-issued",station_name:"Isolated station",capacity:20,
  target_date:"2026-11-18",hourly_forecasts:[{target_start_utc:"2026-11-18T05:00:00Z",
    hour_label:"00:00 (-0500)",status:"available",predicted_mean_bikes:5,availability_class:"balanced"}],
  issued_evaluation:{items:[row]}};
const payload = (stations) => ({status:"available",item:{day_ahead:stations}});

test.beforeEach(async ({page}) => {
  await page.route("**/api/stations?*", (route) => route.fulfill({ json: {
    pagination: { has_more: false }, items: [
      { station_id: station.station_id, name: station.station_name, latitude: 40.75, longitude: -73.99 },
      { station_id: "other", name: "Other station", latitude: 40.76, longitude: -73.98 },
    ],
  } }));
  await page.clock.setFixedTime(new Date("2026-11-17T15:00:00Z"));
});

test("yesterday uses New York dates, sorts hours and shows signed whole bike differences", async ({page}) => {
  const items = [
    {...row,target_start_utc:"2026-11-17T04:00:00Z",predicted_bikes:4.2,actual_bikes:7.4},
    {...row,target_start_utc:"2026-11-17T05:00:00Z",predicted_bikes:999},
    {...row,target_start_utc:"2026-11-16T04:59:00Z",predicted_bikes:999},row];
  await page.route("**/api/eda/day-ahead",route=>route.fulfill({json:payload([
    {...station,issued_evaluation:{items}}])}));
  await page.goto("/predictions");
  const comparison=page.getByRole("region",{name:"Chênh lệch dự báo hôm qua"});
  await expect(comparison.getByRole("heading")).toContainText("2026-11-16");
  await expect(comparison.locator("tbody tr")).toHaveCount(2);
  await expect(comparison.locator("tbody tr").nth(0).locator("td")).toHaveText([
    "00:00 EST 16/11/2026","5","3","-2"]);
  await expect(comparison.locator("tbody tr").nth(1).locator("td")).toHaveText([
    "23:00 EST 16/11/2026","4","7","+3"]);
  await expect(page.locator(".day-ahead-evaluation")).toHaveCount(0);
  await expect(page.getByText("Tổng hợp giờ ít xe của các trạm",{exact:true})).toHaveCount(0);
});

test("station filter changes comparison and missing actuals remain blank",async ({page})=>{
  const other={...station,station_id:"other",station_name:"Other station",
    issued_evaluation:{items:[{...row,status:"awaiting_data",actual_bikes:null}]}};
  await page.route("**/api/eda/day-ahead",route=>route.fulfill({json:payload([station,other])}));
  await page.goto("/predictions");
  await page.getByRole("button", { name: "Other station", exact: true }).click();
  const comparison=page.getByRole("region",{name:"Chênh lệch dự báo hôm qua"});
  await expect(comparison.getByRole("heading")).toContainText("Other station");
  await expect(comparison.locator("tbody tr td").nth(2)).toHaveText("—");
  await expect(comparison.locator("tbody tr td").nth(3)).toHaveText("—");
});

test("no saved forecast yesterday shows no fabricated comparison",async ({page})=>{
  await page.route("**/api/eda/day-ahead",route=>route.fulfill({json:payload([
    {...station,issued_evaluation:{items:[]}}])}));
  await page.goto("/predictions");
  const comparison=page.getByRole("region",{name:"Chênh lệch dự báo hôm qua"});
  await expect(comparison).toContainText("Chưa có bản dự báo đã lưu cho ngày hôm qua");
  await expect(comparison.locator("tbody tr")).toHaveCount(0);
});

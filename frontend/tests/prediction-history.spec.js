import { test, expect } from "@playwright/test";

test("station forecast card opens its own history with pagination and a return link", async ({
  page,
  request,
}) => {
  const stations = await (await request.get("/api/stations")).json();
  const station = stations.items[0];
  const historyPath = `/predictions/${encodeURIComponent(station.station_id)}/history`;
  const requests = [];
  await page.route(/\/api\/stations\/[^/]+\/predictions\?/, async (route) => {
    const url = new URL(route.request().url());
    requests.push(url.pathname);
    const offset = Number(url.searchParams.get("offset"));
    await route.fulfill({
      json: {
        items: [
          {
            id: offset + 1,
            status: "ml",
            issued_at: "2026-11-16T13:00:00Z",
            input_time: "2026-11-16T12:55:00Z",
            target_at: "2026-11-16T13:25:00Z",
            predicted_bikes: offset ? 7 : 5,
            actual_bikes: 4,
            evaluated_at: "2026-11-16T13:30:00Z",
          },
        ],
        pagination: { total: 21, limit: 20, offset, has_more: offset === 0 },
      },
    });
  });
  await page.goto("/predictions");
  await expect(
    page.getByRole("heading", { name: "Lịch sử dự đoán & đối chiếu" }),
  ).toHaveCount(0);
  const card = page
    .locator(".prediction-card")
    .filter({
      has: page.getByRole("link", { name: station.name, exact: true }),
    });
  await expect(card).toBeVisible();
  expect(requests).toHaveLength(0);
  await card.click({ position: { x: 25, y: 25 } });
  await expect(page).toHaveURL(new RegExp(`${historyPath}$`));
  await expect(
    page.getByRole("heading", { name: "Lịch sử dự báo 30 phút" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: station.name, exact: true }),
  ).toBeVisible();
  await expect(page.locator("tbody tr .number-cell")).toHaveText("5");
  expect(
    requests.every((path) =>
      path.includes(encodeURIComponent(station.station_id)),
    ),
  ).toBeTruthy();
  await page.getByRole("button", { name: "Sau", exact: true }).click();
  await expect(page.locator("tbody tr .number-cell")).toHaveText("7");
  await page.getByRole("button", { name: "Trước", exact: true }).click();
  await expect(page.locator("tbody tr .number-cell")).toHaveText("5");
  await page.reload();
  await expect(page.locator("tbody tr .number-cell")).toHaveText("5");
  await page.getByRole("link", { name: "← Quay lại dự báo" }).click();
  await expect(page).toHaveURL(/\/predictions$/);
});

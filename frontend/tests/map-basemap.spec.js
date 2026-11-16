import { test, expect } from "@playwright/test";

test("street basemap loads native place labels without a key or custom geography controls", async ({
  page,
}) => {
  const successfulTiles = [];
  page.on("response", (response) => {
    if (
      response.url().includes("World_Street_Map/MapServer/tile/") &&
      response.status() === 200
    )
      successfulTiles.push(response.url());
  });
  await page.goto("/map");
  const map = page.locator(".leaflet-container");
  await expect(map).toHaveCount(1);
  await expect.poll(() => successfulTiles.length).toBeGreaterThan(0);
  const tiles = map.locator('img.leaflet-tile[src*="World_Street_Map"]');
  await expect(tiles).not.toHaveCount(0);
  for (const url of await tiles.evaluateAll((images) =>
    images.map((image) => image.src),
  )) {
    expect(new URL(url).search).toBe("");
  }
  await expect(
    page.locator(".vietnam-island-marker, .geography-controls"),
  ).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Xem biển đảo Việt Nam" }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Về các trạm New York" }),
  ).toHaveCount(0);
  await expect(map.locator("path.leaflet-interactive")).toHaveCount(10);
  await map.scrollIntoViewIfNeeded();
  await expect
    .poll(() => map.locator("img.leaflet-tile-loaded").count())
    .toBeGreaterThan(3);
  await page.screenshot({
    path: "test-results/street-basemap.png",
    fullPage: true,
  });
});

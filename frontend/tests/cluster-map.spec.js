import { test, expect } from "@playwright/test";
import { clusterColor } from "../src/lib/clusters.js";

test("published clusters have matching map colors, membership and real feature summaries", async ({
  page,
  request,
}) => {
  const response = await request.get("/api/clusters");
  expect(response.ok()).toBeTruthy();
  const { latest_success: run } = await response.json();
  expect(run).toBeTruthy();
  const membersResponse = await request.get(
    `/api/clusters/${run.id}/stations?limit=500`,
  );
  expect(membersResponse.ok()).toBeTruthy();
  const { items } = await membersResponse.json();
  const labels = [...new Set(items.map((m) => m.cluster_label))];
  await page.goto("/map");
  await page.getByLabel("Chế độ bản đồ").selectOption("clusters");
  for (const label of labels) {
    const count = items.filter((m) => m.cluster_label === label).length;
    await expect(
      page.locator(".cluster-explorer .map-legend")
        .getByText(`Nhóm ${label + 1} · ${count} trạm`, { exact: true }),
    ).toHaveCount(1);
    await expect(
      page.locator(
        `.cluster-explorer path.leaflet-interactive[fill="${clusterColor(label)}"]`,
      ),
    ).toHaveCount(count);
  }
  await page.screenshot({
    path: "test-results/cluster-map.png",
    fullPage: true,
  });
  await page.getByLabel("Chế độ bản đồ").selectOption("availability");
  await expect(page.getByLabel("Tìm trạm theo tên")).toBeVisible();
  await page.goto("/clusters");
  const map = page.locator(".cluster-explorer");
  const marker = map.locator(`path.leaflet-interactive[fill="${clusterColor(labels[0])}"]`).first();
  await marker.click();
  await expect(map.locator(".map-popup-group")).toContainText(`Nhóm ${labels[0] + 1}`);
});

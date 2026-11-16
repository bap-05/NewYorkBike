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
  await expect(page.locator(".cluster-card")).toHaveCount(labels.length);
  for (const label of labels) {
    const count = items.filter((m) => m.cluster_label === label).length;
    await expect(
      page
        .locator(".cluster-card h3")
        .filter({ hasText: `Nhóm ${label + 1} · ${count} trạm` }),
    ).toHaveCount(1);
    await expect(
      page.locator(
        `.cluster-explorer path.leaflet-interactive[fill="${clusterColor(label)}"]`,
      ),
    ).toHaveCount(count);
  }
  await expect(
    page
      .locator(".cluster-card")
      .first()
      .getByText("Mức xe thường có", { exact: true }),
  ).toBeVisible();
  await expect(page.locator(".cluster-cards")).not.toContainText("%");
  await page.screenshot({
    path: "test-results/cluster-map.png",
    fullPage: true,
  });
  await page.getByLabel("Chế độ bản đồ").selectOption("availability");
  await expect(page.getByLabel("Tìm trạm theo tên")).toBeVisible();
  await page.goto("/analysis");
  await expect(page.locator(".cluster-card")).toHaveCount(labels.length);
});

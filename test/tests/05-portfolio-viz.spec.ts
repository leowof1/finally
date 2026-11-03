import { test, expect } from "@playwright/test";
import { closePosition, waitForPrice } from "./helpers";

test("heatmap renders positions and P&L chart has data", async ({ page, request }) => {
  await waitForPrice(request, "NVDA");
  await closePosition(request, "NVDA");
  const buy = await request.post("/api/portfolio/trade", { data: { ticker: "NVDA", quantity: 1, side: "buy" } });
  expect(buy.ok()).toBeTruthy();

  const history = await (await request.get("/api/portfolio/history")).json();
  expect(history.length).toBeGreaterThan(0);

  await page.goto("/");
  const heatmap = page.getByTestId("heatmap");
  await expect(heatmap).toBeVisible();
  const cell = page.getByTestId("heatmap-cell-NVDA");
  await expect(cell).toBeVisible();
  const pnl = (await request.get("/api/portfolio").then((r) => r.json())).positions.find(
    (p: { ticker: string }) => p.ticker === "NVDA",
  ).unrealized_pnl;
  if (pnl !== 0) {
    const rgb = pnl > 0 ? /rgba?\(34, 197, 94/ : /rgba?\(239, 68, 68/;
    await expect(cell).toHaveCSS("background-color", rgb);
  }

  const chart = page.getByTestId("pnl-chart");
  await expect(chart).toBeVisible();
  await expect(chart.locator("canvas, svg").first()).toBeVisible();
});

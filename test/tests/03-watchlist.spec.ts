import { test, expect } from "@playwright/test";

test("add and remove a ticker from the watchlist", async ({ page, request }) => {
  await request.delete("/api/watchlist/PYPL");
  await page.goto("/");
  await expect(page.getByTestId("watchlist-row-AAPL")).toBeVisible();

  await page.getByTestId("watchlist-add-input").fill("PYPL");
  await page.getByTestId("watchlist-add-button").click();
  const row = page.getByTestId("watchlist-row-PYPL");
  await expect(row).toBeVisible();
  await expect(page.getByTestId("price-PYPL")).toHaveText(/\d+\.\d{2}/);

  await page.getByTestId("watchlist-remove-PYPL").click();
  await expect(row).toHaveCount(0);

  const rows = await (await request.get("/api/watchlist")).json();
  expect(rows.map((r: { ticker: string }) => r.ticker)).not.toContain("PYPL");
});

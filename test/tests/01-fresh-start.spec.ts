import { test, expect } from "@playwright/test";
import { DEFAULT_TICKERS, moneyOf } from "./helpers";

// Runs first: assumes a fresh database (new volume / deleted db/finally.db).

test("fresh start shows default watchlist, $10,000 cash, streaming prices", async ({ page }) => {
  await page.goto("/");

  for (const ticker of DEFAULT_TICKERS) {
    await expect(page.getByTestId(`watchlist-row-${ticker}`)).toBeVisible();
  }

  expect(await moneyOf(page.getByTestId("cash-balance"))).toBe(10000);
  expect(await moneyOf(page.getByTestId("total-value"))).toBe(10000);

  const price = page.getByTestId("price-AAPL");
  await expect(price).toHaveText(/\d+\.\d{2}/);
  const first = await price.innerText();
  await expect(price).not.toHaveText(first, { timeout: 10_000 });
});

test("connection status shows connected", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("connection-status")).toHaveAttribute("data-status", "connected");
});

import { test, expect, Page } from "@playwright/test";
import { closePosition, moneyOf, waitForPrice } from "./helpers";

async function trade(page: Page, ticker: string, quantity: number, side: "buy" | "sell") {
  await page.getByTestId("trade-ticker").fill(ticker);
  await page.getByTestId("trade-quantity").fill(String(quantity));
  await page.getByTestId(`trade-${side}`).click();
}

test.beforeEach(async ({ request }) => {
  await waitForPrice(request, "GOOGL");
  await closePosition(request, "GOOGL");
});

test("buy shares: cash decreases and position appears", async ({ page }) => {
  await page.goto("/");
  const cash = page.getByTestId("cash-balance");
  await expect(cash).toHaveText(/\d/);
  const before = await moneyOf(cash);

  await trade(page, "GOOGL", 3, "buy");

  const row = page.getByTestId("position-row-GOOGL");
  await expect(row).toBeVisible();
  await expect(row).toContainText("3");
  await expect.poll(() => moneyOf(cash)).toBeLessThan(before);
});

test("sell shares: cash increases, position updates then disappears", async ({ page }) => {
  await page.goto("/");
  await trade(page, "GOOGL", 3, "buy");
  const row = page.getByTestId("position-row-GOOGL");
  await expect(row).toBeVisible();

  const cash = page.getByTestId("cash-balance");
  const afterBuy = await moneyOf(cash);

  await trade(page, "GOOGL", 1, "sell");
  await expect.poll(() => moneyOf(cash)).toBeGreaterThan(afterBuy);
  await expect(row).toContainText("2");

  await trade(page, "GOOGL", 2, "sell");
  await expect(row).toHaveCount(0);
});

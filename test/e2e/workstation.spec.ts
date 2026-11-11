import { expect, type Page, test } from "@playwright/test";

test.describe.configure({ mode: "serial" });

const DEFAULT_TICKERS = ["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA", "NVDA", "META", "JPM", "V", "NFLX"];

const money = (text: string | null) => Number((text ?? "").replace(/[^0-9.-]/g, ""));

async function cash(page: Page) {
  return money(await page.getByTestId("cash-balance").textContent());
}

async function trade(page: Page, ticker: string, quantity: string, side: "Buy" | "Sell") {
  await page.getByLabel("Trade ticker").fill(ticker);
  await page.getByLabel("Quantity").fill(quantity);
  await page.getByRole("button", { name: side, exact: true }).click();
  await expect(page.getByRole("status")).toContainText(side === "Buy" ? "Bought" : "Sold");
}

test.beforeEach(async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("connection-status")).toHaveAttribute("data-status", "connected");
});

test("fresh start shows default watchlist, $10k and streaming prices", async ({ page }) => {
  for (const ticker of DEFAULT_TICKERS) {
    await expect(page.getByTestId(`watch-${ticker}`)).toBeVisible();
  }
  await expect(page.getByTestId("cash-balance")).toHaveText("$10,000.00");
  await expect(page.getByTestId("total-value")).toHaveText("$10,000.00");

  const prices = async () =>
    Promise.all(DEFAULT_TICKERS.map((t) => page.getByTestId(`price-${t}`).textContent()));
  const first = await prices();
  await expect.poll(async () => (await prices()).join(), { timeout: 10_000 }).not.toBe(first.join());
});

test("add and remove a watchlist ticker", async ({ page }) => {
  await page.getByLabel("Ticker to add").fill("PYPL");
  await page.getByRole("button", { name: "Add", exact: true }).click();
  await expect(page.getByTestId("watch-PYPL")).toBeVisible();
  await expect(page.getByTestId("price-PYPL")).not.toHaveText("--");

  await page.getByTestId("watch-PYPL").hover();
  await page.getByLabel("Remove PYPL from watchlist").click();
  await expect(page.getByTestId("watch-PYPL")).toHaveCount(0);
});

test("buy shares: cash decreases and position appears", async ({ page }) => {
  const before = await cash(page);
  await trade(page, "AAPL", "5", "Buy");
  await expect(page.getByTestId("position-AAPL")).toBeVisible();
  expect(await cash(page)).toBeLessThan(before);
});

test("portfolio visualizations render", async ({ page }) => {
  const tile = page.getByTestId("tile-AAPL");
  await expect(tile).toBeVisible();
  const background = await tile.evaluate((el) => getComputedStyle(el).backgroundColor);
  expect(background).toMatch(/rgba\((63, 182, 139|229, 83, 75|123, 136, 152)/);
  await expect(page.getByTestId("pnl-chart")).not.toHaveAttribute("data-points", "0");
});

test("sell shares: cash increases and position disappears", async ({ page }) => {
  const before = await cash(page);
  await trade(page, "AAPL", "5", "Sell");
  await expect(page.getByTestId("position-AAPL")).toHaveCount(0);
  expect(await cash(page)).toBeGreaterThan(before);
});

test("rejects a trade with insufficient cash", async ({ page }) => {
  await page.getByLabel("Trade ticker").fill("NVDA");
  await page.getByLabel("Quantity").fill("1000");
  await page.getByRole("button", { name: "Buy", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("Insufficient cash");
});

test("AI chat (mocked) executes a trade shown inline", async ({ page }) => {
  await page.getByLabel("Chat message").fill("buy 2 MSFT");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByTestId("chat-assistant")).toBeVisible();
  await expect(page.getByTestId("chat-action")).toContainText("Bought 2 MSFT");
  await expect(page.getByTestId("position-MSFT")).toBeVisible();
});

test("SSE retries while the stream is unreachable, then reconnects", async ({ page }) => {
  const status = page.getByTestId("connection-status");
  let attempts = 0;
  await page.route("**/api/stream/prices", (route) => {
    attempts += 1;
    return route.abort("connectionreset");
  });
  await page.reload();
  await expect(status).toHaveAttribute("data-status", "reconnecting");
  await expect.poll(() => attempts, { timeout: 10_000 }).toBeGreaterThan(1);

  await page.unroute("**/api/stream/prices");
  await expect(status).toHaveAttribute("data-status", "connected", { timeout: 15_000 });
  const price = page.getByTestId("price-AAPL");
  await expect(price).not.toHaveText("--");
});

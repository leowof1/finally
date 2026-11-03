import { APIRequestContext, Locator, expect } from "@playwright/test";

export const DEFAULT_TICKERS = ["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA", "NVDA", "META", "JPM", "V", "NFLX"];

/** Parse a displayed money string like "$10,000.00" into a number. */
export function parseMoney(text: string): number {
  return Number(text.replace(/[^0-9.-]/g, ""));
}

/** Read a money value from a locator's text. */
export async function moneyOf(locator: Locator): Promise<number> {
  return parseMoney((await locator.innerText()).trim());
}

/** Fetch the portfolio JSON from the API. */
export async function getPortfolio(request: APIRequestContext) {
  const res = await request.get("/api/portfolio");
  expect(res.ok()).toBeTruthy();
  return res.json();
}

/** Quantity held for a ticker (0 if no position). */
export async function heldQuantity(request: APIRequestContext, ticker: string): Promise<number> {
  const portfolio = await getPortfolio(request);
  const pos = portfolio.positions.find((p: { ticker: string }) => p.ticker === ticker);
  return pos ? pos.quantity : 0;
}

/** Sell any existing position so a test starts from a known state. */
export async function closePosition(request: APIRequestContext, ticker: string) {
  const quantity = await heldQuantity(request, ticker);
  if (quantity > 0) {
    const res = await request.post("/api/portfolio/trade", { data: { ticker, quantity, side: "sell" } });
    expect(res.ok()).toBeTruthy();
  }
}

/** Wait until the backend has a live price for a ticker. */
export async function waitForPrice(request: APIRequestContext, ticker: string) {
  await expect
    .poll(async () => {
      const res = await request.get("/api/watchlist");
      const rows = await res.json();
      return rows.find((r: { ticker: string }) => r.ticker === ticker)?.price ?? null;
    })
    .not.toBeNull();
}

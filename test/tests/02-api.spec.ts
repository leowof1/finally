import { test, expect } from "@playwright/test";
import { DEFAULT_TICKERS, closePosition, waitForPrice } from "./helpers";

test("health check", async ({ request }) => {
  const res = await request.get("/api/health");
  expect(res.status()).toBe(200);
  expect(await res.json()).toEqual({ status: "ok" });
});

test("watchlist shape contains default tickers", async ({ request }) => {
  const res = await request.get("/api/watchlist");
  expect(res.status()).toBe(200);
  const rows = await res.json();
  const tickers = rows.map((r: { ticker: string }) => r.ticker);
  for (const t of DEFAULT_TICKERS) expect(tickers).toContain(t);
  for (const key of ["ticker", "price", "previous_price", "change_percent", "direction", "added_at"]) {
    expect(rows[0]).toHaveProperty(key);
  }
});

test("watchlist add is uppercased, duplicate is 409, delete then 404", async ({ request }) => {
  await request.delete("/api/watchlist/IBM");

  const added = await request.post("/api/watchlist", { data: { ticker: "ibm" } });
  expect(added.status()).toBe(201);
  expect((await added.json()).ticker).toBe("IBM");

  const dup = await request.post("/api/watchlist", { data: { ticker: "IBM" } });
  expect(dup.status()).toBe(409);

  expect((await request.delete("/api/watchlist/IBM")).status()).toBe(204);
  expect((await request.delete("/api/watchlist/IBM")).status()).toBe(404);
});

test("portfolio shape", async ({ request }) => {
  const res = await request.get("/api/portfolio");
  expect(res.status()).toBe(200);
  const body = await res.json();
  for (const key of ["cash_balance", "total_value", "unrealized_pnl", "positions"]) {
    expect(body).toHaveProperty(key);
  }
  expect(Array.isArray(body.positions)).toBeTruthy();
});

test("trade buy then sell returns trade and portfolio", async ({ request }) => {
  await waitForPrice(request, "MSFT");
  await closePosition(request, "MSFT");

  const buy = await request.post("/api/portfolio/trade", { data: { ticker: "MSFT", quantity: 2, side: "buy" } });
  expect(buy.status()).toBe(200);
  const body = await buy.json();
  expect(body.trade).toMatchObject({ ticker: "MSFT", side: "buy", quantity: 2 });
  expect(body.trade.price).toBeGreaterThan(0);
  const pos = body.portfolio.positions.find((p: { ticker: string }) => p.ticker === "MSFT");
  for (const key of ["quantity", "avg_cost", "current_price", "market_value", "unrealized_pnl", "pnl_percent"]) {
    expect(pos).toHaveProperty(key);
  }

  const sell = await request.post("/api/portfolio/trade", { data: { ticker: "MSFT", quantity: 2, side: "sell" } });
  expect(sell.status()).toBe(200);
  const after = await sell.json();
  expect(after.portfolio.positions.find((p: { ticker: string }) => p.ticker === "MSFT")).toBeUndefined();
});

test("invalid trades return 400 with detail", async ({ request }) => {
  await waitForPrice(request, "AAPL");
  const tooBig = await request.post("/api/portfolio/trade", {
    data: { ticker: "AAPL", quantity: 1_000_000, side: "buy" },
  });
  expect(tooBig.status()).toBe(400);
  expect((await tooBig.json()).detail).toBeTruthy();

  const oversell = await request.post("/api/portfolio/trade", {
    data: { ticker: "NFLX", quantity: 1_000_000, side: "sell" },
  });
  expect(oversell.status()).toBe(400);
  expect((await oversell.json()).detail).toBeTruthy();
});

test("portfolio history is a list of snapshots", async ({ request }) => {
  const res = await request.get("/api/portfolio/history");
  expect(res.status()).toBe(200);
  const rows = await res.json();
  expect(rows.length).toBeGreaterThan(0);
  expect(rows[0]).toHaveProperty("total_value");
  expect(rows[0]).toHaveProperty("recorded_at");
});

test("mock chat without buy returns plain response", async ({ request }) => {
  const res = await request.post("/api/chat", { data: { message: "hello there" } });
  expect(res.status()).toBe(200);
  expect(await res.json()).toEqual({ message: "Mock response", trades: [], watchlist_changes: [] });
});

test("chat history returns stored messages", async ({ request }) => {
  const res = await request.get("/api/chat/history");
  expect(res.status()).toBe(200);
  const rows = await res.json();
  expect(rows.length).toBeGreaterThan(0);
  for (const key of ["role", "content", "actions", "created_at"]) expect(rows[0]).toHaveProperty(key);
});

test("price stream sends JSON events keyed by ticker", async ({ page }) => {
  await page.goto("/api/health");
  const event = await page.evaluate(
    () =>
      new Promise<Record<string, Record<string, unknown>>>((resolve) => {
        const source = new EventSource("/api/stream/prices");
        source.onmessage = (e) => {
          source.close();
          resolve(JSON.parse(e.data));
        };
      }),
  );
  expect(event.AAPL).toBeDefined();
  for (const key of ["ticker", "price", "previous_price", "timestamp", "change", "change_percent", "direction"]) {
    expect(event.AAPL).toHaveProperty(key);
  }
});

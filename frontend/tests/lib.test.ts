import { describe, expect, it } from "vitest";
import { livePortfolio } from "@/lib/portfolio";
import { squarify } from "@/lib/treemap";
import type { Portfolio, PriceUpdate } from "@/lib/types";
import { applyUpdate, type PriceState } from "@/lib/usePrices";

const update = (ticker: string, price: number, timestamp: number): PriceUpdate => ({
  ticker,
  price,
  previous_price: price,
  timestamp,
  change: 0,
  change_percent: 0,
  direction: "flat",
});

describe("applyUpdate", () => {
  it("accumulates history and remembers the first price", () => {
    let state: PriceState = { prices: {}, history: {}, sessionOpen: {}, status: "reconnecting" };
    state = applyUpdate(state, { AAPL: update("AAPL", 100, 1) });
    const next = applyUpdate(state, { AAPL: update("AAPL", 101, 2) });
    expect(next.history.AAPL.map((p) => p.value)).toEqual([100, 101]);
    expect(next.sessionOpen.AAPL).toBe(100);
    expect(next.status).toBe("connected");
  });

  it("replaces the point within the same second", () => {
    const state = applyUpdate({ prices: {}, history: {}, sessionOpen: {}, status: "connected" }, { A: update("A", 1, 5.1) });
    const next = applyUpdate(state, { A: update("A", 2, 5.9) });
    expect(next.history.A).toEqual([{ time: 5, value: 2 }]);
  });
});

describe("livePortfolio", () => {
  it("revalues positions with streamed prices", () => {
    const portfolio: Portfolio = {
      cash_balance: 1000,
      positions_value: 1000,
      total_value: 2000,
      unrealized_pnl: 0,
      positions: [
        { ticker: "AAPL", quantity: 10, avg_cost: 100, current_price: 100, market_value: 1000, unrealized_pnl: 0, pnl_percent: 0 },
      ],
    };
    const live = livePortfolio(portfolio, { AAPL: update("AAPL", 110, 1) });
    expect(live.total_value).toBe(2100);
    expect(live.unrealized_pnl).toBe(100);
    expect(live.positions[0].pnl_percent).toBeCloseTo(10);
  });
});

describe("squarify", () => {
  it("fills the box with areas proportional to value", () => {
    const tiles = squarify([6, 6, 4, 3, 2, 2, 1], (v) => v, { x: 0, y: 0, w: 6, h: 4 });
    const totalArea = tiles.reduce((sum, t) => sum + t.rect.w * t.rect.h, 0);
    expect(totalArea).toBeCloseTo(24);
    for (const t of tiles) expect(t.rect.w * t.rect.h).toBeCloseTo(t.item);
  });

  it("ignores non-positive values", () => {
    expect(squarify([0, -1], (v) => v, { x: 0, y: 0, w: 1, h: 1 })).toEqual([]);
  });
});

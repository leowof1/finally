import { describe, expect, it } from "vitest";
import { pnlColor, revalue, sessionChange, treemap } from "./portfolio";
import type { Portfolio, Position } from "./types";

const pos = (ticker: string, quantity: number, avg_cost: number, price: number): Position => ({
  ticker,
  quantity,
  avg_cost,
  current_price: price,
  market_value: quantity * price,
  unrealized_pnl: quantity * (price - avg_cost),
  pnl_percent: ((price - avg_cost) / avg_cost) * 100,
});

describe("sessionChange", () => {
  it("computes percent change from first price", () => {
    expect(sessionChange(100, 110)).toBeCloseTo(10);
  });
  it("returns 0 without a first price", () => {
    expect(sessionChange(undefined, 110)).toBe(0);
  });
});

describe("revalue", () => {
  const portfolio: Portfolio = {
    cash_balance: 1000,
    total_value: 2000,
    unrealized_pnl: 0,
    positions: [pos("AAPL", 10, 100, 100)],
  };

  it("updates value and P&L from live prices", () => {
    const r = revalue(portfolio, { AAPL: 120 });
    expect(r.total_value).toBe(2200);
    expect(r.unrealized_pnl).toBe(200);
    expect(r.positions[0].pnl_percent).toBeCloseTo(20);
  });

  it("keeps positions without a live price unchanged", () => {
    expect(revalue(portfolio, {}).total_value).toBe(2000);
  });
});

describe("treemap", () => {
  it("covers the full area with weights summing to 1", () => {
    const rects = treemap([pos("A", 5, 10, 10), pos("B", 3, 10, 10), pos("C", 2, 10, 10)]);
    expect(rects).toHaveLength(3);
    const area = rects.reduce((s, r) => s + r.w * r.h, 0);
    expect(area).toBeCloseTo(10000);
    expect(rects.reduce((s, r) => s + r.weight, 0)).toBeCloseTo(1);
    expect(rects[0].ticker).toBe("A");
    expect(rects[0].w * rects[0].h).toBeCloseTo(5000);
  });

  it("returns nothing for an empty portfolio", () => {
    expect(treemap([])).toEqual([]);
  });
});

describe("pnlColor", () => {
  it("is green for profit and red for loss", () => {
    expect(pnlColor(2)).toContain("34,197,94");
    expect(pnlColor(-2)).toContain("239,68,68");
  });
});

import type { Portfolio, PriceUpdate } from "./types";

/** Revalue positions with the latest streamed prices so totals update live. */
export function livePortfolio(portfolio: Portfolio, prices: Record<string, PriceUpdate>): Portfolio {
  const positions = portfolio.positions.map((p) => {
    const current = prices[p.ticker]?.price ?? p.current_price;
    const cost = p.avg_cost * p.quantity;
    const marketValue = current * p.quantity;
    const pnl = marketValue - cost;
    return {
      ...p,
      current_price: current,
      market_value: marketValue,
      unrealized_pnl: pnl,
      pnl_percent: cost ? (pnl / cost) * 100 : 0,
    };
  });
  const positionsValue = positions.reduce((sum, p) => sum + p.market_value, 0);
  return {
    cash_balance: portfolio.cash_balance,
    positions_value: positionsValue,
    total_value: portfolio.cash_balance + positionsValue,
    unrealized_pnl: positions.reduce((sum, p) => sum + p.unrealized_pnl, 0),
    positions,
  };
}

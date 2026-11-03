/** Pure portfolio calculations used by the UI. */
import type { Portfolio, Position } from "./types";

/** Percent change from the first price seen this session. */
export function sessionChange(first: number | undefined, last: number) {
  if (!first) return 0;
  return ((last - first) / first) * 100;
}

/** Re-value positions with the latest streamed prices. */
export function revalue(
  portfolio: Portfolio,
  prices: Record<string, number>,
): Portfolio {
  const positions = portfolio.positions.map((p) => revaluePosition(p, prices[p.ticker]));
  const invested = positions.reduce((s, p) => s + p.market_value, 0);
  const pnl = positions.reduce((s, p) => s + p.unrealized_pnl, 0);
  return {
    ...portfolio,
    positions,
    total_value: portfolio.cash_balance + invested,
    unrealized_pnl: pnl,
  };
}

function revaluePosition(p: Position, price: number | undefined): Position {
  if (price == null) return p;
  const market_value = p.quantity * price;
  const cost = p.quantity * p.avg_cost;
  const unrealized_pnl = market_value - cost;
  return {
    ...p,
    current_price: price,
    market_value,
    unrealized_pnl,
    pnl_percent: cost ? (unrealized_pnl / cost) * 100 : 0,
  };
}

export interface Rect {
  ticker: string;
  pnlPercent: number;
  weight: number;
  x: number;
  y: number;
  w: number;
  h: number;
}

/** Binary-split treemap in a unit square (coordinates are 0..100 percentages). */
export function treemap(positions: Position[]): Rect[] {
  const items = positions
    .filter((p) => p.market_value > 0)
    .sort((a, b) => b.market_value - a.market_value);
  const total = items.reduce((s, p) => s + p.market_value, 0);
  const rects: Rect[] = [];
  split(items, total, { x: 0, y: 0, w: 100, h: 100 }, rects, total);
  return rects;
}

type Box = { x: number; y: number; w: number; h: number };

function split(items: Position[], sum: number, box: Box, out: Rect[], total: number) {
  if (items.length === 0) return;
  if (items.length === 1) {
    const p = items[0];
    out.push({ ticker: p.ticker, pnlPercent: p.pnl_percent, weight: p.market_value / total, ...box });
    return;
  }
  let acc = 0;
  let i = 0;
  while (i < items.length - 1 && acc + items[i].market_value <= sum / 2) acc += items[i++].market_value;
  if (i === 0) acc = items[i++].market_value;
  const frac = acc / sum;
  const [a, b] = divide(box, frac);
  split(items.slice(0, i), acc, a, out, total);
  split(items.slice(i), sum - acc, b, out, total);
}

function divide(box: Box, frac: number): [Box, Box] {
  if (box.w >= box.h) {
    const w = box.w * frac;
    return [{ ...box, w }, { ...box, x: box.x + w, w: box.w - w }];
  }
  const h = box.h * frac;
  return [{ ...box, h }, { ...box, y: box.y + h, h: box.h - h }];
}

/** Heatmap color: green for profit, red for loss, intensity by magnitude (caps at 5%). */
export function pnlColor(pnlPercent: number) {
  const t = Math.min(Math.abs(pnlPercent) / 5, 1);
  const alpha = 0.25 + 0.6 * t;
  return pnlPercent >= 0 ? `rgba(34,197,94,${alpha})` : `rgba(239,68,68,${alpha})`;
}

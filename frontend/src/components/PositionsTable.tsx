import { formatPercent, formatPrice, formatQty, formatUsd, signClass } from "@/utils/format";
import type { Position } from "@/utils/types";

const HEADERS = ["Ticker", "Qty", "Avg Cost", "Price", "P&L", "%"];

/** Tabular view of all open positions. */
export function PositionsTable({ positions }: { positions: Position[] }) {
  return (
    <table data-testid="positions-table" className="w-full tabular-nums">
      <thead className="sticky top-0 bg-panel text-muted">
        <tr>
          {HEADERS.map((h, i) => (
            <th key={h} className={`px-1.5 py-1 font-normal ${i === 0 ? "text-left" : "text-right"}`}>
              {h}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {positions.map((p) => (
          <tr key={p.ticker} data-testid={`position-row-${p.ticker}`} className="border-t border-border/50">
            <td className="px-1.5 py-1 font-bold text-primary">{p.ticker}</td>
            <td className="px-1.5 py-1 text-right">{formatQty(p.quantity)}</td>
            <td className="px-1.5 py-1 text-right">{formatPrice(p.avg_cost)}</td>
            <td className="px-1.5 py-1 text-right">{formatPrice(p.current_price)}</td>
            <td className={`px-1.5 py-1 text-right ${signClass(p.unrealized_pnl)}`}>{formatUsd(p.unrealized_pnl)}</td>
            <td className={`px-1.5 py-1 text-right ${signClass(p.pnl_percent)}`}>{formatPercent(p.pnl_percent)}</td>
          </tr>
        ))}
        {positions.length === 0 && (
          <tr>
            <td colSpan={HEADERS.length} className="px-2 py-3 text-center text-muted">
              No positions
            </td>
          </tr>
        )}
      </tbody>
    </table>
  );
}

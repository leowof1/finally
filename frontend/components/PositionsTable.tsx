import { money, percent, quantity, signedMoney, toneClass } from "@/lib/format";
import type { Position } from "@/lib/types";

interface Props {
  positions: Position[];
  onSelect: (ticker: string) => void;
}

export function PositionsTable({ positions, onSelect }: Props) {
  if (!positions.length) {
    return <p className="px-3 py-4 text-sm text-muted">No positions yet. Use the trade bar or ask the assistant to buy.</p>;
  }
  return (
    <table className="w-full text-sm" data-testid="positions-table">
      <thead className="text-xs text-muted">
        <tr className="border-b border-line text-right">
          <th className="px-3 py-1.5 text-left font-medium">Ticker</th>
          <th className="px-3 py-1.5 font-medium">Qty</th>
          <th className="px-3 py-1.5 font-medium">Avg cost</th>
          <th className="px-3 py-1.5 font-medium">Price</th>
          <th className="px-3 py-1.5 font-medium">Unrealized P&amp;L</th>
          <th className="px-3 py-1.5 font-medium">Change</th>
        </tr>
      </thead>
      <tbody>
        {positions.map((p) => (
          <tr
            key={p.ticker}
            data-testid={`position-${p.ticker}`}
            onClick={() => onSelect(p.ticker)}
            className="cursor-pointer border-b border-line/50 text-right hover:bg-raised"
          >
            <td className="px-3 py-1.5 text-left font-semibold">{p.ticker}</td>
            <td className="px-3 py-1.5">{quantity(p.quantity)}</td>
            <td className="px-3 py-1.5">{money(p.avg_cost)}</td>
            <td className="px-3 py-1.5">{money(p.current_price)}</td>
            <td className={`px-3 py-1.5 ${toneClass(p.unrealized_pnl)}`}>{signedMoney(p.unrealized_pnl)}</td>
            <td className={`px-3 py-1.5 ${toneClass(p.pnl_percent)}`}>{percent(p.pnl_percent)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

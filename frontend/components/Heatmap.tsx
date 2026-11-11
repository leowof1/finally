import { percent } from "@/lib/format";
import { squarify } from "@/lib/treemap";
import type { Position } from "@/lib/types";

/** Green for profit, red for loss; intensity saturates at +/-5%. */
export function pnlColor(pnlPercent: number): string {
  const strength = Math.min(Math.abs(pnlPercent) / 5, 1);
  const alpha = (0.25 + strength * 0.65).toFixed(2);
  if (pnlPercent > 0) return `rgb(63 182 139 / ${alpha})`;
  if (pnlPercent < 0) return `rgb(229 83 75 / ${alpha})`;
  return "rgb(123 136 152 / 0.3)";
}

interface Props {
  positions: Position[];
  onSelect: (ticker: string) => void;
}

/** Treemap of positions sized by market value and colored by unrealized P&L. */
export function Heatmap({ positions, onSelect }: Props) {
  if (!positions.length) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-muted">
        Buy a position to see it here, sized by its share of your holdings.
      </div>
    );
  }
  const tiles = squarify(positions, (p) => p.market_value, { x: 0, y: 0, w: 100, h: 100 });
  return (
    <div className="relative h-full w-full" data-testid="heatmap">
      {tiles.map(({ item, rect }) => (
        <button
          type="button"
          key={item.ticker}
          data-testid={`tile-${item.ticker}`}
          onClick={() => onSelect(item.ticker)}
          title={`${item.ticker}: ${percent(item.pnl_percent)}`}
          className="absolute flex flex-col items-center justify-center overflow-hidden border border-ink text-xs"
          style={{
            left: `${rect.x}%`,
            top: `${rect.y}%`,
            width: `${rect.w}%`,
            height: `${rect.h}%`,
            background: pnlColor(item.pnl_percent),
          }}
        >
          <span className="font-semibold">{item.ticker}</span>
          <span>{percent(item.pnl_percent)}</span>
        </button>
      ))}
    </div>
  );
}

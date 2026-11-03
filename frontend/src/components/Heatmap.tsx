import { formatPercent } from "@/utils/format";
import { pnlColor, treemap } from "@/utils/portfolio";
import type { Position } from "@/utils/types";

/** Treemap of positions: area = portfolio weight, color = P&L %. */
export function Heatmap({ positions }: { positions: Position[] }) {
  const rects = treemap(positions);
  return (
    <div data-testid="heatmap" className="relative h-full w-full">
      {rects.length === 0 && (
        <p className="flex h-full items-center justify-center text-muted">No positions yet</p>
      )}
      {rects.map((r) => (
        <div
          key={r.ticker}
          data-testid={`heatmap-cell-${r.ticker}`}
          title={`${r.ticker} ${(r.weight * 100).toFixed(1)}% weight`}
          className="absolute flex flex-col items-center justify-center overflow-hidden border border-bg text-center"
          style={{
            left: `${r.x}%`,
            top: `${r.y}%`,
            width: `${r.w}%`,
            height: `${r.h}%`,
            backgroundColor: pnlColor(r.pnlPercent),
          }}
        >
          <span className="font-bold">{r.ticker}</span>
          <span className="text-[10px]">{formatPercent(r.pnlPercent)}</span>
        </div>
      ))}
    </div>
  );
}

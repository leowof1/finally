"use client";
import { useFlash } from "@/hooks/useFlash";
import type { PricePoint } from "@/hooks/usePriceStream";
import { formatPercent, formatPrice, signClass } from "@/utils/format";
import { sessionChange } from "@/utils/portfolio";
import { Sparkline } from "./Sparkline";

interface Props {
  ticker: string;
  price: number | null;
  firstPrice?: number;
  points: PricePoint[];
  selected: boolean;
  onSelect: (ticker: string) => void;
  onRemove: (ticker: string) => void;
}

/** One watchlist line: symbol, flashing price, session change, sparkline. */
export function WatchlistRow({ ticker, price, firstPrice, points, selected, onSelect, onRemove }: Props) {
  const flash = useFlash(price);
  const change = price == null ? 0 : sessionChange(firstPrice, price);
  return (
    <tr
      data-testid={`watchlist-row-${ticker}`}
      onClick={() => onSelect(ticker)}
      className={`group cursor-pointer border-b border-border/50 hover:bg-panel-2 ${selected ? "bg-panel-2" : ""}`}
    >
      <td className={`px-2 py-1 font-bold ${selected ? "text-accent" : "text-primary"}`}>{ticker}</td>
      <td data-testid={`price-${ticker}`} className={`px-2 py-1 text-right tabular-nums ${flash}`}>
        {formatPrice(price)}
      </td>
      <td className={`px-2 py-1 text-right tabular-nums ${signClass(change)}`}>{formatPercent(change)}</td>
      <td className="px-1 py-1">
        <Sparkline points={points} />
      </td>
      <td className="w-5 pr-1 text-right">
        <button
          data-testid={`watchlist-remove-${ticker}`}
          aria-label={`Remove ${ticker}`}
          onClick={(e) => {
            e.stopPropagation();
            onRemove(ticker);
          }}
          className="text-muted opacity-30 hover:text-down group-hover:opacity-100 focus:opacity-100"
        >
          x
        </button>
      </td>
    </tr>
  );
}

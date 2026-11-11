"use client";

import { useState } from "react";
import { percent, toneClass } from "@/lib/format";
import type { PricePoint, PriceUpdate } from "@/lib/types";
import { Sparkline } from "./Sparkline";
import { useFlash } from "./useFlash";

interface RowProps {
  ticker: string;
  update?: PriceUpdate;
  open?: number;
  points: PricePoint[];
  selected: boolean;
  onSelect: (ticker: string) => void;
  onRemove: (ticker: string) => void;
}

function WatchlistRow({ ticker, update, open, points, selected, onSelect, onRemove }: RowProps) {
  const flash = useFlash(update?.price);
  const change = update && open ? ((update.price - open) / open) * 100 : 0;
  return (
    <li
      data-testid={`watch-${ticker}`}
      className={`group flex items-center gap-2 border-l-2 px-3 py-1.5 ${
        selected ? "border-accent bg-raised" : "border-transparent hover:bg-raised/60"
      }`}
    >
      <button
        type="button"
        onClick={() => onSelect(ticker)}
        className="flex flex-1 items-center gap-2 text-left"
        aria-pressed={selected}
      >
        <span className="w-14 font-semibold">{ticker}</span>
        <Sparkline points={points} />
        <span className="ml-auto flex flex-col items-end leading-tight">
          <span data-testid={`price-${ticker}`} className={`rounded px-1 ${flash}`}>
            {update ? update.price.toFixed(2) : "--"}
          </span>
          <span className={`text-xs ${toneClass(change)}`}>{percent(change)}</span>
        </span>
      </button>
      <button
        type="button"
        onClick={() => onRemove(ticker)}
        aria-label={`Remove ${ticker} from watchlist`}
        className="text-muted opacity-0 hover:text-down focus-visible:opacity-100 group-hover:opacity-100"
      >
        &times;
      </button>
    </li>
  );
}

interface Props {
  tickers: string[];
  prices: Record<string, PriceUpdate>;
  history: Record<string, PricePoint[]>;
  sessionOpen: Record<string, number>;
  selected: string;
  onSelect: (ticker: string) => void;
  onAdd: (ticker: string) => Promise<void>;
  onRemove: (ticker: string) => void;
}

export function Watchlist({ tickers, prices, history, sessionOpen, selected, onSelect, onAdd, onRemove }: Props) {
  const [draft, setDraft] = useState("");
  const [error, setError] = useState("");

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const ticker = draft.trim().toUpperCase();
    if (!ticker) return;
    try {
      await onAdd(ticker);
      setDraft("");
      setError("");
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <section aria-label="Watchlist" className="flex min-h-0 flex-col">
      <header className="flex items-baseline justify-between px-3 pb-1 pt-3">
        <h2 className="text-sm font-semibold text-muted">Watchlist</h2>
        <span className="text-xs text-muted" title="Change since this page was opened">
          since open
        </span>
      </header>
      <ul className="min-h-0 flex-1 overflow-y-auto">
        {tickers.map((ticker) => (
          <WatchlistRow
            key={ticker}
            ticker={ticker}
            update={prices[ticker]}
            open={sessionOpen[ticker]}
            points={history[ticker] ?? []}
            selected={ticker === selected}
            onSelect={onSelect}
            onRemove={onRemove}
          />
        ))}
      </ul>
      <form onSubmit={submit} className="border-t border-line p-3">
        <div className="flex gap-2">
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Add ticker"
            aria-label="Ticker to add"
            className="min-w-0 flex-1 rounded border border-line bg-ink px-2 py-1 uppercase placeholder:normal-case placeholder:text-muted"
          />
          <button type="submit" className="rounded bg-submit px-3 py-1 font-semibold text-white">
            Add
          </button>
        </div>
        {error && <p role="alert" className="mt-1 text-xs text-down">{error}</p>}
      </form>
    </section>
  );
}

"use client";
import { useState, type FormEvent } from "react";
import type { StreamState } from "@/hooks/usePriceStream";
import type { WatchlistItem } from "@/utils/types";
import { Panel } from "./Panel";
import { WatchlistRow } from "./WatchlistRow";

interface Props {
  items: WatchlistItem[];
  stream: StreamState;
  selected: string | null;
  onSelect: (ticker: string) => void;
  onAdd: (ticker: string) => Promise<void>;
  onRemove: (ticker: string) => void;
}

/** Watchlist table with an add-ticker form. */
export function Watchlist({ items, stream, selected, onSelect, onAdd, onRemove }: Props) {
  const [ticker, setTicker] = useState("");
  const [error, setError] = useState("");

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!ticker.trim()) return;
    try {
      await onAdd(ticker.trim().toUpperCase());
      setTicker("");
      setError("");
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <Panel title="Watchlist" className="h-full">
      <form onSubmit={submit} className="flex gap-1 border-b border-border p-1">
        <input
          data-testid="watchlist-add-input"
          value={ticker}
          onChange={(e) => setTicker(e.target.value)}
          placeholder="Add ticker"
          className="min-w-0 flex-1 border border-border bg-bg px-2 py-1 uppercase outline-none focus:border-primary"
        />
        <button data-testid="watchlist-add-button" className="bg-primary px-2 font-semibold text-bg hover:opacity-90">
          Add
        </button>
      </form>
      {error && <p className="px-2 py-1 text-down">{error}</p>}
      <table className="w-full">
        <tbody>
          {items.map(({ ticker: t, price }) => (
            <WatchlistRow
              key={t}
              ticker={t}
              price={stream.prices[t]?.price ?? price}
              firstPrice={stream.firstPrices[t]}
              points={stream.history[t] ?? []}
              selected={t === selected}
              onSelect={onSelect}
              onRemove={onRemove}
            />
          ))}
        </tbody>
      </table>
    </Panel>
  );
}

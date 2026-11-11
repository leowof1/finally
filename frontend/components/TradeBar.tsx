"use client";

import { useEffect, useState } from "react";

interface Props {
  ticker: string;
  onTrade: (ticker: string, quantity: number, side: "buy" | "sell") => Promise<void>;
}

/** Market order entry: ticker, quantity, buy and sell. */
export function TradeBar({ ticker, onTrade }: Props) {
  const [symbol, setSymbol] = useState(ticker);
  const [qty, setQty] = useState("1");
  const [status, setStatus] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => setSymbol(ticker), [ticker]);

  async function trade(side: "buy" | "sell") {
    const amount = Number(qty);
    if (!symbol.trim() || !(amount > 0)) {
      setStatus({ ok: false, text: "Enter a ticker and a quantity above zero." });
      return;
    }
    setBusy(true);
    try {
      await onTrade(symbol.trim().toUpperCase(), amount, side);
      setStatus({ ok: true, text: `${side === "buy" ? "Bought" : "Sold"} ${amount} ${symbol.toUpperCase()}` });
    } catch (err) {
      setStatus({ ok: false, text: (err as Error).message });
    } finally {
      setBusy(false);
    }
  }

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        trade("buy");
      }}
      className="flex flex-wrap items-center gap-2 px-3 py-2"
      aria-label="Trade"
    >
      <input
        value={symbol}
        onChange={(e) => setSymbol(e.target.value)}
        aria-label="Trade ticker"
        className="w-24 rounded border border-line bg-ink px-2 py-1 uppercase"
      />
      <input
        value={qty}
        onChange={(e) => setQty(e.target.value)}
        aria-label="Quantity"
        type="number"
        min="0"
        step="any"
        className="w-24 rounded border border-line bg-ink px-2 py-1"
      />
      <button
        type="submit"
        disabled={busy}
        className="rounded bg-up px-4 py-1 font-semibold text-ink disabled:opacity-50"
      >
        Buy
      </button>
      <button
        type="button"
        disabled={busy}
        onClick={() => trade("sell")}
        className="rounded bg-down px-4 py-1 font-semibold text-ink disabled:opacity-50"
      >
        Sell
      </button>
      {status && (
        <span role="status" className={`text-sm ${status.ok ? "text-up" : "text-down"}`}>
          {status.text}
        </span>
      )}
    </form>
  );
}

"use client";
import { useState } from "react";
import type { Side } from "@/utils/types";

interface Props {
  defaultTicker: string | null;
  onTrade: (ticker: string, quantity: number, side: Side) => Promise<void>;
}

/** Market order entry: ticker, quantity, buy/sell. */
export function TradeBar({ defaultTicker, onTrade }: Props) {
  const [ticker, setTicker] = useState("");
  const [qty, setQty] = useState("1");
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(side: Side) {
    const t = (ticker || defaultTicker || "").trim().toUpperCase();
    const q = Number(qty);
    if (!t || !(q > 0)) return setMsg({ ok: false, text: "Enter a ticker and a positive quantity" });
    setBusy(true);
    try {
      await onTrade(t, q, side);
      setMsg({ ok: true, text: `${side === "buy" ? "Bought" : "Sold"} ${q} ${t}` });
    } catch (err) {
      setMsg({ ok: false, text: (err as Error).message });
    } finally {
      setBusy(false);
    }
  }

  const input = "border border-border bg-bg px-2 py-1 outline-none focus:border-primary";
  return (
    <div className="flex flex-wrap items-center gap-2 border border-border bg-panel px-2 py-1.5">
      <span className="text-[11px] font-semibold uppercase tracking-wider text-accent">Trade</span>
      <input
        data-testid="trade-ticker"
        value={ticker}
        onChange={(e) => setTicker(e.target.value)}
        placeholder={defaultTicker ?? "Ticker"}
        className={`${input} w-24 uppercase`}
      />
      <input
        data-testid="trade-quantity"
        type="number"
        min="0"
        step="any"
        value={qty}
        onChange={(e) => setQty(e.target.value)}
        className={`${input} w-24`}
      />
      <button
        data-testid="trade-buy"
        disabled={busy}
        onClick={() => submit("buy")}
        className="bg-up px-4 py-1 font-bold text-bg hover:opacity-90 disabled:opacity-50"
      >
        BUY
      </button>
      <button
        data-testid="trade-sell"
        disabled={busy}
        onClick={() => submit("sell")}
        className="bg-down px-4 py-1 font-bold text-bg hover:opacity-90 disabled:opacity-50"
      >
        SELL
      </button>
      {msg && (
        <span data-testid="trade-message" className={msg.ok ? "text-up" : "text-down"}>
          {msg.text}
        </span>
      )}
    </div>
  );
}

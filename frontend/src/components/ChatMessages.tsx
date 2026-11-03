import { formatPrice, formatQty } from "@/utils/format";
import type { ChatMessage, ChatTrade, ChatWatchlistChange } from "@/utils/types";

function TradeLine({ t }: { t: ChatTrade }) {
  const ok = t.status === "executed";
  return (
    <li data-testid="chat-trade" className={ok ? "text-up" : "text-down"}>
      {ok ? (t.side === "buy" ? "Bought" : "Sold") : `Failed to ${t.side}`} {formatQty(t.quantity)} {t.ticker}
      {ok && t.price != null && ` @ ${formatPrice(t.price)}`}
      {t.error && ` - ${t.error}`}
    </li>
  );
}

function WatchLine({ c }: { c: ChatWatchlistChange }) {
  const ok = c.status === "executed";
  return (
    <li data-testid="chat-watchlist-change" className={ok ? "text-primary" : "text-down"}>
      Watchlist {c.action} {c.ticker}
      {!ok && ` failed${c.error ? ` - ${c.error}` : ""}`}
    </li>
  );
}

/** One chat bubble with inline action confirmations. */
export function ChatBubble({ m }: { m: ChatMessage }) {
  const user = m.role === "user";
  return (
    <div
      data-testid="chat-message"
      data-role={m.role}
      className={`max-w-[90%] border px-2 py-1.5 ${user ? "self-end border-primary/40 bg-primary/10" : "self-start border-border bg-panel-2"}`}
    >
      <p className="whitespace-pre-wrap">{m.content}</p>
      {(m.trades?.length || m.watchlist_changes?.length) ? (
        <ul className="mt-1 border-t border-border pt-1 text-[11px]">
          {m.trades?.map((t, i) => <TradeLine key={`t${i}`} t={t} />)}
          {m.watchlist_changes?.map((c, i) => <WatchLine key={`w${i}`} c={c} />)}
        </ul>
      ) : null}
    </div>
  );
}

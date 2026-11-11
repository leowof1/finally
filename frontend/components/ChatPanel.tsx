"use client";

import { useEffect, useRef, useState } from "react";
import { money } from "@/lib/format";
import type { ChatActions, ChatMessage, ChatReply } from "@/lib/types";

function ActionList({ actions }: { actions: ChatActions }) {
  const items = [
    ...actions.watchlist_changes.map((w) => ({
      key: `w-${w.ticker}-${w.action}`,
      ok: w.status === "ok",
      text:
        w.status === "ok"
          ? `${w.action === "add" ? "Added" : "Removed"} ${w.ticker} ${w.action === "add" ? "to" : "from"} watchlist`
          : `Watchlist ${w.action} ${w.ticker} failed: ${w.error}`,
    })),
    ...actions.trades.map((t, i) => ({
      key: `t-${i}`,
      ok: t.status === "ok",
      text:
        t.status === "ok"
          ? `${t.side === "buy" ? "Bought" : "Sold"} ${t.quantity} ${t.ticker} at ${money(t.price ?? 0)}`
          : `${t.side === "buy" ? "Buy" : "Sell"} ${t.quantity} ${t.ticker} failed`,
    })),
  ];
  if (!items.length) return null;
  return (
    <ul className="mt-2 space-y-1">
      {items.map((item) => (
        <li
          key={item.key}
          data-testid="chat-action"
          className={`rounded border-l-2 bg-ink px-2 py-1 text-xs ${item.ok ? "border-up text-up" : "border-down text-down"}`}
        >
          {item.text}
        </li>
      ))}
    </ul>
  );
}

interface Props {
  open: boolean;
  onToggle: () => void;
  onSend: (message: string) => Promise<ChatReply>;
}

/** Docked assistant panel with history, loading state and inline action confirmations. */
export function ChatPanel({ open, onToggle, onSend }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [loading, setLoading] = useState(false);
  const log = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (log.current) log.current.scrollTop = log.current.scrollHeight;
  }, [messages, loading]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const text = draft.trim();
    if (!text || loading) return;
    setDraft("");
    setMessages((m) => [...m, { role: "user", content: text }]);
    setLoading(true);
    try {
      const reply = await onSend(text);
      setMessages((m) => [...m, { role: "assistant", content: reply.message, actions: reply.actions }]);
    } catch (err) {
      setMessages((m) => [...m, { role: "assistant", content: `Message not sent: ${(err as Error).message}` }]);
    } finally {
      setLoading(false);
    }
  }

  if (!open) {
    return (
      <button
        type="button"
        onClick={onToggle}
        className="border-l border-line bg-panel px-2 text-sm text-muted [writing-mode:vertical-rl] hover:text-text"
      >
        Open assistant
      </button>
    );
  }

  return (
    <aside aria-label="AI assistant" className="flex w-full flex-col border-l border-line bg-panel lg:w-[22rem]">
      <header className="flex items-center justify-between border-b border-line px-3 py-2">
        <h2 className="font-semibold">FinAlly assistant</h2>
        <button type="button" onClick={onToggle} className="text-sm text-muted hover:text-text" aria-label="Collapse assistant">
          Hide
        </button>
      </header>
      <div ref={log} className="min-h-0 flex-1 space-y-3 overflow-y-auto p-3 text-sm" data-testid="chat-log">
        {!messages.length && (
          <p className="text-muted">
            Ask about your portfolio, or tell me to trade: &ldquo;Buy 5 NVDA&rdquo;, &ldquo;What&rsquo;s my biggest risk?&rdquo;,
            &ldquo;Add PYPL to my watchlist&rdquo;.
          </p>
        )}
        {messages.map((m, i) => (
          <div
            key={i}
            data-testid={`chat-${m.role}`}
            className={m.role === "user" ? "ml-8 rounded bg-raised px-3 py-2" : "mr-4"}
          >
            <p className="whitespace-pre-wrap">{m.content}</p>
            {m.actions && <ActionList actions={m.actions} />}
          </div>
        ))}
        {loading && (
          <p className="animate-pulse text-muted" data-testid="chat-loading">
            Thinking&hellip;
          </p>
        )}
      </div>
      <form onSubmit={submit} className="flex gap-2 border-t border-line p-3">
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Message FinAlly"
          aria-label="Chat message"
          className="min-w-0 flex-1 rounded border border-line bg-ink px-2 py-1.5 placeholder:text-muted"
        />
        <button type="submit" disabled={loading} className="rounded bg-submit px-4 font-semibold text-white disabled:opacity-50">
          Send
        </button>
      </form>
    </aside>
  );
}

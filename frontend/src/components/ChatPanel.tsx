"use client";
import { useEffect, useRef, useState, type FormEvent } from "react";
import type { ChatMessage } from "@/utils/types";
import { ChatBubble } from "./ChatMessages";

interface Props {
  messages: ChatMessage[];
  loading: boolean;
  onSend: (text: string) => void;
}

/** Collapsible AI assistant sidebar. */
export function ChatPanel({ messages, loading, onSend }: Props) {
  const [open, setOpen] = useState(true);
  const [text, setText] = useState("");
  const end = useRef<HTMLDivElement>(null);

  useEffect(() => {
    end.current?.scrollIntoView?.({ block: "end" });
  }, [messages, loading]);

  function submit(e: FormEvent) {
    e.preventDefault();
    if (!text.trim() || loading) return;
    onSend(text.trim());
    setText("");
  }

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="border-l border-border bg-panel px-1 text-accent [writing-mode:vertical-rl]"
      >
        AI ASSISTANT
      </button>
    );
  }

  return (
    <aside className="flex w-80 shrink-0 flex-col border-l border-border bg-panel">
      <header className="flex items-center justify-between border-b border-border px-2 py-1">
        <h2 className="text-[11px] font-semibold uppercase tracking-wider text-accent">AI Assistant</h2>
        <button onClick={() => setOpen(false)} aria-label="Collapse chat" className="text-muted hover:text-text">
          &raquo;
        </button>
      </header>
      <div className="flex min-h-0 flex-1 flex-col gap-2 overflow-auto p-2">
        {messages.length === 0 && (
          <p className="text-muted">Ask about your portfolio, or say &quot;buy 5 NVDA&quot;.</p>
        )}
        {messages.map((m, i) => (
          <ChatBubble key={i} m={m} />
        ))}
        {loading && (
          <p data-testid="chat-loading" className="animate-pulse text-muted">
            FinAlly is thinking...
          </p>
        )}
        <div ref={end} />
      </div>
      <form onSubmit={submit} className="flex gap-1 border-t border-border p-2">
        <input
          data-testid="chat-input"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Message FinAlly..."
          className="min-w-0 flex-1 border border-border bg-bg px-2 py-1 outline-none focus:border-primary"
        />
        <button
          data-testid="chat-send"
          disabled={loading}
          className="bg-secondary px-3 font-semibold text-white hover:opacity-90 disabled:opacity-50"
        >
          Send
        </button>
      </form>
    </aside>
  );
}

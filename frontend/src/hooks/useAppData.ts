"use client";
import { useCallback, useEffect, useState } from "react";
import * as api from "@/utils/api";
import type { ChatMessage, Portfolio, Side, Snapshot, WatchlistItem } from "@/utils/types";

const HISTORY_POLL_MS = 30_000;

/** Loads and mutates portfolio, watchlist, history and chat via the REST API. */
export function useAppData() {
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [watchlist, setWatchlist] = useState<WatchlistItem[]>([]);
  const [history, setHistory] = useState<Snapshot[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [chatLoading, setChatLoading] = useState(false);

  const refresh = useCallback(async () => {
    const [p, w, h] = await Promise.all([api.getPortfolio(), api.getWatchlist(), api.getHistory()]);
    setPortfolio(p);
    setWatchlist(w);
    setHistory(h);
  }, []);

  useEffect(() => {
    refresh().catch(console.error);
    api.getChatHistory().then(setMessages).catch(console.error);
    const id = setInterval(() => api.getHistory().then(setHistory).catch(console.error), HISTORY_POLL_MS);
    return () => clearInterval(id);
  }, [refresh]);

  const trade = async (ticker: string, quantity: number, side: Side) => {
    const res = await api.trade(ticker, quantity, side);
    setPortfolio(res.portfolio);
    setHistory(await api.getHistory());
  };

  const addTicker = async (ticker: string) => {
    await api.addTicker(ticker);
    setWatchlist(await api.getWatchlist());
  };

  const removeTicker = async (ticker: string) => {
    await api.removeTicker(ticker);
    setWatchlist((w) => w.filter((i) => i.ticker !== ticker));
  };

  const sendChat = async (text: string) => {
    setMessages((m) => [...m, { role: "user", content: text }]);
    setChatLoading(true);
    try {
      const res = await api.sendChat(text);
      setMessages((m) => [...m, {
          role: "assistant",
          content: res.message,
          trades: res.trades,
          watchlist_changes: res.watchlist_changes,
        }]);
      await refresh();
    } catch (err) {
      setMessages((m) => [...m, { role: "assistant", content: `Error: ${(err as Error).message}` }]);
    } finally {
      setChatLoading(false);
    }
  };

  return { portfolio, watchlist, history, messages, chatLoading, trade, addTicker, removeTicker, sendChat };
}

/** Thin fetch wrappers for the same-origin backend API. */
import type {
  ChatMessage,
  ChatResponse,
  Portfolio,
  Side,
  Snapshot,
  WatchlistItem,
} from "./types";

export class ApiError extends Error {}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json" },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(body.detail ?? `Request failed (${res.status})`);
  }
  return res.status === 204 ? (undefined as T) : res.json();
}

const post = (body: unknown): RequestInit => ({
  method: "POST",
  body: JSON.stringify(body),
});

export const getPortfolio = () => request<Portfolio>("/api/portfolio");

export const getHistory = () => request<Snapshot[]>("/api/portfolio/history");

export const trade = (ticker: string, quantity: number, side: Side) =>
  request<{ portfolio: Portfolio }>(
    "/api/portfolio/trade",
    post({ ticker, quantity, side }),
  );

export const getWatchlist = () => request<WatchlistItem[]>("/api/watchlist");

export const addTicker = (ticker: string) =>
  request<{ ticker: string }>("/api/watchlist", post({ ticker }));

export const removeTicker = (ticker: string) =>
  request<void>(`/api/watchlist/${ticker}`, { method: "DELETE" });

export const sendChat = (message: string) =>
  request<ChatResponse>("/api/chat", post({ message }));

interface RawChatMessage {
  role: "user" | "assistant";
  content: string;
  actions: Partial<ChatResponse> | null;
}

export async function getChatHistory(): Promise<ChatMessage[]> {
  const rows = await request<RawChatMessage[]>("/api/chat/history");
  return rows.map((r) => ({
    role: r.role,
    content: r.content,
    trades: r.actions?.trades,
    watchlist_changes: r.actions?.watchlist_changes,
  }));
}

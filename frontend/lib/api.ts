import type { ChatReply, Portfolio, PriceUpdate, Snapshot } from "./types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json" },
  });
  const body = await response.json();
  if (!response.ok) {
    const detail = typeof body.detail === "string" ? body.detail : "Request failed";
    throw new Error(detail);
  }
  return body as T;
}

export const api = {
  portfolio: () => request<Portfolio>("/api/portfolio"),
  history: () => request<Snapshot[]>("/api/portfolio/history"),
  watchlist: () => request<(PriceUpdate | { ticker: string; price: null })[]>("/api/watchlist"),
  trade: (ticker: string, quantity: number, side: "buy" | "sell") =>
    request<{ portfolio: Portfolio }>("/api/portfolio/trade", {
      method: "POST",
      body: JSON.stringify({ ticker, quantity, side }),
    }),
  addTicker: (ticker: string) =>
    request("/api/watchlist", { method: "POST", body: JSON.stringify({ ticker }) }),
  removeTicker: (ticker: string) =>
    request(`/api/watchlist/${encodeURIComponent(ticker)}`, { method: "DELETE" }),
  chat: (message: string) =>
    request<ChatReply>("/api/chat", { method: "POST", body: JSON.stringify({ message }) }),
};

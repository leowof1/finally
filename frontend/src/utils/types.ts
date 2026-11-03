/** Shared API types, mirroring planning/TEAM_CONTRACT.md. */

export type Direction = "up" | "down" | "flat";

export interface PriceUpdate {
  ticker: string;
  price: number;
  previous_price: number;
  timestamp: number;
  change: number;
  change_percent: number;
  direction: Direction;
}

export interface Position {
  ticker: string;
  quantity: number;
  avg_cost: number;
  current_price: number;
  market_value: number;
  unrealized_pnl: number;
  pnl_percent: number;
}

export interface Portfolio {
  cash_balance: number;
  total_value: number;
  unrealized_pnl: number;
  positions: Position[];
}

export interface Snapshot {
  total_value: number;
  recorded_at: string;
}

export interface WatchlistItem {
  ticker: string;
  price: number | null;
  previous_price: number | null;
  change_percent: number | null;
  direction: Direction | null;
  added_at: string;
}

export type Side = "buy" | "sell";

export interface ChatTrade {
  ticker: string;
  side: Side;
  quantity: number;
  status: "executed" | "failed";
  price?: number;
  error?: string;
}

export interface ChatWatchlistChange {
  ticker: string;
  action: "add" | "remove";
  status: "executed" | "failed";
  error?: string;
}

export interface ChatResponse {
  message: string;
  trades: ChatTrade[];
  watchlist_changes: ChatWatchlistChange[];
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  trades?: ChatTrade[];
  watchlist_changes?: ChatWatchlistChange[];
}

export type ConnectionStatus = "connected" | "reconnecting" | "disconnected";

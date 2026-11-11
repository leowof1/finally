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

export interface PricePoint {
  time: number;
  value: number;
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
  positions_value: number;
  total_value: number;
  unrealized_pnl: number;
  positions: Position[];
}

export interface Snapshot {
  total_value: number;
  recorded_at: string;
}

export interface TradeResult {
  ticker: string;
  side: "buy" | "sell";
  quantity: number;
  status: "ok" | "error";
  price?: number;
  error?: string;
}

export interface WatchlistResult {
  ticker: string;
  action: "add" | "remove";
  status: "ok" | "error";
  error?: string;
}

export interface ChatActions {
  trades: TradeResult[];
  watchlist_changes: WatchlistResult[];
}

export interface ChatReply {
  message: string;
  actions: ChatActions;
  portfolio: Portfolio;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  actions?: ChatActions;
}

export type ConnectionStatus = "connected" | "reconnecting" | "disconnected";

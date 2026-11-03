"use client";
import { useEffect, useState } from "react";
import type { ConnectionStatus, PriceUpdate } from "@/utils/types";

const MAX_POINTS = 500;
const RECONNECT_MS = 2000;

export interface PricePoint {
  time: number;
  value: number;
}

export interface StreamState {
  prices: Record<string, PriceUpdate>;
  history: Record<string, PricePoint[]>;
  firstPrices: Record<string, number>;
}

const EMPTY: StreamState = { prices: {}, history: {}, firstPrices: {} };

/** Merge one SSE payload into the accumulated stream state. */
export function applyUpdate(
  state: StreamState,
  batch: Record<string, PriceUpdate>,
): StreamState {
  const history = { ...state.history };
  const firstPrices = { ...state.firstPrices };
  for (const u of Object.values(batch)) {
    const prev = history[u.ticker] ?? [];
    if (prev.at(-1)?.time === u.timestamp) continue;
    history[u.ticker] = [...prev, { time: u.timestamp, value: u.price }].slice(-MAX_POINTS);
    firstPrices[u.ticker] ??= u.price;
  }
  return { prices: { ...state.prices, ...batch }, history, firstPrices };
}

/** Subscribe to /api/stream/prices and accumulate prices and history. */
export function usePriceStream() {
  const [state, setState] = useState<StreamState>(EMPTY);
  const [status, setStatus] = useState<ConnectionStatus>("reconnecting");

  useEffect(() => {
    let es: EventSource;
    let timer: ReturnType<typeof setTimeout>;

    function connect() {
      es = new EventSource("/api/stream/prices");
      es.onopen = () => setStatus("connected");
      es.onmessage = (e) => {
        setStatus("connected");
        setState((s) => applyUpdate(s, JSON.parse(e.data)));
      };
      es.onerror = () => {
        setStatus("reconnecting");
        // The browser only auto-retries while CONNECTING; a CLOSED stream needs a new EventSource.
        if (es.readyState === EventSource.CLOSED) timer = setTimeout(connect, RECONNECT_MS);
      };
    }

    connect();
    return () => {
      clearTimeout(timer);
      es.close();
    };
  }, []);

  return { ...state, status };
}

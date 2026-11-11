"use client";

import { useEffect, useState } from "react";
import type { ConnectionStatus, PricePoint, PriceUpdate } from "./types";

const MAX_POINTS = 600;

export interface PriceState {
  prices: Record<string, PriceUpdate>;
  history: Record<string, PricePoint[]>;
  sessionOpen: Record<string, number>;
  status: ConnectionStatus;
}

const empty: PriceState = { prices: {}, history: {}, sessionOpen: {}, status: "reconnecting" };

/** Merge one SSE payload into the accumulated price state. */
export function applyUpdate(state: PriceState, payload: Record<string, PriceUpdate>): PriceState {
  const history = { ...state.history };
  const sessionOpen = { ...state.sessionOpen };
  for (const update of Object.values(payload)) {
    const series = history[update.ticker] ?? [];
    const time = Math.floor(update.timestamp);
    const last = series[series.length - 1];
    const point = { time, value: update.price };
    history[update.ticker] =
      last && last.time === time
        ? [...series.slice(0, -1), point]
        : [...series, point].slice(-MAX_POINTS);
    sessionOpen[update.ticker] ??= update.price;
  }
  return { prices: payload, history, sessionOpen, status: "connected" };
}

/** Subscribe to the SSE price stream and accumulate history since page load. */
export function usePrices(): PriceState {
  const [state, setState] = useState<PriceState>(empty);

  useEffect(() => {
    const source = new EventSource("/api/stream/prices");
    source.onopen = () => setState((s) => ({ ...s, status: "connected" }));
    source.onmessage = (event) => setState((s) => applyUpdate(s, JSON.parse(event.data)));
    source.onerror = () =>
      setState((s) => ({
        ...s,
        status: source.readyState === EventSource.CLOSED ? "disconnected" : "reconnecting",
      }));
    return () => source.close();
  }, []);

  return state;
}

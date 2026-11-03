import { act, renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { applyUpdate, usePriceStream } from "./usePriceStream";

class FakeEventSource {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSED = 2;
  static instances: FakeEventSource[] = [];
  readyState = 0;
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onmessage: ((e: { data: string }) => void) | null = null;
  constructor(public url: string) {
    FakeEventSource.instances.push(this);
  }
  close() {
    this.readyState = 2;
  }
}

describe("usePriceStream reconnect", () => {
  it("creates a new EventSource after a CLOSED error", () => {
    vi.useFakeTimers();
    vi.stubGlobal("EventSource", FakeEventSource);
    const { result } = renderHook(() => usePriceStream());
    const first = FakeEventSource.instances.at(-1)!;
    act(() => first.onopen!());
    expect(result.current.status).toBe("connected");
    act(() => {
      first.readyState = 2;
      first.onerror!();
    });
    expect(result.current.status).toBe("reconnecting");
    const count = FakeEventSource.instances.length;
    act(() => vi.advanceTimersByTime(2000));
    expect(FakeEventSource.instances.length).toBe(count + 1);
    act(() => FakeEventSource.instances.at(-1)!.onopen!());
    expect(result.current.status).toBe("connected");
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });
});

const update = (price: number, timestamp: number) => ({
  AAPL: { ticker: "AAPL", price, previous_price: price, timestamp, change: 0, change_percent: 0, direction: "flat" as const },
});

describe("applyUpdate", () => {
  it("accumulates history and remembers the first price", () => {
    let s = applyUpdate({ prices: {}, history: {}, firstPrices: {} }, update(100, 1));
    s = applyUpdate(s, update(101, 2));
    s = applyUpdate(s, update(101, 2));
    expect(s.history.AAPL.map((p) => p.value)).toEqual([100, 101]);
    expect(s.firstPrices.AAPL).toBe(100);
    expect(s.prices.AAPL.price).toBe(101);
  });
});

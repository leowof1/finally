import { act, fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { Position } from "@/utils/types";
import { ChatPanel } from "./ChatPanel";
import { Header } from "./Header";
import { Heatmap } from "./Heatmap";
import { PositionsTable } from "./PositionsTable";
import { TradeBar } from "./TradeBar";
import { WatchlistRow } from "./WatchlistRow";

const position: Position = {
  ticker: "AAPL",
  quantity: 10,
  avg_cost: 100,
  current_price: 110,
  market_value: 1100,
  unrealized_pnl: 100,
  pnl_percent: 10,
};

function renderRow(price: number) {
  return (
    <table>
      <tbody>
        <WatchlistRow
          ticker="AAPL"
          price={price}
          firstPrice={100}
          points={[]}
          selected={false}
          onSelect={() => {}}
          onRemove={() => {}}
        />
      </tbody>
    </table>
  );
}

describe("WatchlistRow", () => {
  it("renders price and session change", () => {
    render(renderRow(105));
    expect(screen.getByTestId("price-AAPL")).toHaveTextContent("105.00");
    expect(screen.getByTestId("watchlist-row-AAPL")).toHaveTextContent("+5.00%");
  });

  it("flashes green on uptick and red on downtick, then fades", () => {
    vi.useFakeTimers();
    const { rerender } = render(renderRow(100));
    const cell = screen.getByTestId("price-AAPL");
    expect(cell).not.toHaveClass("flash-up");
    rerender(renderRow(101));
    expect(cell).toHaveClass("flash-up");
    act(() => vi.advanceTimersByTime(200));
    expect(cell).not.toHaveClass("flash-up");
    rerender(renderRow(99));
    expect(cell).toHaveClass("flash-down");
    vi.useRealTimers();
  });
});

describe("Header", () => {
  it("shows values and connection status", () => {
    render(<Header totalValue={10500} cash={9000} pnl={500} status="connected" />);
    expect(screen.getByTestId("total-value")).toHaveTextContent("$10,500.00");
    expect(screen.getByTestId("cash-balance")).toHaveTextContent("$9,000.00");
    expect(screen.getByTestId("connection-status")).toHaveClass("bg-up");
  });
});

describe("Portfolio views", () => {
  it("renders positions rows", () => {
    render(<PositionsTable positions={[position]} />);
    expect(screen.getByTestId("position-row-AAPL")).toHaveTextContent("+10.00%");
  });

  it("renders heatmap cells colored by P&L", () => {
    render(<Heatmap positions={[position, { ...position, ticker: "TSLA", pnl_percent: -3 }]} />);
    expect(screen.getByTestId("heatmap-cell-AAPL").style.backgroundColor).toContain("34, 197, 94");
    expect(screen.getByTestId("heatmap-cell-TSLA").style.backgroundColor).toContain("239, 68, 68");
  });
});

describe("TradeBar", () => {
  it("shows backend errors", async () => {
    const onTrade = vi.fn().mockRejectedValue(new Error("Insufficient cash"));
    render(<TradeBar defaultTicker="AAPL" onTrade={onTrade} />);
    fireEvent.change(screen.getByTestId("trade-quantity"), { target: { value: "1000" } });
    fireEvent.click(screen.getByTestId("trade-buy"));
    expect(await screen.findByText("Insufficient cash")).toBeInTheDocument();
    expect(onTrade).toHaveBeenCalledWith("AAPL", 1000, "buy");
  });
});

describe("ChatPanel", () => {
  it("renders messages with inline trade confirmations", () => {
    const messages = [
      { role: "user" as const, content: "buy AAPL" },
      {
        role: "assistant" as const,
        content: "Mock: bought 1 AAPL",
        trades: [{ ticker: "AAPL", side: "buy" as const, quantity: 1, status: "executed" as const, price: 190 }],
      },
    ];
    render(<ChatPanel messages={messages} loading={false} onSend={() => {}} />);
    expect(screen.getAllByTestId("chat-message")).toHaveLength(2);
    expect(screen.getByTestId("chat-trade")).toHaveTextContent("Bought 1 AAPL @ 190.00");
    expect(screen.queryByTestId("chat-loading")).toBeNull();
  });

  it("shows loading indicator and sends input", () => {
    const onSend = vi.fn();
    const { rerender } = render(<ChatPanel messages={[]} loading={false} onSend={onSend} />);
    fireEvent.change(screen.getByTestId("chat-input"), { target: { value: "hello" } });
    fireEvent.click(screen.getByTestId("chat-send"));
    expect(onSend).toHaveBeenCalledWith("hello");
    rerender(<ChatPanel messages={[]} loading onSend={onSend} />);
    expect(screen.getByTestId("chat-loading")).toBeInTheDocument();
  });
});

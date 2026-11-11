import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ChatPanel } from "@/components/ChatPanel";
import { Header } from "@/components/Header";
import { Heatmap, pnlColor } from "@/components/Heatmap";
import { PositionsTable } from "@/components/PositionsTable";
import { Watchlist } from "@/components/Watchlist";
import type { ChatReply, Position, PriceUpdate } from "@/lib/types";

const price = (ticker: string, value: number): PriceUpdate => ({
  ticker,
  price: value,
  previous_price: value,
  timestamp: 1,
  change: 0,
  change_percent: 0,
  direction: "flat",
});

const position: Position = {
  ticker: "AAPL",
  quantity: 10,
  avg_cost: 100,
  current_price: 110,
  market_value: 1100,
  unrealized_pnl: 100,
  pnl_percent: 10,
};

function renderWatchlist(prices: Record<string, PriceUpdate>, overrides = {}) {
  const props = {
    tickers: ["AAPL"],
    prices,
    history: {},
    sessionOpen: { AAPL: 100 },
    selected: "AAPL",
    onSelect: vi.fn(),
    onAdd: vi.fn().mockResolvedValue(undefined),
    onRemove: vi.fn(),
    ...overrides,
  };
  return { props, ...render(<Watchlist {...props} />) };
}

afterEach(() => vi.useRealTimers());

describe("Watchlist", () => {
  it("flashes green on an uptick and fades", () => {
    vi.useFakeTimers();
    const { props, rerender } = renderWatchlist({ AAPL: price("AAPL", 100) });
    rerender(<Watchlist {...props} prices={{ AAPL: price("AAPL", 101) }} />);
    expect(screen.getByTestId("price-AAPL")).toHaveClass("flash-up");
    act(() => vi.advanceTimersByTime(200));
    expect(screen.getByTestId("price-AAPL")).not.toHaveClass("flash-up");
  });

  it("flashes red on a downtick", () => {
    const { props, rerender } = renderWatchlist({ AAPL: price("AAPL", 100) });
    rerender(<Watchlist {...props} prices={{ AAPL: price("AAPL", 99) }} />);
    expect(screen.getByTestId("price-AAPL")).toHaveClass("flash-down");
  });

  it("shows change since session open", () => {
    renderWatchlist({ AAPL: price("AAPL", 105) });
    expect(screen.getByText("+5.00%")).toBeInTheDocument();
  });

  it("adds and removes tickers", async () => {
    const user = userEvent.setup();
    const { props } = renderWatchlist({ AAPL: price("AAPL", 100) });
    await user.type(screen.getByLabelText("Ticker to add"), "pypl");
    await user.click(screen.getByRole("button", { name: "Add" }));
    expect(props.onAdd).toHaveBeenCalledWith("PYPL");
    await user.click(screen.getByLabelText("Remove AAPL from watchlist"));
    expect(props.onRemove).toHaveBeenCalledWith("AAPL");
  });

  it("shows add errors", async () => {
    const user = userEvent.setup();
    renderWatchlist({}, { onAdd: vi.fn().mockRejectedValue(new Error("PYPL is already on the watchlist")) });
    await user.type(screen.getByLabelText("Ticker to add"), "PYPL");
    await user.click(screen.getByRole("button", { name: "Add" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("already on the watchlist");
  });
});

describe("Portfolio display", () => {
  it("renders positions with P&L", () => {
    render(<PositionsTable positions={[position]} onSelect={vi.fn()} />);
    expect(screen.getByText("+$100.00")).toHaveClass("text-up");
    expect(screen.getByText("+10.00%")).toBeInTheDocument();
  });

  it("renders header totals and connection state", () => {
    render(
      <Header
        portfolio={{ cash_balance: 500, positions_value: 1100, total_value: 1600, unrealized_pnl: 100, positions: [position] }}
        status="reconnecting"
      />,
    );
    expect(screen.getByTestId("total-value")).toHaveTextContent("$1,600.00");
    expect(screen.getByTestId("connection-status")).toHaveTextContent("Reconnecting");
  });

  it("colors heatmap tiles by P&L", () => {
    render(<Heatmap positions={[position, { ...position, ticker: "TSLA", pnl_percent: -3 }]} onSelect={vi.fn()} />);
    expect(screen.getByTestId("tile-AAPL").style.background).toContain("63, 182, 139");
    expect(screen.getByTestId("tile-TSLA").style.background).toContain("229, 83, 75");
    expect(pnlColor(0)).toContain("123 136 152");
  });
});

describe("ChatPanel", () => {
  it("shows loading, then the reply with inline actions", async () => {
    const user = userEvent.setup();
    let resolve!: (reply: ChatReply) => void;
    const onSend = vi.fn(() => new Promise<ChatReply>((r) => (resolve = r)));
    render(<ChatPanel open onToggle={vi.fn()} onSend={onSend} />);
    await user.type(screen.getByLabelText("Chat message"), "buy 2 AAPL");
    await user.click(screen.getByRole("button", { name: "Send" }));
    expect(screen.getByTestId("chat-loading")).toBeInTheDocument();
    act(() =>
      resolve({
        message: "Done.",
        actions: {
          trades: [{ ticker: "AAPL", side: "buy", quantity: 2, status: "ok", price: 190 }],
          watchlist_changes: [{ ticker: "PYPL", action: "add", status: "ok" }],
        },
        portfolio: { cash_balance: 0, positions_value: 0, total_value: 0, unrealized_pnl: 0, positions: [] },
      }),
    );
    await waitFor(() => expect(screen.queryByTestId("chat-loading")).not.toBeInTheDocument());
    expect(screen.getByText("Done.")).toBeInTheDocument();
    expect(screen.getByText("Bought 2 AAPL at $190.00")).toBeInTheDocument();
    expect(screen.getByText("Added PYPL to watchlist")).toBeInTheDocument();
  });
});

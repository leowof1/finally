"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { ChatPanel } from "@/components/ChatPanel";
import { Header } from "@/components/Header";
import { Heatmap } from "@/components/Heatmap";
import { PositionsTable } from "@/components/PositionsTable";
import { TimeChart } from "@/components/TimeChart";
import { TradeBar } from "@/components/TradeBar";
import { Watchlist } from "@/components/Watchlist";
import { api } from "@/lib/api";
import { money } from "@/lib/format";
import { livePortfolio } from "@/lib/portfolio";
import type { Portfolio, PricePoint } from "@/lib/types";
import { usePrices } from "@/lib/usePrices";

function Panel({ title, children, className = "" }: { title: string; children: React.ReactNode; className?: string }) {
  return (
    <section aria-label={title} className={`flex min-h-0 flex-col border border-line bg-panel ${className}`}>
      <h2 className="px-3 pt-2 text-sm font-semibold text-muted">{title}</h2>
      <div className="min-h-0 flex-1">{children}</div>
    </section>
  );
}

export default function Home() {
  const { prices, history, sessionOpen, status } = usePrices();
  const [tickers, setTickers] = useState<string[]>([]);
  const [selected, setSelected] = useState("AAPL");
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [snapshots, setSnapshots] = useState<PricePoint[]>([]);
  const [chatOpen, setChatOpen] = useState(true);

  const refreshWatchlist = useCallback(async () => {
    const entries = await api.watchlist();
    setTickers(entries.map((e) => e.ticker));
  }, []);

  const refreshPortfolio = useCallback(async (next?: Portfolio) => {
    setPortfolio(next ?? (await api.portfolio()));
    const rows = await api.history();
    setSnapshots(
      rows.map((r) => ({ time: Math.floor(Date.parse(r.recorded_at) / 1000), value: r.total_value }))
        .filter((p, i, all) => i === all.length - 1 || p.time !== all[i + 1].time),
    );
  }, []);

  useEffect(() => {
    refreshWatchlist();
    refreshPortfolio();
    const timer = setInterval(() => refreshPortfolio(), 30_000);
    return () => clearInterval(timer);
  }, [refreshWatchlist, refreshPortfolio]);

  const live = useMemo(() => (portfolio ? livePortfolio(portfolio, prices) : null), [portfolio, prices]);

  async function trade(ticker: string, quantity: number, side: "buy" | "sell") {
    const result = await api.trade(ticker, quantity, side);
    await refreshPortfolio(result.portfolio);
  }

  async function addTicker(ticker: string) {
    await api.addTicker(ticker);
    await refreshWatchlist();
    setSelected(ticker);
  }

  async function removeTicker(ticker: string) {
    await api.removeTicker(ticker);
    await refreshWatchlist();
  }

  async function sendChat(message: string) {
    const reply = await api.chat(message);
    await Promise.all([refreshWatchlist(), refreshPortfolio(reply.portfolio)]);
    return reply;
  }

  const selectedPrice = prices[selected]?.price;

  return (
    <div className="flex h-screen flex-col">
      <Header portfolio={live} status={status} />
      <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
        <aside className="flex max-h-80 min-h-0 flex-col border-r border-line bg-panel lg:max-h-none lg:w-72">
          <Watchlist
            tickers={tickers}
            prices={prices}
            history={history}
            sessionOpen={sessionOpen}
            selected={selected}
            onSelect={setSelected}
            onAdd={addTicker}
            onRemove={removeTicker}
          />
        </aside>
        <main className="grid min-h-0 flex-1 grid-rows-[minmax(16rem,1.3fr)_auto_minmax(12rem,1fr)_auto] gap-2 overflow-y-auto p-2">
          <section aria-label="Price chart" className="flex min-h-0 flex-col border border-line bg-panel">
            <div className="flex items-baseline gap-3 px-3 pt-2">
              <h2 className="text-xl font-semibold" data-testid="chart-ticker">{selected}</h2>
              <span className="text-lg">{selectedPrice ? money(selectedPrice) : "--"}</span>
            </div>
            <div className="min-h-0 flex-1">
              <TimeChart points={history[selected] ?? []} color="#209dd7" label={`${selected} price chart`} />
            </div>
          </section>
          <div className="border border-line bg-panel">
            <TradeBar ticker={selected} onTrade={trade} />
          </div>
          <div className="grid min-h-0 grid-cols-1 gap-2 md:grid-cols-2">
            <Panel title="Holdings heatmap">
              <div className="h-full p-2">
                <Heatmap positions={live?.positions ?? []} onSelect={setSelected} />
              </div>
            </Panel>
            <Panel title="Portfolio value">
              <div className="h-full" data-testid="pnl-chart" data-points={snapshots.length}>
                {snapshots.length ? (
                  <TimeChart points={snapshots} color="#ecad0a" label="Portfolio value over time" />
                ) : (
                  <p className="p-3 text-sm text-muted">Value is recorded every 30 seconds and after each trade.</p>
                )}
              </div>
            </Panel>
          </div>
          <Panel title="Positions">
            <PositionsTable positions={live?.positions ?? []} onSelect={setSelected} />
          </Panel>
        </main>
        <ChatPanel open={chatOpen} onToggle={() => setChatOpen((o) => !o)} onSend={sendChat} />
      </div>
    </div>
  );
}

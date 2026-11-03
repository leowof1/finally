"use client";
import { useMemo, useState } from "react";
import { useAppData } from "@/hooks/useAppData";
import { usePriceStream } from "@/hooks/usePriceStream";
import { revalue } from "@/utils/portfolio";
import { ChatPanel } from "./ChatPanel";
import { Header } from "./Header";
import { Heatmap } from "./Heatmap";
import { Panel } from "./Panel";
import { PositionsTable } from "./PositionsTable";
import { TimeChart } from "./TimeChart";
import { TradeBar } from "./TradeBar";
import { Watchlist } from "./Watchlist";

/** Full trading workstation layout. */
export function Dashboard() {
  const stream = usePriceStream();
  const data = useAppData();
  const [picked, setPicked] = useState<string | null>(null);
  const selected = picked ?? data.watchlist[0]?.ticker ?? null;

  const livePortfolio = useMemo(() => {
    if (!data.portfolio) return null;
    const prices = Object.fromEntries(Object.values(stream.prices).map((u) => [u.ticker, u.price]));
    return revalue(data.portfolio, prices);
  }, [data.portfolio, stream.prices]);

  const pnlPoints = useMemo(
    () => data.history.map((s) => ({ time: Date.parse(s.recorded_at) / 1000, value: s.total_value })),
    [data.history],
  );

  return (
    <div className="flex h-screen flex-col">
      <Header
        totalValue={livePortfolio?.total_value ?? null}
        cash={livePortfolio?.cash_balance ?? null}
        pnl={livePortfolio?.unrealized_pnl ?? 0}
        status={stream.status}
      />
      <div className="flex min-h-0 flex-1">
        <main className="grid min-h-0 flex-1 grid-cols-[320px_1fr] grid-rows-[3fr_2fr_auto] gap-1 p-1">
          <div className="row-span-2 min-h-0">
            <Watchlist
              items={data.watchlist}
              stream={stream}
              selected={selected}
              onSelect={setPicked}
              onAdd={data.addTicker}
              onRemove={(t) => data.removeTicker(t).catch(console.error)}
            />
          </div>
          <Panel title={selected ? `${selected} - Live` : "Chart"}>
            <TimeChart points={selected ? (stream.history[selected] ?? []) : []} color="#209dd7" />
          </Panel>
          <div className="grid min-h-0 grid-cols-[1fr_1fr_1.4fr] gap-1">
            <Panel title="Portfolio Heatmap">
              <Heatmap positions={livePortfolio?.positions ?? []} />
            </Panel>
            <Panel title="Portfolio Value">
              <TimeChart points={pnlPoints} color="#ecad0a" testId="pnl-chart" />
            </Panel>
            <Panel title="Positions">
              <PositionsTable positions={livePortfolio?.positions ?? []} />
            </Panel>
          </div>
          <div className="col-span-2">
            <TradeBar defaultTicker={selected} onTrade={data.trade} />
          </div>
        </main>
        <ChatPanel messages={data.messages} loading={data.chatLoading} onSend={data.sendChat} />
      </div>
    </div>
  );
}

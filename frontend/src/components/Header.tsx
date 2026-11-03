import { formatUsd, signClass } from "@/utils/format";
import type { ConnectionStatus } from "@/utils/types";

const DOT: Record<ConnectionStatus, string> = {
  connected: "bg-up",
  reconnecting: "bg-accent",
  disconnected: "bg-down",
};

interface Props {
  totalValue: number | null;
  cash: number | null;
  pnl: number;
  status: ConnectionStatus;
}

function Stat({ label, value, testId, cls = "" }: { label: string; value: string; testId?: string; cls?: string }) {
  return (
    <div className="flex flex-col items-end leading-tight">
      <span className="text-[10px] uppercase text-muted">{label}</span>
      <span data-testid={testId} className={`text-sm font-bold tabular-nums ${cls}`}>
        {value}
      </span>
    </div>
  );
}

/** Top bar: brand, portfolio value, cash, P&L, connection dot. */
export function Header({ totalValue, cash, pnl, status }: Props) {
  return (
    <header className="flex items-center justify-between border-b border-border bg-panel px-3 py-1.5">
      <div className="flex items-baseline gap-2">
        <span className="text-lg font-bold text-accent">FinAlly</span>
        <span className="text-muted">AI Trading Workstation</span>
      </div>
      <div className="flex items-center gap-6">
        <Stat label="Total Value" testId="total-value" value={totalValue == null ? "--" : formatUsd(totalValue)} />
        <Stat label="Cash" testId="cash-balance" value={cash == null ? "--" : formatUsd(cash)} />
        <Stat label="Unreal. P&L" value={formatUsd(pnl)} cls={signClass(pnl)} />
        <div className="flex items-center gap-1.5" title={status}>
          <span
            data-testid="connection-status"
            data-status={status}
            className={`inline-block h-2.5 w-2.5 rounded-full ${DOT[status]}`}
          />
          <span className="text-[10px] uppercase text-muted">{status}</span>
        </div>
      </div>
    </header>
  );
}

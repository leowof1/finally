import { money, signedMoney, toneClass } from "@/lib/format";
import type { ConnectionStatus, Portfolio } from "@/lib/types";

const statusStyle: Record<ConnectionStatus, { color: string; label: string }> = {
  connected: { color: "bg-up", label: "Live" },
  reconnecting: { color: "bg-accent", label: "Reconnecting" },
  disconnected: { color: "bg-down", label: "Disconnected" },
};

interface Props {
  portfolio: Portfolio | null;
  status: ConnectionStatus;
}

export function Header({ portfolio, status }: Props) {
  const conn = statusStyle[status];
  return (
    <header className="flex flex-wrap items-end gap-x-8 gap-y-1 border-b border-line bg-panel px-4 py-2">
      <h1 className="text-lg font-bold">
        Fin<span className="text-primary">Ally</span>
      </h1>
      <div className="flex flex-col leading-none">
        <span className="text-xs text-muted">Portfolio value</span>
        <span className="text-3xl font-semibold text-accent" data-testid="total-value">
          {portfolio ? money(portfolio.total_value) : "--"}
        </span>
      </div>
      <div className="flex flex-col leading-tight">
        <span className="text-xs text-muted">Cash</span>
        <span data-testid="cash-balance">{portfolio ? money(portfolio.cash_balance) : "--"}</span>
      </div>
      <div className="flex flex-col leading-tight">
        <span className="text-xs text-muted">Unrealized P&amp;L</span>
        <span className={portfolio ? toneClass(portfolio.unrealized_pnl) : ""}>
          {portfolio ? signedMoney(portfolio.unrealized_pnl) : "--"}
        </span>
      </div>
      <div className="ml-auto flex items-center gap-2 text-sm text-muted" data-testid="connection-status" data-status={status}>
        <span className={`h-2.5 w-2.5 rounded-full ${conn.color}`} aria-hidden="true" />
        {conn.label}
      </div>
    </header>
  );
}

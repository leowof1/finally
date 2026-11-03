import type { ReactNode } from "react";

/** Titled bordered box used for every dashboard section. */
export function Panel({
  title,
  right,
  children,
  className = "",
}: {
  title: string;
  right?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`flex min-h-0 flex-col border border-border bg-panel ${className}`}>
      <header className="flex items-center justify-between border-b border-border px-2 py-1">
        <h2 className="text-[11px] font-semibold uppercase tracking-wider text-accent">{title}</h2>
        {right}
      </header>
      <div className="min-h-0 flex-1 overflow-auto">{children}</div>
    </section>
  );
}

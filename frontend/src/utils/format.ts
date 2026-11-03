/** Number formatting helpers. */

const usd = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

export const formatUsd = (n: number) => usd.format(n);

export const formatPrice = (n: number | null | undefined) =>
  n == null ? "--" : n.toFixed(2);

export const formatPercent = (n: number) =>
  `${n >= 0 ? "+" : ""}${n.toFixed(2)}%`;

export const formatQty = (n: number) =>
  Number.isInteger(n) ? String(n) : n.toFixed(4).replace(/0+$/, "");

/** Tailwind text color class for a signed value. */
export const signClass = (n: number) =>
  n > 0 ? "text-up" : n < 0 ? "text-down" : "text-muted";

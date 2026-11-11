const usd = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });

export const money = (value: number) => usd.format(value);

export const signedMoney = (value: number) => (value >= 0 ? "+" : "-") + usd.format(Math.abs(value));

export const percent = (value: number) => `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;

export const quantity = (value: number) =>
  value.toLocaleString("en-US", { maximumFractionDigits: 4 });

export const toneClass = (value: number) =>
  value > 0 ? "text-up" : value < 0 ? "text-down" : "text-muted";

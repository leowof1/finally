import type { PricePoint } from "@/lib/types";

interface Props {
  points: PricePoint[];
  width?: number;
  height?: number;
}

/** Tiny SVG line of prices accumulated since page load. */
export function Sparkline({ points, width = 72, height = 22 }: Props) {
  if (points.length < 2) {
    return <svg width={width} height={height} aria-hidden="true" />;
  }
  const values = points.map((p) => p.value);
  const min = Math.min(...values);
  const range = Math.max(...values) - min || 1;
  const step = width / (points.length - 1);
  const path = values
    .map((v, i) => `${(i * step).toFixed(1)},${(height - ((v - min) / range) * (height - 2) - 1).toFixed(1)}`)
    .join(" ");
  const rising = values[values.length - 1] >= values[0];
  return (
    <svg width={width} height={height} aria-hidden="true">
      <polyline
        points={path}
        fill="none"
        stroke={rising ? "var(--color-up)" : "var(--color-down)"}
        strokeWidth="1.25"
      />
    </svg>
  );
}

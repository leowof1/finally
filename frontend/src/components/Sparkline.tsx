import type { PricePoint } from "@/hooks/usePriceStream";

const W = 80;
const H = 20;

/** Tiny SVG line of recent prices. */
export function Sparkline({ points }: { points: PricePoint[] }) {
  if (points.length < 2) return <svg width={W} height={H} />;
  const values = points.map((p) => p.value);
  const min = Math.min(...values);
  const range = Math.max(...values) - min || 1;
  const path = values
    .map((v, i) => `${(i / (values.length - 1)) * W},${H - ((v - min) / range) * H}`)
    .join(" ");
  const up = values.at(-1)! >= values[0];
  return (
    <svg width={W} height={H} className="overflow-visible">
      <polyline
        points={path}
        fill="none"
        strokeWidth={1.2}
        stroke={up ? "var(--color-up)" : "var(--color-down)"}
      />
    </svg>
  );
}

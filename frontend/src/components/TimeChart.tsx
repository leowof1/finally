"use client";
import { useEffect, useRef } from "react";
import {
  AreaSeries,
  ColorType,
  createChart,
  type IChartApi,
  type ISeriesApi,
  type UTCTimestamp,
} from "lightweight-charts";
import type { PricePoint } from "@/hooks/usePriceStream";

interface Props {
  points: PricePoint[];
  color: string;
  testId?: string;
}

/** Keep strictly ascending times (last value wins), as Lightweight Charts requires. */
export function toSeries(points: PricePoint[]) {
  const out: { time: UTCTimestamp; value: number }[] = [];
  for (const p of points) {
    const time = Math.floor(p.time) as UTCTimestamp;
    if (out.length && out.at(-1)!.time >= time) out[out.length - 1] = { time: out.at(-1)!.time, value: p.value };
    else out.push({ time, value: p.value });
  }
  return out;
}

/** Canvas area chart (Lightweight Charts) for time/value points in Unix seconds. */
export function TimeChart({ points, color, testId }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const chart = useRef<IChartApi | null>(null);
  const series = useRef<ISeriesApi<"Area"> | null>(null);

  useEffect(() => {
    const c = createChart(container.current!, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: "#8b949e",
        fontSize: 10,
        attributionLogo: false,
      },
      grid: { vertLines: { color: "#21262d" }, horzLines: { color: "#21262d" } },
      rightPriceScale: { borderColor: "#30363d" },
      timeScale: { borderColor: "#30363d", timeVisible: true, secondsVisible: true },
    });
    chart.current = c;
    series.current = c.addSeries(AreaSeries, {
      lineColor: color,
      topColor: `${color}55`,
      bottomColor: `${color}05`,
      lineWidth: 2,
    });
    return () => c.remove();
  }, [color]);

  useEffect(() => {
    series.current?.setData(toSeries(points));
    chart.current?.timeScale().fitContent();
  }, [points, color]);

  return <div ref={container} data-testid={testId} className="h-full w-full" />;
}

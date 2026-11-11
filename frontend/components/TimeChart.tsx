"use client";

import { AreaSeries, createChart, type IChartApi, type ISeriesApi, type UTCTimestamp } from "lightweight-charts";
import { useEffect, useRef } from "react";
import type { PricePoint } from "@/lib/types";

interface Props {
  points: PricePoint[];
  color: string;
  label: string;
}

/** Canvas area chart (lightweight-charts) that follows the latest data. */
export function TimeChart({ points, color, label }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const chart = useRef<IChartApi | null>(null);
  const series = useRef<ISeriesApi<"Area"> | null>(null);

  useEffect(() => {
    const instance = createChart(container.current!, {
      autoSize: true,
      layout: {
        background: { color: "transparent" },
        textColor: "#7b8898",
        fontFamily: "inherit",
        attributionLogo: false,
      },
      grid: { vertLines: { color: "#1a2330" }, horzLines: { color: "#1a2330" } },
      rightPriceScale: { borderColor: "#263241" },
      timeScale: { borderColor: "#263241", timeVisible: true, secondsVisible: true },
      crosshair: { horzLine: { labelBackgroundColor: "#263241" }, vertLine: { labelBackgroundColor: "#263241" } },
    });
    chart.current = instance;
    series.current = instance.addSeries(AreaSeries, {
      lineColor: color,
      topColor: `${color}55`,
      bottomColor: `${color}00`,
      lineWidth: 2,
    });
    return () => instance.remove();
  }, [color]);

  useEffect(() => {
    series.current?.setData(points.map((p) => ({ time: p.time as UTCTimestamp, value: p.value })));
    chart.current?.timeScale().fitContent();
  }, [points]);

  return <div ref={container} role="img" aria-label={label} className="h-full w-full" />;
}

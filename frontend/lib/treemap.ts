export interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface TreemapItem<T> {
  item: T;
  rect: Rect;
}

/** Squarified treemap layout in a unit-free box; values must be positive. */
export function squarify<T>(items: T[], value: (item: T) => number, box: Rect): TreemapItem<T>[] {
  const sorted = [...items].filter((i) => value(i) > 0).sort((a, b) => value(b) - value(a));
  const total = sorted.reduce((sum, i) => sum + value(i), 0);
  if (!total) return [];
  const scale = (box.w * box.h) / total;
  const result: TreemapItem<T>[] = [];
  let remaining = sorted;
  let free = { ...box };

  while (remaining.length) {
    const short = Math.min(free.w, free.h);
    let row: T[] = [];
    let best = Infinity;
    for (const item of remaining) {
      const candidate = [...row, item];
      const ratio = worstRatio(candidate.map((i) => value(i) * scale), short);
      if (ratio > best) break;
      best = ratio;
      row = candidate;
    }
    free = layoutRow(row, value, scale, free, result);
    remaining = remaining.slice(row.length);
  }
  return result;
}

function worstRatio(areas: number[], side: number): number {
  const sum = areas.reduce((a, b) => a + b, 0);
  const max = Math.max(...areas);
  const min = Math.min(...areas);
  return Math.max((side * side * max) / (sum * sum), (sum * sum) / (side * side * min));
}

function layoutRow<T>(row: T[], value: (item: T) => number, scale: number, free: Rect, out: TreemapItem<T>[]): Rect {
  const area = row.reduce((sum, i) => sum + value(i) * scale, 0);
  const horizontal = free.w >= free.h;
  const thickness = area / (horizontal ? free.h : free.w);
  let offset = 0;
  for (const item of row) {
    const length = (value(item) * scale) / thickness;
    out.push({
      item,
      rect: horizontal
        ? { x: free.x, y: free.y + offset, w: thickness, h: length }
        : { x: free.x + offset, y: free.y, w: length, h: thickness },
    });
    offset += length;
  }
  return horizontal
    ? { x: free.x + thickness, y: free.y, w: free.w - thickness, h: free.h }
    : { x: free.x, y: free.y + thickness, w: free.w, h: free.h - thickness };
}

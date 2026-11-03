"use client";
import { useEffect, useRef, useState } from "react";

const HOLD_MS = 150;

/** Returns a CSS class that briefly flashes when `value` goes up or down. */
export function useFlash(value: number | null | undefined) {
  const prev = useRef(value);
  const [flash, setFlash] = useState("");

  useEffect(() => {
    const old = prev.current;
    prev.current = value;
    if (old == null || value == null || old === value) return;
    setFlash(value > old ? "flash-up" : "flash-down");
    const id = setTimeout(() => setFlash(""), HOLD_MS);
    return () => clearTimeout(id);
  }, [value]);

  return `flash-cell ${flash}`;
}

"use client";

import { useEffect, useRef, useState } from "react";

/** Returns a flash class for ~500ms after the value moves up or down. */
export function useFlash(value: number | undefined): string {
  const previous = useRef(value);
  const [flash, setFlash] = useState("");

  useEffect(() => {
    const before = previous.current;
    previous.current = value;
    if (value === undefined || before === undefined || value === before) return;
    setFlash(value > before ? "flash-up" : "flash-down");
    const timer = setTimeout(() => setFlash(""), 120);
    return () => clearTimeout(timer);
  }, [value]);

  return `flash-cell ${flash}`;
}

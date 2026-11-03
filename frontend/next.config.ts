import type { NextConfig } from "next";
import { PHASE_DEVELOPMENT_SERVER } from "next/constants";

const API_ORIGIN = process.env.API_ORIGIN ?? "http://localhost:8000";

const baseConfig: NextConfig = {
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

/** Static export for production; dev server proxies /api/* to the backend. */
export default function config(phase: string): NextConfig {
  if (phase === PHASE_DEVELOPMENT_SERVER) {
    return {
      ...baseConfig,
      compress: false, // gzip buffers the proxied SSE stream
      rewrites: async () => [
        { source: "/api/:path*", destination: `${API_ORIGIN}/api/:path*` },
      ],
    };
  }
  return { ...baseConfig, output: "export" };
}

import type { NextConfig } from "next";
import { PHASE_DEVELOPMENT_SERVER, PHASE_PRODUCTION_BUILD } from "next/constants";

// Backend address for the /api proxy. Rewrites are resolved when `next build` runs,
// so set PRIVACYTWIN_API_URL at build time (e.g. http://backend:8000 in Docker).
// Only `next dev` falls back to a local backend.
export default function config(phase: string): NextConfig {
  const apiUrl =
    process.env.PRIVACYTWIN_API_URL ||
    (phase === PHASE_DEVELOPMENT_SERVER ? "http://localhost:8000" : "");
  if (!apiUrl && phase === PHASE_PRODUCTION_BUILD) {
    throw new Error(
      "PRIVACYTWIN_API_URL is required for a production build (e.g. http://backend:8000).",
    );
  }
  return {
    poweredByHeader: false,
    async rewrites() {
      // At `next start` the rewrites already built into .next are used.
      if (!apiUrl) return [];
      return [
        {
          source: "/api/:path*",
          destination: `${apiUrl.replace(/\/$/, "")}/api/:path*`,
        },
      ];
    },
  };
}

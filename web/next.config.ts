import type { NextConfig } from "next";

// Static export: the frontend is plain files (deployable to Vercel or any static host).
// The API URL is baked in at build time via NEXT_PUBLIC_API_URL.
const config: NextConfig = {
  output: "export",
  trailingSlash: true,
  poweredByHeader: false,
  reactStrictMode: true,
  images: { unoptimized: true },
};

export default config;

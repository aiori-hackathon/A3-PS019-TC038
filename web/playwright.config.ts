import { defineConfig } from "@playwright/test";

// Expects the API on :8000 and the static site on :3000 (see README "Run the smoke test").
// CI uses Playwright's Chromium; locally set PW_CHANNEL=msedge to use an installed Edge.
export default defineConfig({
  testDir: "./tests",
  timeout: 90_000,
  expect: { timeout: 20_000 },
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"]],
  use: {
    baseURL: process.env.PT_WEB_URL || "http://127.0.0.1:3000",
    channel: process.env.PW_CHANNEL || undefined,
    viewport: { width: 1440, height: 900 },
    acceptDownloads: true,
    colorScheme: "dark",
  },
});

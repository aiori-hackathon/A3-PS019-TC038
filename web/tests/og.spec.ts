import { test } from "@playwright/test";
// PT_SCREENSHOTS=1 npx playwright test og  -> regenerates public/og.png (1200x630)
test.skip(!process.env.PT_SCREENSHOTS, "set PT_SCREENSHOTS=1");
test("og image", async ({ page }) => {
  await page.setViewportSize({ width: 1200, height: 630 });
  await page.goto("/");
  await page.addStyleTag({ content: ".site-nav{display:none} .hero{padding-top:64px !important}" });
  await page.waitForTimeout(1500);
  await page.screenshot({ path: "public/og.png" });
});

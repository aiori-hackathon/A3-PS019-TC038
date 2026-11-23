import { test } from "@playwright/test";

// Captures README screenshots: PT_SCREENSHOTS=1 npx playwright test screenshots
test.skip(!process.env.PT_SCREENSHOTS, "set PT_SCREENSHOTS=1 to capture screenshots");

const OUT = "../docs/screenshots";

test("capture key pages", async ({ page }) => {
  test.setTimeout(240_000);
  await page.goto("/");
  await page.evaluate(() => { localStorage.clear(); localStorage.setItem("pt.tourSeen", "1"); });
  await page.waitForTimeout(1200);
  await page.screenshot({ path: `${OUT}/01-landing.png` });
  await page.goto("/app/overview/?demo=1");
  await page.getByRole("button", { name: /PII candidates:/ }).waitFor({ timeout: 60_000 });
  await page.waitForTimeout(1500);
  await page.screenshot({ path: `${OUT}/02-overview.png`, fullPage: true });
  const shots: [string, string, number?][] = [
    ["/app/inventory/", "03-inventory.png"],
    ["/app/review/", "05-review.png"],
    ["/app/metadata/", "06-metadata.png"],
    ["/app/time-machine/", "07-time-machine.png"],
    ["/app/simulator/?tab=blast", "08-simulator.png"],
    ["/app/simulator/?tab=lineage", "09-lineage.png"],
    ["/app/evaluation/", "10-evaluation.png"],
    ["/app/rules/", "11-rules.png"],
    ["/app/evidence/", "12-evidence.png"],
    ["/app/audit/", "13-audit.png"],
  ];
  for (const [path, file] of shots) {
    await page.goto(path);
    await page.waitForTimeout(2200);
    await page.screenshot({ path: `${OUT}/${file}` });
  }
  await page.goto("/app/inventory/?f=PT-00004");
  await page.waitForTimeout(2000);
  await page.screenshot({ path: `${OUT}/04-evidence-card.png` });
  await page.emulateMedia({ colorScheme: "light" });
  await page.evaluate(() => { document.documentElement.dataset.theme = "light"; });
  await page.goto("/app/overview/");
  await page.evaluate(() => { document.documentElement.dataset.theme = "light"; });
  await page.waitForTimeout(1500);
  await page.screenshot({ path: `${OUT}/14-overview-light.png` });
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto("/app/overview/");
  await page.evaluate(() => { document.documentElement.dataset.theme = "dark"; });
  await page.waitForTimeout(1500);
  await page.screenshot({ path: `${OUT}/15-mobile.png` });
});

import { expect, test } from "@playwright/test";

const FOOTER = "Technical evidence for human review. Not a legal determination.";

test("demo → keyboard review → undo → export → verify", async ({ page }) => {
  // fresh browser workspace
  await page.goto("/");
  await page.evaluate(() => localStorage.clear());
  await page.reload();
  // the root opens the tool directly
  await expect(page.getByRole("button", { name: "Load sample company" })).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText(FOOTER)).toBeVisible();

  const t0 = Date.now();
  await page.getByRole("button", { name: "Load sample company" }).click();
  await expect(page.getByRole("button", { name: /PII candidates:/ })).toBeVisible({ timeout: 30_000 });
  const elapsed = (Date.now() - t0) / 1000;
  console.log(`demo populated in ${elapsed.toFixed(1)}s`);
  expect(elapsed).toBeLessThan(10);
  await expect(page.getByText(FOOTER)).toBeVisible();
  // AI analyst is visible on the overview
  await expect(page.locator(".ai-badge").filter({ hasText: "AI ANALYST" })).toBeVisible();
  await expect(page.getByText(/Highest exposure:/)).toBeVisible();

  // keyboard-only review
  await page.keyboard.press("g");
  await page.keyboard.press("r");
  await expect(page).toHaveURL(/\/app\/review\//);
  const first = page.locator('[role="option"][aria-selected="true"] code').first();
  await expect(first).toBeVisible();
  await page.keyboard.press("j");
  await page.keyboard.press("k");
  await page.keyboard.press("c");
  await expect(page.locator(".toast").filter({ hasText: "confirmed" }).first()).toBeVisible();
  // reject needs a note: R focuses the note field, type, Enter submits
  await page.keyboard.press("r");
  await expect(page.getByPlaceholder("Why? (goes into the audit log)")).toBeFocused();
  await page.keyboard.type("Synthetic test value");
  await page.keyboard.press("Enter");
  await expect(page.locator(".toast").filter({ hasText: "rejected" }).first()).toBeVisible();
  // undo with Z (no confirmation dialog)
  await page.locator("body").click({ position: { x: 5, y: 300 } });
  await page.keyboard.press("z");
  await expect(page.locator(".toast").filter({ hasText: "Undone" }).first()).toBeVisible();

  // audit chain verifies
  await page.goto("/app/audit/");
  await page.getByRole("button", { name: "Verify integrity" }).click();
  await expect(page.getByText(/Chain intact/)).toBeVisible();

  // export and verify the evidence pack
  await page.goto("/app/evidence/");
  const [dl] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: "Export evidence pack" }).click()]);
  const path = await dl.path();
  expect(dl.suggestedFilename()).toMatch(/privacytwin-evidence-.*\.zip/);
  await page.locator('input[type="file"][accept=".zip"]').setInputFiles(path!);
  await expect(page.getByText("Pack verified: every file matches its manifest hash")).toBeVisible();
  await expect(page.getByText(FOOTER)).toBeVisible();
});

test("every page shows the legal footer and works at 375px", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 800 });
  for (const path of ["/", "/security/", "/docs/", "/evaluation/", "/faq/", "/app/overview/", "/app/inventory/", "/app/time-machine/"]) {
    await page.goto(path);
    await expect(page.getByText(FOOTER).first()).toBeVisible();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow, `horizontal scroll on ${path}`).toBeLessThanOrEqual(1);
  }
});

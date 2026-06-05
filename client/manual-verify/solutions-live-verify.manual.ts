/**
 * MANUAL verification harness — NOT part of CI.
 *
 * Lives in `manual-verify/` (outside Playwright's `testDir: ./e2e`) and is named
 * `.manual.ts` (not `.spec.ts`), so `./test.sh client e2e` never collects it.
 * It logs in with the debug-stack dev credentials and assumes the operator has
 * a port-mode debug stack running — neither holds on a clean CI test stack.
 *
 * Run it explicitly against a live debug stack (uses playwright.manual.config.ts,
 * whose testDir is manual-verify/):
 *   cd client && TEST_BASE_URL=http://localhost:<port> \
 *     npx playwright test -c playwright.manual.config.ts
 */
import { test, expect } from "@playwright/test";

const SHOTS = "test-results/solutions-live";

test("real login flow works", async ({ page }) => {
  await page.goto("/login");
  await page.fill("#email", "dev@gobifrost.com");
  await page.fill("#password", "password");
  await page.screenshot({ path: `${SHOTS}/00-login.png` });
  await page.click('button[type="submit"]');
  // After login we should leave /login and land in the authenticated app.
  await page.waitForURL((url) => !url.pathname.startsWith("/login"), {
    timeout: 20000,
  });
  await page.waitForLoadState("networkidle");
  await page.screenshot({ path: `${SHOTS}/01-dashboard.png`, fullPage: true });
  expect(page.url()).not.toContain("/login");
});

test("authenticated surfaces render (apps, workflows)", async ({ page }) => {
  // Log in first (each test gets a fresh context in the unauth project).
  await page.goto("/login");
  await page.fill("#email", "dev@gobifrost.com");
  await page.fill("#password", "password");
  await page.click('button[type="submit"]');
  await page.waitForURL((url) => !url.pathname.startsWith("/login"), {
    timeout: 20000,
  });

  await page.goto("/apps");
  await page.waitForLoadState("networkidle");
  await page.screenshot({ path: `${SHOTS}/02-apps-list.png`, fullPage: true });
  await expect(page.locator("body")).toBeVisible();

  await page.goto("/workflows");
  await page.waitForLoadState("networkidle");
  await page.screenshot({ path: `${SHOTS}/03-workflows.png`, fullPage: true });
  await expect(page.locator("body")).toBeVisible();
});

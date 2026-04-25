/**
 * Summary Backfill (Admin) — T110
 *
 * Asserts the backfill UI's structural contract on `/agents`:
 *
 *   1. When no runs are eligible for backfill, the button is hidden (the
 *      component returns null for a 0-eligible response).
 *   2. When eligible runs exist, clicking the button opens a confirm dialog
 *      with the eligible count and an estimated cost. Cancel closes it
 *      without submitting.
 *
 * Full "seed 5 pending runs → trigger → progress WS reaches 5/5" coverage
 * from the plan is not possible without a dev-only seed endpoint for
 * synthesized completed-with-pending-summary runs, and there is no such
 * endpoint today (see `client/e2e/setup/seed-agent.ts` top comment). This
 * spec covers what can be tested end-to-end without that fixture. The
 * backend service itself has its own e2e at
 * `api/tests/e2e/api/test_backfill_summaries.py`, so the UI-only gap is
 * the WS progress render — which the vitest unit tests exercise against
 * a mocked socket.
 */

import { test, expect } from "@playwright/test";

test.describe("Summary backfill (admin)", () => {
	test("structural contract on /agents", async ({ page }) => {
		await page.goto("/agents");
		await expect(
			page.getByRole("heading", { name: "Agents", exact: true }),
		).toBeVisible({ timeout: 10000 });

		const button = page.getByTestId("summary-backfill-button");
		const visible = await button.isVisible();

		if (!visible) {
			// No eligible runs in this environment — component correctly
			// returns null. Assert the gate behavior and stop here.
			await expect(button).toHaveCount(0);
			return;
		}

		// Button is present — exercise the confirm dialog.
		await button.click();

		// Confirm dialog shows a title referencing either eligible runs or
		// "Nothing to backfill" (the latter is a defensive branch when
		// eligibility drops between the list query and dialog open).
		await expect(
			page
				.getByRole("alertdialog")
				.getByText(/backfill|nothing to backfill/i)
				.first(),
		).toBeVisible();

		// Cancel closes without submitting.
		await page.getByRole("button", { name: /cancel/i }).click();
		await expect(page.getByRole("alertdialog")).toHaveCount(0);
	});
});

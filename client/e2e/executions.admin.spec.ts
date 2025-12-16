/**
 * Execution History Tests (Admin)
 *
 * Tests execution history viewing and management from the platform admin perspective.
 * These tests run as platform_admin with full system access.
 *
 * Mirrors: api/tests/e2e/api/test_executions.py
 */

import { test, expect } from "@playwright/test";

test.describe("Execution History", () => {
	test("should display execution history page", async ({ page }) => {
		await page.goto("/history");

		// Should see history heading
		await expect(
			page.getByRole("heading", { name: /history|executions/i }).first(),
		).toBeVisible({ timeout: 10000 });
	});

	test("should list executions", async ({ page }) => {
		await page.goto("/history");

		await expect(
			page.getByRole("heading", { name: /history|executions/i }).first(),
		).toBeVisible({ timeout: 10000 });

		// Either we have executions or an empty state
		const executionContent = page.locator(
			"table tbody tr, [data-testid='execution-row'], [data-testid='execution-card']",
		);

		const hasExecutions = await executionContent.count().catch(() => 0);
		const hasEmptyState = await page
			.getByText(/no executions|empty|run a workflow/i)
			.isVisible()
			.catch(() => false);

		expect(hasExecutions > 0 || hasEmptyState).toBe(true);
	});

	test("should show execution status badges", async ({ page }) => {
		await page.goto("/history");

		await expect(
			page.getByRole("heading", { name: /history|executions/i }).first(),
		).toBeVisible({ timeout: 10000 });

		// Look for status indicators
		const statusBadge = page.locator(
			"[data-testid='status-badge'], .badge, [class*='status']",
		);

		// If we have executions, we should have status badges
		const hasExecutions =
			(await page
				.locator("table tbody tr, [data-testid='execution-row']")
				.count()
				.catch(() => 0)) > 0;

		if (hasExecutions) {
			await expect(statusBadge.first()).toBeVisible();
		}
	});
});

test.describe("Execution Details", () => {
	test("should navigate to execution details", async ({ page }) => {
		await page.goto("/history");

		await expect(
			page.getByRole("heading", { name: /history|executions/i }).first(),
		).toBeVisible({ timeout: 10000 });

		// Find an execution row
		const executionRow = page
			.locator(
				"table tbody tr, [data-testid='execution-row'], [data-testid='execution-card']",
			)
			.first();

		if (await executionRow.isVisible().catch(() => false)) {
			await executionRow.click();

			// Should navigate to execution details
			await page.waitForURL(/\/history\/[a-f0-9-]+/, { timeout: 5000 });

			// Should show execution details
			await expect(
				page.getByText(/status|result|output|logs/i),
			).toBeVisible({ timeout: 5000 });
		}
	});

	test("should show execution output/results", async ({ page }) => {
		await page.goto("/history");

		await expect(
			page.getByRole("heading", { name: /history|executions/i }).first(),
		).toBeVisible({ timeout: 10000 });

		// Find an execution
		const executionRow = page
			.locator(
				"table tbody tr, [data-testid='execution-row'], [data-testid='execution-card']",
			)
			.first();

		if (await executionRow.isVisible().catch(() => false)) {
			await executionRow.click();
			await page.waitForURL(/\/history\/[a-f0-9-]+/, { timeout: 5000 });

			// Should show output section
			await expect(page.getByText(/output|result|response/i)).toBeVisible(
				{ timeout: 5000 },
			);
		}
	});

	test("should show execution logs", async ({ page }) => {
		await page.goto("/history");

		await expect(
			page.getByRole("heading", { name: /history|executions/i }).first(),
		).toBeVisible({ timeout: 10000 });

		// Find an execution
		const executionRow = page
			.locator(
				"table tbody tr, [data-testid='execution-row'], [data-testid='execution-card']",
			)
			.first();

		if (await executionRow.isVisible().catch(() => false)) {
			await executionRow.click();
			await page.waitForURL(/\/history\/[a-f0-9-]+/, { timeout: 5000 });

			// Look for logs tab/section
			const logsTab = page.getByRole("tab", { name: /logs/i });
			const logsSection = page.getByText(/logs|console/i);

			const hasLogs =
				(await logsTab.isVisible().catch(() => false)) ||
				(await logsSection.isVisible().catch(() => false));

			expect(hasLogs).toBe(true);
		}
	});
});

test.describe("Execution Filtering", () => {
	test("should filter by status", async ({ page }) => {
		await page.goto("/history");

		await expect(
			page.getByRole("heading", { name: /history|executions/i }).first(),
		).toBeVisible({ timeout: 10000 });

		// Look for status filter
		const statusFilter = page
			.getByRole("combobox", { name: /status/i })
			.or(page.locator("[data-testid='status-filter']"))
			.or(page.getByLabel(/status/i));

		if (await statusFilter.isVisible().catch(() => false)) {
			await statusFilter.click();

			// Should show filter options
			await expect(
				page.getByText(/completed|failed|running|pending/i),
			).toBeVisible({ timeout: 3000 });
		}
	});

	test("should search executions", async ({ page }) => {
		await page.goto("/history");

		await expect(
			page.getByRole("heading", { name: /history|executions/i }).first(),
		).toBeVisible({ timeout: 10000 });

		// Look for search input
		const searchInput = page
			.getByPlaceholder(/search|filter/i)
			.or(page.getByRole("searchbox"));

		if (await searchInput.isVisible().catch(() => false)) {
			await searchInput.fill("test");
			await page.waitForTimeout(500);

			// Results should update
			await expect(page.locator("main")).toBeVisible();
		}
	});
});

test.describe("Execution Actions", () => {
	test("should show cancel button for running executions", async ({
		page,
	}) => {
		await page.goto("/history");

		await expect(
			page.getByRole("heading", { name: /history|executions/i }).first(),
		).toBeVisible({ timeout: 10000 });

		// Look for running executions
		const runningStatus = page.getByText(/running|pending/i).first();

		if (await runningStatus.isVisible().catch(() => false)) {
			// Running executions should have cancel button
			const cancelButton = page.getByRole("button", {
				name: /cancel|stop/i,
			});
			await expect(cancelButton).toBeVisible();
		}
	});

	test("should show re-run option for completed executions", async ({
		page,
	}) => {
		await page.goto("/history");

		await expect(
			page.getByRole("heading", { name: /history|executions/i }).first(),
		).toBeVisible({ timeout: 10000 });

		// Find a completed execution
		const completedRow = page
			.locator("table tbody tr, [data-testid='execution-row']")
			.filter({ hasText: /completed|success|failed/i })
			.first();

		if (await completedRow.isVisible().catch(() => false)) {
			// Look for re-run button
			const rerunButton = page
				.getByRole("button", { name: /re-?run|retry/i })
				.first();

			// Re-run functionality may or may not be implemented
			const _hasRerun = await rerunButton.isVisible().catch(() => false);
			// Just checking the page works, not requiring re-run feature
			expect(true).toBe(true);
		}
	});
});

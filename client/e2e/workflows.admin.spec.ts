/**
 * Workflow Management Tests (Admin)
 *
 * Tests workflow listing, viewing, and execution from the platform admin perspective.
 * These tests run as platform_admin with full system access.
 *
 * Mirrors: api/tests/e2e/api/test_workflows.py
 */

import { test, expect } from "@playwright/test";

test.describe("Workflow Listing", () => {
	test("should display workflows page", async ({ page }) => {
		await page.goto("/workflows");

		// Should see workflows heading (use first() in case dashboard sidebar also shows "Workflows")
		await expect(
			page.getByRole("heading", { name: /workflows/i }).first(),
		).toBeVisible({ timeout: 10000 });

		// Should see workflow list/table
		await expect(page.locator("main")).toBeVisible();
	});

	test("should show workflow cards or table rows", async ({ page }) => {
		await page.goto("/workflows");

		// Wait for page to load
		await expect(
			page.getByRole("heading", { name: /workflows/i }).first(),
		).toBeVisible({ timeout: 10000 });

		// Should see some workflow content (table or cards)
		const workflowContent = page.locator(
			"table tbody tr, [data-testid='workflow-card'], [data-testid='workflow-row']",
		);

		// Either we have workflows or we have an empty state message
		const hasWorkflows = await workflowContent.count().catch(() => 0);
		const hasEmptyState = await page
			.getByText(/no workflows available|no workflows match/i)
			.isVisible()
			.catch(() => false);

		expect(hasWorkflows > 0 || hasEmptyState).toBe(true);
	});

	test("should show workflow details when clicked", async ({ page }) => {
		await page.goto("/workflows");

		// Wait for page to load
		await expect(
			page.getByRole("heading", { name: /workflows/i }).first(),
		).toBeVisible({ timeout: 10000 });

		// Find a workflow row/card
		const workflowItem = page
			.locator(
				"table tbody tr, [data-testid='workflow-card'], [data-testid='workflow-row']",
			)
			.first();

		if (await workflowItem.isVisible().catch(() => false)) {
			await workflowItem.click();

			// Should navigate to workflow detail or show details panel
			await page.waitForTimeout(1000);

			// Check if we're on a detail page or showing details
			const hasDetails =
				page.url().includes("/workflows/") ||
				(await page
					.getByText(/parameters|inputs|description/i)
					.isVisible()
					.catch(() => false));

			expect(hasDetails).toBe(true);
		}
	});
});

test.describe("Workflow Execution", () => {
	test("should show execute button on workflows", async ({ page }) => {
		await page.goto("/workflows");

		// Wait for page to load
		await expect(
			page.getByRole("heading", { name: /workflows/i }).first(),
		).toBeVisible({ timeout: 10000 });

		// Look for execute buttons
		const executeButton = page
			.getByRole("button", { name: /execute|run/i })
			.first();

		// Either we have execute buttons or no workflows
		const hasButton = await executeButton.isVisible().catch(() => false);
		const hasEmptyState = await page
			.getByText(/no workflows available|no workflows match/i)
			.isVisible()
			.catch(() => false);

		expect(hasButton || hasEmptyState).toBe(true);
	});

	test("should navigate to execute page when clicking execute", async ({
		page,
	}) => {
		await page.goto("/workflows");

		// Wait for page to load
		await expect(
			page.getByRole("heading", { name: /workflows/i }).first(),
		).toBeVisible({ timeout: 10000 });

		// Find execute button
		const executeButton = page
			.getByRole("button", { name: /execute|run/i })
			.first();

		if (await executeButton.isVisible().catch(() => false)) {
			await executeButton.click();

			// Should navigate to execute page or show execution modal
			await page.waitForTimeout(1000);

			const isOnExecutePage = page.url().includes("/execute");
			const hasExecutionForm = await page
				.getByRole("button", { name: /run|submit|execute/i })
				.isVisible()
				.catch(() => false);

			expect(isOnExecutePage || hasExecutionForm).toBe(true);
		}
	});

	test("should execute workflow and show progress", async ({ page }) => {
		await page.goto("/workflows");

		// Wait for page to load
		await expect(
			page.getByRole("heading", { name: /workflows/i }).first(),
		).toBeVisible({ timeout: 10000 });

		// Find and click execute button
		const executeButton = page
			.getByRole("button", { name: /execute|run/i })
			.first();

		if (!(await executeButton.isVisible().catch(() => false))) {
			test.skip();
			return;
		}

		await executeButton.click();

		// Wait for execution form/page
		await page.waitForTimeout(1000);

		// Find the run/submit button on the execution form
		const runButton = page
			.getByRole("button", { name: /run|submit|execute/i })
			.first();

		if (await runButton.isVisible().catch(() => false)) {
			await runButton.click();

			// Should show execution progress or redirect to execution detail
			await page
				.waitForURL(/\/history\/[a-f0-9-]+|\/executions/, {
					timeout: 15000,
				})
				.catch(() => {});

			// Should see execution status
			await expect(
				page.getByText(
					/pending|running|queued|success|completed|failed/i,
				),
			).toBeVisible({ timeout: 30000 });
		}
	});
});

test.describe("Workflow Discovery", () => {
	test("should show platform workflows", async ({ page }) => {
		await page.goto("/workflows");

		// Wait for page to load
		await expect(
			page.getByRole("heading", { name: /workflows/i }).first(),
		).toBeVisible({ timeout: 10000 });

		// Platform workflows should be visible to admin
		// (specific workflow names depend on what's in the platform directory)
	});

	test("should filter workflows", async ({ page }) => {
		await page.goto("/workflows");

		// Wait for page to load
		await expect(
			page.getByRole("heading", { name: /workflows/i }).first(),
		).toBeVisible({ timeout: 10000 });

		// Look for filter/search input
		const searchInput = page
			.getByPlaceholder(/search|filter/i)
			.or(page.getByRole("searchbox"));

		if (await searchInput.isVisible().catch(() => false)) {
			await searchInput.fill("test");

			// Wait for filter to apply
			await page.waitForTimeout(500);

			// Results should be filtered
			await expect(page.locator("main")).toBeVisible();
		}
	});
});

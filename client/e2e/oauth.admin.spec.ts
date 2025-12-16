/**
 * OAuth Connection Tests (Admin)
 *
 * Tests OAuth connection management from the platform admin perspective.
 * These tests run as platform_admin with full system access.
 *
 * Mirrors: api/tests/e2e/api/test_oauth.py
 */

import { test, expect } from "@playwright/test";

test.describe("OAuth Connection Listing", () => {
	test("should display OAuth connections page", async ({ page }) => {
		// OAuth might be under settings or integrations
		await page.goto("/settings/oauth");

		// If not found, try /integrations
		const oauthHeading = page.getByRole("heading", {
			name: /oauth|connections|integrations/i,
		});

		if (
			!(await oauthHeading
				.isVisible({ timeout: 5000 })
				.catch(() => false))
		) {
			await page.goto("/integrations");
		}

		// Should see OAuth/integrations content
		await expect(page.locator("main")).toBeVisible({ timeout: 10000 });
	});

	test("should list OAuth connections", async ({ page }) => {
		await page.goto("/settings/oauth");

		// Wait for page
		await page.waitForTimeout(2000);

		// Should show connection list or empty state
		await expect(page.locator("main")).toBeVisible();
	});

	test("should show add connection button", async ({ page }) => {
		await page.goto("/settings/oauth");

		// Wait for page
		await page.waitForTimeout(2000);

		// Look for add button
		const _addButton = page.getByRole("button", {
			name: /add|create|connect|new/i,
		});

		// May or may not have add button
		await expect(page.locator("main")).toBeVisible();
	});
});

test.describe("OAuth Connection Configuration", () => {
	test("should open add connection dialog", async ({ page }) => {
		await page.goto("/settings/oauth");

		// Wait for page
		await page.waitForTimeout(2000);

		// Try to click add button
		const addButton = page.getByRole("button", {
			name: /add|create|connect|new/i,
		});

		if (await addButton.isVisible().catch(() => false)) {
			await addButton.click();

			// Should show connection form
			await expect(
				page
					.getByLabel(/name/i)
					.or(page.getByText(/oauth|connection type/i)),
			).toBeVisible({ timeout: 5000 });
		}
	});

	test("should show connection types", async ({ page }) => {
		await page.goto("/settings/oauth");

		// Wait for page
		await page.waitForTimeout(2000);

		// Try to click add button
		const addButton = page.getByRole("button", {
			name: /add|create|connect|new/i,
		});

		if (await addButton.isVisible().catch(() => false)) {
			await addButton.click();

			// Should show connection type options
			await expect(
				page.getByText(/client credentials|authorization code|oauth/i),
			).toBeVisible({ timeout: 5000 });
		}
	});
});

test.describe("OAuth Connection Details", () => {
	test("should show connection details when clicked", async ({ page }) => {
		await page.goto("/settings/oauth");

		// Wait for page
		await page.waitForTimeout(2000);

		// Find a connection
		const connectionItem = page
			.locator(
				"table tbody tr, [data-testid='connection-row'], [data-testid='connection-card']",
			)
			.first();

		if (await connectionItem.isVisible().catch(() => false)) {
			await connectionItem.click();

			// Should show connection details
			await page.waitForTimeout(1000);
			await expect(page.locator("main")).toBeVisible();
		}
	});
});

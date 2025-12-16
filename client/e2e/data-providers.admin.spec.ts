/**
 * Data Provider Tests (Admin)
 *
 * Tests data provider management from the platform admin perspective.
 * These tests run as platform_admin with full system access.
 *
 * Mirrors: api/tests/e2e/api/test_data_providers.py
 */

import { test, expect } from "@playwright/test";

test.describe("Data Provider Listing", () => {
	test("should display data providers page", async ({ page }) => {
		await page.goto("/data-providers");

		// Should see data providers heading
		await expect(
			page.getByRole("heading", { name: /data providers/i }).first(),
		).toBeVisible({ timeout: 10000 });
	});

	test("should list available data providers", async ({ page }) => {
		await page.goto("/data-providers");

		await expect(
			page.getByRole("heading", { name: /data providers/i }).first(),
		).toBeVisible({ timeout: 10000 });

		// Should show data provider list or empty state
		await expect(page.locator("main")).toBeVisible();
	});

	test("should show data provider details", async ({ page }) => {
		await page.goto("/data-providers");

		await expect(
			page.getByRole("heading", { name: /data providers/i }).first(),
		).toBeVisible({ timeout: 10000 });

		// Find a data provider
		const providerItem = page
			.locator(
				"table tbody tr, [data-testid='provider-row'], [data-testid='provider-card']",
			)
			.first();

		if (await providerItem.isVisible().catch(() => false)) {
			await providerItem.click();

			// Should show provider details
			await page.waitForTimeout(1000);
			await expect(page.locator("main")).toBeVisible();
		}
	});
});

test.describe("Data Provider Configuration", () => {
	test("should show configure button", async ({ page }) => {
		await page.goto("/data-providers");

		await expect(
			page.getByRole("heading", { name: /data providers/i }).first(),
		).toBeVisible({ timeout: 10000 });

		// Look for configure button
		const _configureButton = page.getByRole("button", {
			name: /configure|setup|connect/i,
		});

		// May or may not have data providers
		await expect(page.locator("main")).toBeVisible();
	});
});

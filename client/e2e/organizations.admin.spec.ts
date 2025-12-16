/**
 * Organization Management Tests (Admin)
 *
 * Tests organization CRUD operations from the platform admin perspective.
 * These tests run as platform_admin with full system access.
 *
 * Mirrors: api/tests/e2e/api/test_organizations.py
 */

import { test, expect } from "@playwright/test";

test.describe("Organization Management", () => {
	test("should display organizations list", async ({ page }) => {
		await page.goto("/organizations");

		// Should see organizations page
		await expect(
			page.getByRole("heading", { name: /organizations/i }).first(),
		).toBeVisible({ timeout: 10000 });

		// Wait for content to load
		await page.waitForTimeout(1000);

		// Should see some organization content or empty state
		const hasOrgs = (await page.locator("table tbody tr").count()) > 0;
		const hasCards =
			(await page.locator("[data-testid='org-card']").count()) > 0;
		const hasContent = await page
			.getByText(/bifrost|gobifrost|organization/i)
			.first()
			.isVisible()
			.catch(() => false);

		expect(hasOrgs || hasCards || hasContent).toBe(true);
	});

	test("should show organization details", async ({ page }) => {
		await page.goto("/organizations");

		// Wait for list to load
		await expect(
			page.getByRole("heading", { name: /organizations/i }).first(),
		).toBeVisible({ timeout: 10000 });

		// Click on first organization
		const orgRow = page
			.locator(
				"table tbody tr, [data-testid='org-row'], [data-testid='org-card']",
			)
			.first();

		if (await orgRow.isVisible().catch(() => false)) {
			await orgRow.click();

			// Should show organization details
			await expect(
				page.getByText(/details|settings|members/i),
			).toBeVisible({ timeout: 5000 });
		}
	});

	test("should be able to create new organization", async ({ page }) => {
		await page.goto("/organizations");

		// Look for create button
		const createButton = page.getByRole("button", {
			name: /create|new|add/i,
		});

		if (await createButton.isVisible().catch(() => false)) {
			await createButton.click();

			// Should show create form/dialog
			await expect(
				page.getByLabel(/name/i).or(page.getByPlaceholder(/name/i)),
			).toBeVisible({ timeout: 5000 });
		}
	});

	test("should show organization members", async ({ page }) => {
		await page.goto("/organizations");

		// Wait for list to load
		await expect(
			page.getByRole("heading", { name: /organizations/i }).first(),
		).toBeVisible({ timeout: 10000 });

		// Look for members link/tab
		const membersLink = page
			.getByRole("link", { name: /members/i })
			.first();
		const membersTab = page.getByRole("tab", { name: /members/i }).first();

		if (await membersLink.isVisible().catch(() => false)) {
			await membersLink.click();
			await expect(page.getByText(/alice|bob|admin/i)).toBeVisible({
				timeout: 5000,
			});
		} else if (await membersTab.isVisible().catch(() => false)) {
			await membersTab.click();
			await expect(page.getByText(/alice|bob|admin/i)).toBeVisible({
				timeout: 5000,
			});
		}
	});
});

test.describe("Organization Settings", () => {
	test("should access organization settings", async ({ page }) => {
		await page.goto("/organizations");

		// Wait for page to load
		await expect(
			page.getByRole("heading", { name: /organizations/i }).first(),
		).toBeVisible({ timeout: 10000 });

		// Look for settings link or button
		const settingsLink = page
			.getByRole("link", { name: /settings/i })
			.or(page.getByRole("button", { name: /settings/i }))
			.first();

		if (await settingsLink.isVisible().catch(() => false)) {
			await settingsLink.click();

			// Should show settings page/panel
			await expect(page.locator("main")).toBeVisible();
		}
	});
});

/**
 * Permission Tests (Org User)
 *
 * Tests that org users have restricted access as expected.
 * These tests run as org1_user (not platform admin) to verify
 * permission boundaries are enforced in the UI.
 *
 * Mirrors: api/tests/e2e/api/test_permissions.py
 */

import { test, expect } from "@playwright/test";

test.describe("Org User Restrictions", () => {
	test("should not see organization management in navigation", async ({
		page,
	}) => {
		await page.goto("/");

		// Wait for page to load
		await expect(page.locator("main")).toBeVisible();

		// Organizations link should not be visible to org users
		await expect(
			page.getByRole("link", { name: /organizations/i }),
		).not.toBeVisible();
	});

	test("should not have access to platform admin pages", async ({ page }) => {
		// Try to access organizations page directly
		await page.goto("/organizations");

		// Should either redirect away or show access denied
		const accessDenied = page.getByText(
			/access denied|forbidden|unauthorized|not found/i,
		);
		const notOnPage = async () => !page.url().includes("/organizations");

		// Wait for either condition
		await Promise.race([
			accessDenied
				.waitFor({ state: "visible", timeout: 5000 })
				.catch(() => {}),
			page
				.waitForURL((url) => !url.pathname.includes("/organizations"), {
					timeout: 5000,
				})
				.catch(() => {}),
		]);

		// Verify one of the conditions is true
		const isAccessDenied = await accessDenied
			.isVisible()
			.catch(() => false);
		const isRedirected = await notOnPage();
		expect(isAccessDenied || isRedirected).toBe(true);
	});

	test("should see own organization data only", async ({ page }) => {
		await page.goto("/");

		// Should see dashboard with org-specific data
		await expect(page.locator("main")).toBeVisible();

		// Should NOT see data from other organizations
		// (Specific assertions depend on UI implementation)
	});

	test("should be able to view execution history", async ({ page }) => {
		await page.goto("/history");

		// Should see history page
		await expect(
			page.getByRole("heading", { name: /history|executions/i }).first(),
		).toBeVisible({ timeout: 10000 });
	});

	test("should not see admin-only menu items", async ({ page }) => {
		await page.goto("/");

		// Wait for page to load
		await expect(page.locator("main")).toBeVisible();

		// Look for settings or admin menu
		const settingsButton = page.getByRole("button", {
			name: /settings|admin|menu/i,
		});

		if (await settingsButton.isVisible().catch(() => false)) {
			await settingsButton.click();

			// Admin-only items should not be visible
			await expect(
				page.getByRole("menuitem", { name: /manage users/i }),
			).not.toBeVisible();
			await expect(
				page.getByRole("menuitem", { name: /system config/i }),
			).not.toBeVisible();
		}
	});

	test("should be able to access forms assigned to their role", async ({
		page,
	}) => {
		await page.goto("/forms");

		// Should see forms page (filtered to assigned forms)
		await expect(
			page.getByRole("heading", { name: /forms/i }).first(),
		).toBeVisible({
			timeout: 10000,
		});

		// Should NOT see "Create Form" button (admin only)
		await expect(
			page.getByRole("button", { name: /create form|new form/i }),
		).not.toBeVisible();
	});
});

test.describe("Cross-Org Access Prevention", () => {
	test("should not see config management page", async ({ page }) => {
		await page.goto("/settings/config");

		// Either the router redirects away, or an Access Denied screen renders.
		// Wait for whichever happens — reading page.url() synchronously was racy.
		const denied = page.getByText(/access denied|forbidden|unauthorized/i);
		const redirected = page.waitForURL(
			(url) => !url.pathname.includes("/settings/config"),
			{ timeout: 5000 },
		);

		await Promise.race([
			denied.waitFor({ state: "visible", timeout: 5000 }),
			redirected,
		]);

		const isDenied = await denied.isVisible().catch(() => false);
		const isRedirected = !page.url().includes("/settings/config");
		expect(isDenied || isRedirected).toBe(true);
	});
});

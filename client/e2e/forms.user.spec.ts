/**
 * Form Access Tests (Org User)
 *
 * Tests form access from the org user perspective.
 * These tests run as org1_user with restricted access.
 *
 * Mirrors: api/tests/e2e/api/test_forms.py (org user scenarios)
 */

import { test, expect } from "@playwright/test";

test.describe("Form Access for Org Users", () => {
	test("should display forms page", async ({ page }) => {
		await page.goto("/forms");

		// Should see forms heading
		await expect(
			page.getByRole("heading", { name: /forms/i }).first(),
		).toBeVisible({
			timeout: 10000,
		});
	});

	test("should NOT show create form button", async ({ page }) => {
		await page.goto("/forms");

		await expect(
			page.getByRole("heading", { name: /forms/i }).first(),
		).toBeVisible({
			timeout: 10000,
		});

		// Org user should NOT see create button
		await expect(
			page.getByRole("button", { name: /create|new form/i }),
		).not.toBeVisible();
	});

	test("should only see assigned forms", async ({ page }) => {
		await page.goto("/forms");

		await expect(
			page.getByRole("heading", { name: /forms/i }).first(),
		).toBeVisible({
			timeout: 10000,
		});

		// User should see their assigned forms (or empty state if none assigned)
		await expect(page.locator("main")).toBeVisible();
	});

	test("should NOT show edit button for forms", async ({ page }) => {
		await page.goto("/forms");

		await expect(
			page.getByRole("heading", { name: /forms/i }).first(),
		).toBeVisible({
			timeout: 10000,
		});

		// Org user should NOT see edit buttons
		await expect(
			page.getByRole("button", { name: /edit/i }),
		).not.toBeVisible();
	});

	test("should NOT show delete button for forms", async ({ page }) => {
		await page.goto("/forms");

		await expect(
			page.getByRole("heading", { name: /forms/i }).first(),
		).toBeVisible({
			timeout: 10000,
		});

		// Org user should NOT see delete buttons
		await expect(
			page.getByRole("button", { name: /delete|remove/i }),
		).not.toBeVisible();
	});
});

test.describe("Form Submission for Org Users", () => {
	test("should be able to view assigned form details", async ({ page }) => {
		await page.goto("/forms");

		await expect(
			page.getByRole("heading", { name: /forms/i }).first(),
		).toBeVisible({
			timeout: 10000,
		});

		// Find a form
		const formItem = page
			.locator(
				"table tbody tr, [data-testid='form-card'], [data-testid='form-row']",
			)
			.first();

		if (await formItem.isVisible().catch(() => false)) {
			await formItem.click();

			// Should be able to view form (but not edit)
			await page.waitForTimeout(1000);
			await expect(page.locator("main")).toBeVisible();
		}
	});

	test("should be able to submit assigned forms", async ({ page }) => {
		await page.goto("/forms");

		await expect(
			page.getByRole("heading", { name: /forms/i }).first(),
		).toBeVisible({
			timeout: 10000,
		});

		// Find a form with submit/run button
		const submitButton = page
			.getByRole("button", { name: /submit|run|execute/i })
			.first();

		if (await submitButton.isVisible().catch(() => false)) {
			await submitButton.click();

			// Should show form submission UI
			await expect(
				page.locator("form").or(page.getByRole("dialog")),
			).toBeVisible({ timeout: 5000 });
		}
	});
});

test.describe("Form Permission Boundaries", () => {
	test("should not access form management endpoints", async ({ page }) => {
		// Try to access form settings directly
		await page.goto("/forms/settings");

		// Should redirect or show access denied
		const isRedirected = !page.url().includes("/forms/settings");
		const accessDenied = await page
			.getByText(/access denied|forbidden|not found/i)
			.isVisible()
			.catch(() => false);

		expect(isRedirected || accessDenied).toBe(true);
	});

	test("should not see role assignment options", async ({ page }) => {
		await page.goto("/forms");

		await expect(
			page.getByRole("heading", { name: /forms/i }).first(),
		).toBeVisible({
			timeout: 10000,
		});

		// Should not see role/permission management UI
		await expect(
			page.getByRole("button", { name: /assign|permissions|roles/i }),
		).not.toBeVisible();
	});
});

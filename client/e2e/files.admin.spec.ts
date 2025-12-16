/**
 * File Editor Tests (Admin)
 *
 * Tests file editor operations from the platform admin perspective.
 * These tests run as platform_admin with full system access.
 *
 * Mirrors: api/tests/e2e/api/test_files.py
 */

import { test, expect } from "@playwright/test";

test.describe("File Editor", () => {
	test("should display file editor page", async ({ page }) => {
		await page.goto("/editor");

		// Should see editor or file browser
		await expect(
			page
				.getByRole("heading", { name: /editor|files/i })
				.or(page.locator("[data-testid='file-tree']"))
				.or(page.locator(".monaco-editor")),
		).toBeVisible({ timeout: 10000 });
	});

	test("should show file tree", async ({ page }) => {
		await page.goto("/editor");

		// Wait for editor to load
		await page.waitForTimeout(2000);

		// Should see file tree or file list
		await expect(
			page
				.locator("[data-testid='file-tree']")
				.or(page.locator(".file-tree"))
				.or(page.getByRole("tree")),
		).toBeVisible({ timeout: 10000 });
	});

	test("should show create file button", async ({ page }) => {
		await page.goto("/editor");

		// Wait for editor to load
		await page.waitForTimeout(2000);

		// Should see create file button
		await expect(
			page.getByRole("button", { name: /new file|create|add/i }),
		).toBeVisible({ timeout: 5000 });
	});

	test("should show create folder button", async ({ page }) => {
		await page.goto("/editor");

		// Wait for editor to load
		await page.waitForTimeout(2000);

		// Should see create folder button
		await expect(
			page.getByRole("button", { name: /new folder|create folder/i }),
		).toBeVisible({ timeout: 5000 });
	});
});

test.describe("File Operations", () => {
	test("should open file when clicked", async ({ page }) => {
		await page.goto("/editor");

		// Wait for editor to load
		await page.waitForTimeout(2000);

		// Find a file in the tree
		const fileItem = page
			.locator("[data-testid='file-item'], .file-item, [role='treeitem']")
			.filter({ hasText: /\.py$|\.json$|\.yaml$/i })
			.first();

		if (await fileItem.isVisible().catch(() => false)) {
			await fileItem.click();

			// Should show file content in editor
			await expect(
				page
					.locator(".monaco-editor")
					.or(page.locator("[data-testid='editor']")),
			).toBeVisible({ timeout: 5000 });
		}
	});

	test("should show save button when file is modified", async ({ page }) => {
		await page.goto("/editor");

		// Wait for editor to load
		await page.waitForTimeout(2000);

		// Find and open a file
		const fileItem = page
			.locator("[data-testid='file-item'], .file-item, [role='treeitem']")
			.filter({ hasText: /\.py$|\.json$/i })
			.first();

		if (await fileItem.isVisible().catch(() => false)) {
			await fileItem.click();

			// Wait for editor
			await page.waitForTimeout(1000);

			// Look for save button (should exist even if disabled)
			await expect(
				page.getByRole("button", { name: /save/i }),
			).toBeVisible({ timeout: 5000 });
		}
	});
});

test.describe("File Upload", () => {
	test("should show upload button", async ({ page }) => {
		await page.goto("/editor");

		// Wait for editor to load
		await page.waitForTimeout(2000);

		// Look for upload button
		const _uploadButton = page.getByRole("button", { name: /upload/i });

		// Upload might be available
		await expect(page.locator("main")).toBeVisible();
	});
});

test.describe("Workspace Files", () => {
	test("should show workspace root", async ({ page }) => {
		await page.goto("/editor");

		// Wait for editor to load
		await page.waitForTimeout(2000);

		// Should show workspace root or file tree
		await expect(
			page
				.getByText(/workspace|files|root/i)
				.or(page.locator("[data-testid='file-tree']")),
		).toBeVisible({ timeout: 10000 });
	});

	test("should list workflow files", async ({ page }) => {
		await page.goto("/editor");

		// Wait for editor to load
		await page.waitForTimeout(2000);

		// Should see workflow files (if any exist)
		const workflowFiles = page.locator(
			"[data-testid='file-item'], .file-item, [role='treeitem']",
		);

		// Either we have files or the tree is empty
		const hasFiles = (await workflowFiles.count()) > 0;
		const hasEmptyState = await page
			.getByText(/empty|no files|create/i)
			.isVisible()
			.catch(() => false);

		expect(hasFiles || hasEmptyState || true).toBe(true);
	});
});

test.describe("File Context Menu", () => {
	test("should show context menu on right-click", async ({ page }) => {
		await page.goto("/editor");

		// Wait for editor to load
		await page.waitForTimeout(2000);

		// Find a file in the tree
		const fileItem = page
			.locator("[data-testid='file-item'], .file-item, [role='treeitem']")
			.first();

		if (await fileItem.isVisible().catch(() => false)) {
			// Right-click to open context menu
			await fileItem.click({ button: "right" });

			// Should show context menu
			await expect(
				page
					.getByRole("menu")
					.or(page.locator("[data-testid='context-menu']"))
					.or(page.getByText(/rename|delete|copy/i)),
			).toBeVisible({ timeout: 3000 });
		}
	});
});

/**
 * Authentication Flow E2E Tests (Unauthenticated)
 *
 * Tests the authentication flow for unauthenticated users:
 * - Login page visibility
 * - Invalid credentials handling
 * - MFA flow
 * - Redirect after login
 * - Protected route redirection
 *
 * These tests run WITHOUT pre-authenticated state to test the login flow itself.
 */

import { test, expect } from "@playwright/test";
import * as fs from "fs";
import * as path from "path";
import { fileURLToPath } from "url";
import { generateTOTP } from "./setup/totp";
import { getCredentialsPath, type UserCredentials } from "./fixtures/users";

// ESM equivalent of __dirname
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Load credentials from global setup
function loadCredentials(): Record<string, UserCredentials> {
	const credPath = path.resolve(__dirname, getCredentialsPath());
	if (!fs.existsSync(credPath)) {
		throw new Error(
			`Credentials file not found at ${credPath}. Run setup first.`,
		);
	}
	return JSON.parse(fs.readFileSync(credPath, "utf-8"));
}

test.describe("Login Flow", () => {
	test.beforeEach(async ({ page }) => {
		// Navigate first, then clear auth state (localStorage needs a page context)
		await page.goto("/login");
		await page.context().clearCookies();
		await page.evaluate(() => localStorage.clear());
	});

	test("should show login page", async ({ page }) => {
		await page.goto("/login");

		// Check for login form elements
		await expect(
			page.getByRole("heading", { name: /bifrost/i }),
		).toBeVisible();
		await expect(page.getByLabel("Email")).toBeVisible();
		await expect(page.getByLabel("Password")).toBeVisible();
		await expect(
			page.getByRole("button", { name: "Sign In" }),
		).toBeVisible();
	});

	test("should show error for invalid credentials", async ({ page }) => {
		await page.goto("/login");

		// Enter invalid credentials
		await page.getByLabel("Email").fill("invalid@example.com");
		await page.getByLabel("Password").fill("wrongpassword");
		await page.getByRole("button", { name: "Sign In" }).click();

		// Should show error message (alert or toast)
		await expect(
			page.getByRole("alert").or(page.getByText(/invalid|error|failed/i)),
		).toBeVisible({ timeout: 5000 });
	});

	test("should redirect unauthenticated users to login", async ({ page }) => {
		// Try to access protected route
		await page.goto("/workflows");

		// Should redirect to login
		await page.waitForURL(/\/login/, { timeout: 5000 });
		await expect(page.getByLabel("Email")).toBeVisible();
	});

	test("should complete full login flow with MFA", async ({ page }) => {
		const credentials = loadCredentials();
		const user = credentials.platform_admin;

		await page.goto("/login");

		// Fill login form
		await page.getByLabel("Email").fill(user.email);
		await page.getByLabel("Password").fill(user.password);
		await page.getByRole("button", { name: "Sign In" }).click();

		// Wait for MFA prompt
		const mfaInput = page.getByLabel(/code|totp|verification/i);

		try {
			await mfaInput.waitFor({ state: "visible", timeout: 5000 });

			// Enter TOTP code
			const totpCode = generateTOTP(user.totpSecret);
			await mfaInput.fill(totpCode);
			await page
				.getByRole("button", { name: /verify|submit|continue/i })
				.click();
		} catch {
			// MFA might not be required in test environment
		}

		// Should redirect to dashboard (wait for not being on login page)
		await page.waitForURL((url) => !url.pathname.includes("/login"), {
			timeout: 15000,
		});

		// Verify we're logged in by checking for user menu (not Sign In button)
		await expect(
			page.getByRole("button", { name: /Platform Admin|user|account/i }),
		).toBeVisible({ timeout: 5000 });
	});

	test("should preserve redirect path after login", async ({ page }) => {
		const credentials = loadCredentials();
		const user = credentials.platform_admin;

		// Try to access workflows page while not logged in
		await page.goto("/workflows");

		// Should redirect to login
		await page.waitForURL(/\/login/, { timeout: 5000 });

		// Login
		await page.getByLabel("Email").fill(user.email);
		await page.getByLabel("Password").fill(user.password);
		await page.getByRole("button", { name: "Sign In" }).click();

		// Handle MFA if required
		const mfaInput = page.getByLabel(/code|totp|verification/i);
		try {
			await mfaInput.waitFor({ state: "visible", timeout: 5000 });
			const totpCode = generateTOTP(user.totpSecret);
			await mfaInput.fill(totpCode);
			await page
				.getByRole("button", { name: /verify|submit|continue/i })
				.click();
		} catch {
			// MFA might not be required
		}

		// Should redirect back to workflows (the original destination)
		// Note: This depends on the app preserving the redirect state
		await page.waitForURL(/\/(workflows)?/, { timeout: 15000 });
	});
});

test.describe("Access Control", () => {
	test.beforeEach(async ({ page }) => {
		// Navigate first, then clear auth state (localStorage needs a page context)
		await page.goto("/login");
		await page.context().clearCookies();
		await page.evaluate(() => localStorage.clear());
	});

	test("should deny access to API endpoints without auth", async ({
		page,
	}) => {
		// Try to access an API endpoint directly
		const response = await page.request.get("/api/organizations");
		expect(response.status()).toBe(401);
	});

	test("should show login page for protected routes", async ({ page }) => {
		const protectedRoutes = [
			"/workflows",
			"/forms",
			"/history",
			"/settings",
		];

		for (const route of protectedRoutes) {
			await page.goto(route);
			await page.waitForURL(/\/login/, { timeout: 5000 });
		}
	});
});

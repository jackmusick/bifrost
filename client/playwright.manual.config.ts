/**
 * Playwright config for the MANUAL Solutions verification harnesses in
 * `manual-verify/`. These drive a live, port-mode debug stack with debug
 * credentials + manually-deployed fixtures — they are NOT part of CI (the
 * default `playwright.config.ts` has `testDir: ./e2e` and never sees them).
 *
 * Run against a running debug stack:
 *   cd client && TEST_BASE_URL=http://localhost:<port> \
 *     npx playwright test -c playwright.manual.config.ts
 */
import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
	testDir: "./manual-verify",
	testMatch: /.*\.manual\.ts$/,
	fullyParallel: false,
	reporter: "line",
	use: {
		baseURL: process.env.TEST_BASE_URL || "http://localhost:3000",
		trace: "off",
	},
	projects: [
		{
			name: "manual",
			use: { ...devices["Desktop Chrome"] },
		},
	],
});

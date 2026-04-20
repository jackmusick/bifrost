/**
 * API Fixture
 *
 * Wraps Playwright's `request` context to auto-inject the CSRF token that
 * the Bifrost API requires on mutating calls. The token lives in a
 * non-HttpOnly `csrf_token` cookie set during login; we pull it out of the
 * authenticated browser context and add `X-CSRF-Token` to every POST, PUT,
 * PATCH, DELETE.
 *
 * Usage:
 *
 *   import { test, expect } from "./fixtures/api-fixture";
 *
 *   test.beforeAll(async ({ api }) => {
 *     const app = await api.post("/api/applications", { data: {...} });
 *     expect(app.ok()).toBe(true);
 *   });
 *
 * The spec file picks the auth storage state via its project (e.g.
 * `.admin.spec.ts` → platform_admin.json), so `api` is pre-authenticated.
 */

import {
	test as base,
	expect,
	type APIRequestContext,
	type APIResponse,
	type BrowserContext,
} from "@playwright/test";

type MutatingMethod = "POST" | "PUT" | "PATCH" | "DELETE";

interface RequestOptions {
	data?: unknown;
	headers?: Record<string, string>;
	params?: Record<string, string | number | boolean>;
}

/**
 * Thin wrapper around APIRequestContext that auto-injects CSRF.
 *
 * We expose the four methods the specs actually need. If you need something
 * exotic (multipart, custom timeout), fall back to the raw `request` parameter
 * on the Playwright fixture and call csrfHeader() yourself.
 */
export interface AuthedApi {
	get(url: string, options?: RequestOptions): Promise<APIResponse>;
	post(url: string, options?: RequestOptions): Promise<APIResponse>;
	put(url: string, options?: RequestOptions): Promise<APIResponse>;
	patch(url: string, options?: RequestOptions): Promise<APIResponse>;
	delete(url: string, options?: RequestOptions): Promise<APIResponse>;
	/** Raw CSRF header for when you need to build a request manually. */
	csrfHeader(): Promise<Record<string, string>>;
}

export async function csrfHeader(
	context: BrowserContext,
): Promise<Record<string, string>> {
	const cookies = await context.cookies();
	const csrf = cookies.find((c) => c.name === "csrf_token");
	return csrf ? { "X-CSRF-Token": csrf.value } : {};
}

function buildApi(
	request: APIRequestContext,
	context: BrowserContext,
): AuthedApi {
	const send = async (
		method: MutatingMethod | "GET",
		url: string,
		options: RequestOptions = {},
	) => {
		const baseHeaders =
			method === "GET" ? {} : await csrfHeader(context);
		return request.fetch(url, {
			method,
			data: options.data,
			params: options.params,
			headers: { ...baseHeaders, ...(options.headers ?? {}) },
		});
	};

	return {
		get: (url, opts) => send("GET", url, opts),
		post: (url, opts) => send("POST", url, opts),
		put: (url, opts) => send("PUT", url, opts),
		patch: (url, opts) => send("PATCH", url, opts),
		delete: (url, opts) => send("DELETE", url, opts),
		csrfHeader: () => csrfHeader(context),
	};
}

/**
 * Extended Playwright test with an `api` fixture that handles CSRF.
 *
 * The fixture creates a new browser context from the project's storageState
 * for each use, so it works in beforeAll/afterAll hooks where the `page`
 * fixture is not available.
 */
export const test = base.extend<{ api: AuthedApi }>({
	api: async ({ browser }, use, testInfo) => {
		const storageState = testInfo.project.use.storageState as
			| string
			| undefined;
		const context = await browser.newContext(
			storageState ? { storageState } : {},
		);
		// eslint-disable-next-line react-hooks/rules-of-hooks
		await use(buildApi(context.request, context));
		await context.close();
	},
});

export { expect };

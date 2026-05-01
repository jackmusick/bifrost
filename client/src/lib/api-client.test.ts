import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { authFetch } from "./api-client";
import { ACCESS_TOKEN_KEY } from "./auth-token";

/**
 * Build a mock Response with a given status and an empty body.
 */
function mockResponse(status: number): Response {
	return new Response(null, { status });
}

/**
 * Build a never-expiring access token so `ensureValidToken` short-circuits
 * without actually hitting the refresh endpoint.
 *
 * JWT shape: header.payload.signature (signature is unverified by the
 * client). The payload is `{exp: <far-future>}`.
 */
function buildFakeToken(): string {
	const farFuture = Math.floor(Date.now() / 1000) + 60 * 60 * 24 * 365;
	const header = btoa(JSON.stringify({ alg: "none", typ: "JWT" }));
	const payload = btoa(JSON.stringify({ exp: farFuture }));
	return `${header}.${payload}.sig`;
}

/**
 * Drain the microtask queue + advance fake timers so any pending setTimeout
 * for retry backoff fires. Repeated multiple times to flush
 * await-then-setTimeout chains.
 */
async function flushRetries(maxBackoffMs: number = 5000): Promise<void> {
	// Run microtasks so awaited fetch promises resolve before timers tick.
	for (let i = 0; i < 5; i++) {
		await Promise.resolve();
	}
	await vi.advanceTimersByTimeAsync(maxBackoffMs);
}

describe("authFetch transient 5xx retry", () => {
	let fetchMock: ReturnType<typeof vi.fn>;

	beforeEach(() => {
		// Seed a valid access token so ensureValidToken passes without a
		// refresh call.
		localStorage.setItem(ACCESS_TOKEN_KEY, buildFakeToken());

		fetchMock = vi.fn();
		vi.stubGlobal("fetch", fetchMock);

		// Use fake timers so the backoff sleeps don't actually delay tests.
		vi.useFakeTimers();
	});

	afterEach(() => {
		vi.useRealTimers();
		vi.unstubAllGlobals();
		localStorage.clear();
		sessionStorage.clear();
	});

	it("retries a GET that returns 503 twice then 200", async () => {
		fetchMock
			.mockResolvedValueOnce(mockResponse(503))
			.mockResolvedValueOnce(mockResponse(503))
			.mockResolvedValueOnce(mockResponse(200));

		const promise = authFetch("/api/test");
		await flushRetries();
		const response = await promise;

		expect(response.status).toBe(200);
		expect(fetchMock).toHaveBeenCalledTimes(3);
	});

	it("does not retry a POST that returns 503", async () => {
		fetchMock.mockResolvedValueOnce(mockResponse(503));

		const promise = authFetch("/api/test", { method: "POST" });
		await flushRetries();
		const response = await promise;

		expect(response.status).toBe(503);
		expect(fetchMock).toHaveBeenCalledTimes(1);
	});

	it("returns the last 503 after a PUT exhausts all retries", async () => {
		fetchMock
			.mockResolvedValueOnce(mockResponse(503))
			.mockResolvedValueOnce(mockResponse(503))
			.mockResolvedValueOnce(mockResponse(503))
			.mockResolvedValueOnce(mockResponse(503));

		const promise = authFetch("/api/test", {
			method: "PUT",
			body: JSON.stringify({ x: 1 }),
		});
		await flushRetries();
		const response = await promise;

		expect(response.status).toBe(503);
		// 1 initial attempt + 3 retries
		expect(fetchMock).toHaveBeenCalledTimes(4);
	});

	it("does not retry a GET that returns 200 immediately", async () => {
		fetchMock.mockResolvedValueOnce(mockResponse(200));

		const promise = authFetch("/api/test");
		await flushRetries();
		const response = await promise;

		expect(response.status).toBe(200);
		expect(fetchMock).toHaveBeenCalledTimes(1);
	});

	it("retries a GET through 502 then 503 then resolves to 200", async () => {
		fetchMock
			.mockResolvedValueOnce(mockResponse(502))
			.mockResolvedValueOnce(mockResponse(503))
			.mockResolvedValueOnce(mockResponse(200));

		const promise = authFetch("/api/test");
		await flushRetries();
		const response = await promise;

		expect(response.status).toBe(200);
		expect(fetchMock).toHaveBeenCalledTimes(3);
	});

	it("retries a DELETE on 504 and resolves to 204", async () => {
		fetchMock
			.mockResolvedValueOnce(mockResponse(504))
			.mockResolvedValueOnce(mockResponse(204));

		const promise = authFetch("/api/test", { method: "DELETE" });
		await flushRetries();
		const response = await promise;

		expect(response.status).toBe(204);
		expect(fetchMock).toHaveBeenCalledTimes(2);
	});

	it("does not retry a GET that returns 500 (not in TRANSIENT_5XX)", async () => {
		fetchMock.mockResolvedValueOnce(mockResponse(500));

		const promise = authFetch("/api/test");
		await flushRetries();
		const response = await promise;

		expect(response.status).toBe(500);
		expect(fetchMock).toHaveBeenCalledTimes(1);
	});

	it("retries a HEAD on 503 and resolves to 200", async () => {
		fetchMock
			.mockResolvedValueOnce(mockResponse(503))
			.mockResolvedValueOnce(mockResponse(200));

		const promise = authFetch("/api/test", { method: "HEAD" });
		await flushRetries();
		const response = await promise;

		expect(response.status).toBe(200);
		expect(fetchMock).toHaveBeenCalledTimes(2);
	});
});

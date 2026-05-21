import { beforeEach, describe, expect, it, vi } from "vitest";
import {
	EMBED_TOKEN_KEY,
	clearAuthTokens,
	consumeEmbedTokenFromHash,
} from "./auth-token";

const validJwt = "eyJhbGciOiJIUzI1NiJ9.eyJlbWJlZCI6dHJ1ZX0.signature";

describe("consumeEmbedTokenFromHash", () => {
	beforeEach(() => {
		clearAuthTokens();
		window.history.replaceState(null, "", "/");
		vi.restoreAllMocks();
	});

	it("stores iframe embed tokens that look like JWTs and strips the fragment", () => {
		vi.spyOn(window, "top", "get").mockReturnValue({} as Window);
		window.history.replaceState(null, "", `/#embed_token=${validJwt}`);

		consumeEmbedTokenFromHash();

		expect(sessionStorage.getItem(EMBED_TOKEN_KEY)).toBe(validJwt);
		expect(window.location.hash).toBe("");
	});

	it("rejects malformed embed token fragments", () => {
		vi.spyOn(window, "top", "get").mockReturnValue({} as Window);
		window.history.replaceState(null, "", "/#embed_token=not-a-jwt");

		consumeEmbedTokenFromHash();

		expect(sessionStorage.getItem(EMBED_TOKEN_KEY)).toBeNull();
		expect(window.location.hash).toBe("");
	});

	it("does not persist embed tokens in a top-level tab", () => {
		vi.spyOn(window, "top", "get").mockReturnValue(window);
		window.history.replaceState(null, "", `/#embed_token=${validJwt}`);

		consumeEmbedTokenFromHash();

		expect(sessionStorage.getItem(EMBED_TOKEN_KEY)).toBeNull();
		expect(window.location.hash).toBe("");
	});
});

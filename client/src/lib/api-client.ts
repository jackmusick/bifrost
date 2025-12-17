/**
 * Type-safe API client using openapi-fetch and openapi-react-query
 * Automatically handles X-Organization-Id and X-User-Id headers from session storage
 * Includes CSRF protection for cookie-based authentication
 *
 * Usage:
 * - $api.useQuery("get", "/api/endpoint") for queries in components
 * - $api.useMutation("post", "/api/endpoint") for mutations in components
 * - apiClient.GET/POST/etc for imperative usage outside React
 */

import createClient from "openapi-fetch";
import createQueryClient from "openapi-react-query";
import type { paths } from "./v1";
import { parseApiError, ApiError, RateLimitError } from "./api-error";

// Token storage key (shared with AuthContext)
// Note: Refresh token is stored in HttpOnly cookie only (more secure)
const ACCESS_TOKEN_KEY = "bifrost_access_token";

// Buffer time before expiration to trigger refresh (60 seconds)
const TOKEN_REFRESH_BUFFER_SECONDS = 60;

// Endpoints that should skip token refresh check
const AUTH_ENDPOINTS = [
	"/auth/login",
	"/auth/status",
	"/auth/refresh",
	"/api/auth/refresh",
	"/auth/oauth/callback",
	"/auth/mfa/login",
	"/auth/mfa/setup",
];

/**
 * Parse JWT payload without verification (server validates)
 */
function parseJwt(token: string): { exp?: number } | null {
	try {
		const base64Url = token.split(".")[1];
		if (!base64Url) return null;
		const base64 = base64Url.replace(/-/g, "+").replace(/_/g, "/");
		const jsonPayload = decodeURIComponent(
			atob(base64)
				.split("")
				.map(
					(c) =>
						"%" + ("00" + c.charCodeAt(0).toString(16)).slice(-2),
				)
				.join(""),
		);
		return JSON.parse(jsonPayload);
	} catch {
		return null;
	}
}

/**
 * Check if token is expiring soon (within buffer period)
 */
function isTokenExpiringSoon(token: string): boolean {
	const payload = parseJwt(token);
	if (!payload || payload.exp === undefined) return true;
	return Date.now() >= (payload.exp - TOKEN_REFRESH_BUFFER_SECONDS) * 1000;
}

// Lock to prevent concurrent refresh attempts
let refreshPromise: Promise<boolean> | null = null;

/**
 * Refresh the access token using the refresh token cookie
 * Uses HttpOnly cookie for refresh token (more secure than localStorage)
 * Returns true if successful, false if refresh failed
 */
async function refreshAccessToken(): Promise<boolean> {
	// Use lock to prevent concurrent refresh attempts
	if (refreshPromise) {
		return refreshPromise;
	}

	refreshPromise = (async () => {
		try {
			// POST to refresh endpoint - browser sends refresh_token cookie automatically
			const res = await fetch("/api/auth/refresh", {
				method: "POST",
				credentials: "same-origin",
			});

			if (!res.ok) return false;

			const data = await res.json();
			if (data.access_token) {
				// Store access token in localStorage for proactive expiry checking
				localStorage.setItem(ACCESS_TOKEN_KEY, data.access_token);
				return true;
			}
			return false;
		} catch {
			return false;
		}
	})().finally(() => {
		refreshPromise = null;
	});

	return refreshPromise;
}

/**
 * Handle authentication failure - clear session and redirect to login
 */
function handleAuthFailure(): void {
	sessionStorage.removeItem("userId");
	sessionStorage.removeItem("current_org_id");
	localStorage.removeItem(ACCESS_TOKEN_KEY);

	const currentPath = window.location.pathname;
	if (currentPath !== "/login" && currentPath !== "/setup") {
		window.location.href = `/login?returnTo=${encodeURIComponent(currentPath)}`;
	}
}

/**
 * Ensure we have a valid (non-expiring) access token before making a request
 * Proactively refreshes token before it expires
 */
async function ensureValidToken(): Promise<boolean> {
	const token = localStorage.getItem(ACCESS_TOKEN_KEY);

	// No token at all - user needs to log in
	if (!token) return false;

	// Token is still valid - proceed
	if (!isTokenExpiringSoon(token)) return true;

	// Token is expiring soon - refresh it
	// Lock is handled inside refreshAccessToken
	return refreshAccessToken();
}

/**
 * Get CSRF token from cookie (set by backend on login/OAuth)
 * The csrf_token cookie is non-HttpOnly so JavaScript can read it
 */
function getCsrfToken(): string | null {
	const match = document.cookie.match(/(?:^|;\s*)csrf_token=([^;]+)/);
	return match ? decodeURIComponent(match[1]) : null;
}

/**
 * Check if request method requires CSRF protection
 */
function requiresCsrf(method: string): boolean {
	return ["POST", "PUT", "PATCH", "DELETE"].includes(method.toUpperCase());
}

// Create base client (internal - don't export directly)
// baseUrl is empty because OpenAPI paths already include /api prefix
const baseClient = createClient<paths>({
	baseUrl: "",
});

// Middleware to automatically inject organization and user context headers,
// CSRF tokens, handle token refresh, and handle authentication errors
baseClient.use({
	async onRequest({ request }) {
		const url = new URL(request.url, window.location.origin);
		const isAuthEndpoint = AUTH_ENDPOINTS.some((ep) =>
			url.pathname.startsWith(ep),
		);

		// Skip token refresh for auth endpoints to avoid infinite loops
		if (!isAuthEndpoint) {
			const hasValidToken = await ensureValidToken();
			if (!hasValidToken) {
				// No valid token and refresh failed - redirect to login
				const currentPath = window.location.pathname;
				if (currentPath !== "/login" && currentPath !== "/setup") {
					window.location.href = `/login?returnTo=${encodeURIComponent(currentPath)}`;
				}
				// Throw to prevent the request from proceeding
				throw new Error("Authentication required");
			}
		}

		// Get organization ID from session storage (set by org switcher)
		const orgId = sessionStorage.getItem("current_org_id");
		if (orgId) {
			request.headers.set("X-Organization-Id", orgId);
		}

		// Get user ID from session storage (set by auth provider)
		const userId = sessionStorage.getItem("userId");
		if (userId) {
			request.headers.set("X-User-Id", userId);
		}

		// Add CSRF token for mutating requests (cookie-based auth protection)
		if (requiresCsrf(request.method)) {
			const csrfToken = getCsrfToken();
			if (csrfToken) {
				request.headers.set("X-CSRF-Token", csrfToken);
			}
		}

		// Authentication via HttpOnly cookie (set by backend on login)
		// No need to manually add Authorization header - cookies are sent automatically
		// For service-to-service auth, clients can still use Authorization: Bearer header

		return request;
	},
	async onResponse({ request, response }) {
		// Handle 429 Too Many Requests - rate limited
		if (response.status === 429) {
			const retryAfter = parseInt(
				response.headers.get("Retry-After") || "60",
				10,
			);
			throw new RateLimitError(retryAfter);
		}

		// Handle 401 Unauthorized - attempt token refresh and retry
		if (response.status === 401) {
			// Skip retry for auth endpoints to prevent infinite loops
			const url = request.url;
			if (AUTH_ENDPOINTS.some((ep) => url.includes(ep))) {
				handleAuthFailure();
				return response;
			}

			// Attempt token refresh via cookie
			const refreshed = await refreshAccessToken();
			if (refreshed) {
				// Retry original request with fresh credentials
				return fetch(request.clone());
			}

			// Refresh failed - redirect to login
			handleAuthFailure();
		}
		// 403 Forbidden = permission issue, don't redirect (user is authenticated)
		// Let the calling code handle displaying an appropriate error message

		return response;
	},
});

/**
 * Raw API client with automatic header injection
 * Use for imperative calls outside React components
 * For React components, prefer $api.useQuery() and $api.useMutation()
 */
export const apiClient = baseClient;

/**
 * Type-safe React Query hooks from OpenAPI spec
 * Use in React components for automatic caching, refetching, and loading states
 *
 * @example
 * // Query
 * const { data, isLoading } = $api.useQuery("get", "/api/organizations");
 *
 * // Query with parameters
 * const { data } = $api.useQuery("get", "/api/organizations/{org_id}", {
 *   params: { path: { org_id: "123" } }
 * });
 *
 * // Mutation
 * const mutation = $api.useMutation("post", "/api/organizations");
 * mutation.mutate({ body: { name: "New Org" } });
 */
export const $api = createQueryClient(baseClient);

/**
 * Shared response handler for all clients
 * Handles 429 rate limiting and 401 authentication errors with retry
 */
async function handleAuthResponse(
	request: Request,
	response: Response,
): Promise<Response> {
	// Handle 429 Too Many Requests - rate limited
	if (response.status === 429) {
		const retryAfter = parseInt(
			response.headers.get("Retry-After") || "60",
			10,
		);
		throw new RateLimitError(retryAfter);
	}

	// Handle 401 Unauthorized - attempt token refresh and retry
	if (response.status === 401) {
		const url = request.url;
		if (!AUTH_ENDPOINTS.some((ep) => url.includes(ep))) {
			const refreshed = await refreshAccessToken();
			if (refreshed) {
				// Retry original request with fresh credentials
				return fetch(request.clone());
			}
		}
		handleAuthFailure();
	}

	return response;
}

/**
 * Helper to override organization context for admin operations
 */
export function withOrgContext(orgId: string) {
	const client = createClient<paths>({
		baseUrl: "",
	});

	client.use({
		async onRequest({ request }) {
			// Ensure valid token before request
			const hasValidToken = await ensureValidToken();
			if (!hasValidToken) {
				const currentPath = window.location.pathname;
				if (currentPath !== "/login" && currentPath !== "/setup") {
					window.location.href = `/login?returnTo=${encodeURIComponent(currentPath)}`;
				}
				throw new Error("Authentication required");
			}

			request.headers.set("X-Organization-Id", orgId);

			const userId = sessionStorage.getItem("userId");
			if (userId) {
				request.headers.set("X-User-Id", userId);
			}

			// Add CSRF token for mutating requests
			if (requiresCsrf(request.method)) {
				const csrfToken = getCsrfToken();
				if (csrfToken) {
					request.headers.set("X-CSRF-Token", csrfToken);
				}
			}

			return request;
		},
		async onResponse({ request, response }) {
			return handleAuthResponse(request, response);
		},
	});

	return client;
}

/**
 * Helper to override user context for admin operations
 */
export function withUserContext(userId: string) {
	const client = createClient<paths>({
		baseUrl: "",
	});

	client.use({
		async onRequest({ request }) {
			// Ensure valid token before request
			const hasValidToken = await ensureValidToken();
			if (!hasValidToken) {
				const currentPath = window.location.pathname;
				if (currentPath !== "/login" && currentPath !== "/setup") {
					window.location.href = `/login?returnTo=${encodeURIComponent(currentPath)}`;
				}
				throw new Error("Authentication required");
			}

			const orgId = sessionStorage.getItem("current_org_id");
			if (orgId) {
				request.headers.set("X-Organization-Id", orgId);
			}

			request.headers.set("X-User-Id", userId);

			// Add CSRF token for mutating requests
			if (requiresCsrf(request.method)) {
				const csrfToken = getCsrfToken();
				if (csrfToken) {
					request.headers.set("X-CSRF-Token", csrfToken);
				}
			}

			return request;
		},
		async onResponse({ request, response }) {
			return handleAuthResponse(request, response);
		},
	});

	return client;
}

/**
 * Helper to set both org and user context (for admin operations)
 */
export function withContext(orgId: string, userId: string) {
	const client = createClient<paths>({
		baseUrl: "",
	});

	client.use({
		async onRequest({ request }) {
			// Ensure valid token before request
			const hasValidToken = await ensureValidToken();
			if (!hasValidToken) {
				const currentPath = window.location.pathname;
				if (currentPath !== "/login" && currentPath !== "/setup") {
					window.location.href = `/login?returnTo=${encodeURIComponent(currentPath)}`;
				}
				throw new Error("Authentication required");
			}

			request.headers.set("X-Organization-Id", orgId);
			request.headers.set("X-User-Id", userId);

			// Add CSRF token for mutating requests
			if (requiresCsrf(request.method)) {
				const csrfToken = getCsrfToken();
				if (csrfToken) {
					request.headers.set("X-CSRF-Token", csrfToken);
				}
			}

			return request;
		},
		async onResponse({ request, response }) {
			return handleAuthResponse(request, response);
		},
	});

	return client;
}

/**
 * Helper to handle openapi-fetch errors
 * Converts the error object to an ApiError with proper message extraction
 */
export function handleApiError(error: unknown): never {
	throw parseApiError(error);
}

// Re-export error classes for convenience
export { ApiError, RateLimitError };

/**
 * Authenticated fetch wrapper for endpoints not in OpenAPI spec
 * Automatically injects context headers, CSRF tokens, and handles 401 responses
 * Auth is handled via HttpOnly cookies (sent automatically by browser)
 */
export async function authFetch(
	url: string,
	options: RequestInit = {},
): Promise<Response> {
	// Check if this is an auth endpoint that should skip token refresh
	const isAuthEndpoint = AUTH_ENDPOINTS.some((ep) => url.startsWith(ep));

	// Ensure valid token before request (skip for auth endpoints)
	if (!isAuthEndpoint) {
		const hasValidToken = await ensureValidToken();
		if (!hasValidToken) {
			handleAuthFailure();
			throw new Error("Authentication required");
		}
	}

	const headers = new Headers(options.headers);
	const method = options.method?.toUpperCase() || "GET";

	// Auth via cookie (sent automatically by browser)
	// No need to manually add Authorization header

	// Add org context
	const orgId = sessionStorage.getItem("current_org_id");
	if (orgId) {
		headers.set("X-Organization-Id", orgId);
	}

	// Add user context
	const userId = sessionStorage.getItem("userId");
	if (userId) {
		headers.set("X-User-Id", userId);
	}

	// Add CSRF token for mutating requests
	if (requiresCsrf(method)) {
		const csrfToken = getCsrfToken();
		if (csrfToken) {
			headers.set("X-CSRF-Token", csrfToken);
		}
	}

	// Default to JSON content type for POST/PUT/PATCH
	// BUT: Don't set Content-Type if body is FormData (browser will set it with boundary)
	if (
		["POST", "PUT", "PATCH"].includes(method) &&
		!headers.has("Content-Type") &&
		!(options.body instanceof FormData)
	) {
		headers.set("Content-Type", "application/json");
	}

	// Build request for retry support
	const request = new Request(url, {
		...options,
		headers,
		credentials: "same-origin",
	});

	const response = await fetch(request.clone());

	// Handle 429 and 401 with retry support
	return handleAuthResponse(request, response);
}

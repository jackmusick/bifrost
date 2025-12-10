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
// CSRF tokens, and handle authentication errors
baseClient.use({
	async onRequest({ request }) {
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
	async onResponse({ response }) {
		// Handle 429 Too Many Requests - rate limited
		if (response.status === 429) {
			const retryAfter = parseInt(
				response.headers.get("Retry-After") || "60",
				10,
			);
			throw new RateLimitError(retryAfter);
		}

		// Handle 401 Unauthorized - token expired or invalid
		// Only redirect if it's a true authentication failure, not a permission issue
		if (response.status === 401) {
			// Clear session storage (cookies are HttpOnly and handled by backend)
			sessionStorage.removeItem("userId");
			sessionStorage.removeItem("current_org_id");

			// Redirect to login, preserving the current path for return
			const currentPath = window.location.pathname;
			if (currentPath !== "/login" && currentPath !== "/setup") {
				window.location.href = `/login?returnTo=${encodeURIComponent(currentPath)}`;
			}
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
 * Handles 429 rate limiting and 401 authentication errors
 */
function handleAuthResponse(response: Response): Response {
	// Handle 429 Too Many Requests - rate limited
	if (response.status === 429) {
		const retryAfter = parseInt(
			response.headers.get("Retry-After") || "60",
			10,
		);
		throw new RateLimitError(retryAfter);
	}

	// Handle 401 Unauthorized - token expired or invalid
	if (response.status === 401) {
		// Clear session storage (cookies are HttpOnly and handled by backend)
		sessionStorage.removeItem("userId");
		sessionStorage.removeItem("current_org_id");

		// Redirect to login, preserving the current path for return
		const currentPath = window.location.pathname;
		if (currentPath !== "/login" && currentPath !== "/setup") {
			window.location.href = `/login?returnTo=${encodeURIComponent(currentPath)}`;
		}
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
		async onResponse({ response }) {
			return handleAuthResponse(response);
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
		async onResponse({ response }) {
			return handleAuthResponse(response);
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
		async onResponse({ response }) {
			return handleAuthResponse(response);
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

	// Ensure credentials are sent (required for cookies in cross-origin scenarios)
	const response = await fetch(url, {
		...options,
		headers,
		credentials: "same-origin", // Send cookies for same-origin requests
	});

	// Handle 429 and 401 the same way as apiClient
	return handleAuthResponse(response);
}

/**
 * Platform hook: useParams
 *
 * Wrapper around react-router's useParams for JSX runtime.
 * Returns URL path parameters as a Record<string, string>.
 */

import { useParams as useRouterParams } from "react-router-dom";

/**
 * Get URL path parameters from the current route
 *
 * @returns Object containing all URL parameters
 *
 * @example
 * ```jsx
 * // URL: /clients/123/contacts
 * // Route: /clients/:clientId/contacts
 *
 * const params = useParams();
 * // params = { clientId: "123" }
 *
 * const { data: client } = useWorkflow('get_client', { id: params.clientId });
 * ```
 */
export function useParams(): Record<string, string> {
	const params = useRouterParams();

	// Filter out undefined values and ensure all values are strings
	const result: Record<string, string> = {};
	for (const [key, value] of Object.entries(params)) {
		if (value !== undefined) {
			result[key] = value;
		}
	}

	return result;
}

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
 * const { data: client } = useWorkflowQuery('get_client', { id: params.clientId });
 * ```
 */
// Keys that could pollute the prototype chain if assigned via bracket notation
// on a regular object. We use Object.create(null) below to make this defensive,
// but we also skip these keys explicitly so a parent route accidentally named
// `__proto__` (or similar) doesn't end up shadowing real params.
const FORBIDDEN_PARAM_KEYS = new Set(["__proto__", "constructor", "prototype"]);

export function useParams(): Record<string, string> {
	const params = useRouterParams();

	// Use a null-prototype object so attacker-controlled URL segments cannot
	// reach Object.prototype via bracket-notation assignment.
	const result: Record<string, string> = Object.create(null);
	for (const [key, value] of Object.entries(params)) {
		if (value === undefined) continue;
		if (FORBIDDEN_PARAM_KEYS.has(key)) continue;
		result[key] = value;
	}

	return result;
}

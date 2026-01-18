/**
 * Platform hook: useSearchParams
 *
 * Wrapper around react-router's useSearchParams for JSX runtime.
 * Returns URLSearchParams for query string access.
 */

import { useSearchParams as useRouterSearchParams } from "react-router-dom";

/**
 * Get query string parameters from the current URL
 *
 * @returns URLSearchParams object for accessing query parameters
 *
 * @example
 * ```jsx
 * // URL: /clients?status=active&page=2
 *
 * const searchParams = useSearchParams();
 *
 * const status = searchParams.get('status'); // "active"
 * const page = searchParams.get('page'); // "2"
 *
 * // Iterate over all params
 * for (const [key, value] of searchParams) {
 *   console.log(key, value);
 * }
 * ```
 */
export function useSearchParams(): URLSearchParams {
	const [searchParams] = useRouterSearchParams();
	return searchParams;
}

/**
 * App Code Platform APIs
 *
 * This module exports all platform hooks and functions that are injected
 * into the runtime scope. These APIs allow apps to interact with
 * the platform (run workflows, navigate, access user info, etc.).
 *
 * Usage: These are injected into the runtime scope automatically.
 * User code can use them without imports:
 *
 * ```jsx
 * // All of these are available in code
 * const { data, isLoading } = useWorkflow('list_clients');
 * const user = useUser();
 * const params = useParams();
 * navigate('/clients');
 * ```
 */

// Workflow execution
export { useWorkflow } from "./useWorkflow";

// Router utilities
export { useParams } from "./useParams";
export { useSearchParams } from "./useSearchParams";
export {
	navigate,
	useNavigate,
	setNavigateRef,
	clearNavigateRef,
} from "./navigate";

// User context
export { useUser } from "./useUser";

// App state
export {
	useAppState,
	appCodeStateStore,
	resetAppCodeState,
} from "./useAppState";

// UI Components
export { APP_CODE_COMPONENTS } from "./components";
export type { AppCodeComponents } from "./components";

/**
 * Platform scope object for runtime
 *
 * This object contains all platform APIs that are injected into
 * the runtime scope. The compiler uses this to make
 * these functions/hooks available to user-authored code.
 *
 * Note: React hooks (useState, useEffect, etc.) are added separately
 * by the runtime to ensure they come from the same React instance.
 */
export { createPlatformScope } from "./scope";

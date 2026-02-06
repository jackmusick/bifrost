/**
 * Platform Scope for App Code Runtime
 *
 * Creates the scope object that gets injected into the runtime.
 * All platform APIs are bundled here for easy injection.
 */

import {
	useLocation,
	useMatch,
	useResolvedPath,
	Outlet,
	useOutletContext,
} from "react-router-dom";
import { useWorkflow } from "./useWorkflow";
import { useParams } from "./useParams";
import { useSearchParams } from "./useSearchParams";
import { navigate, useNavigate } from "./navigate";
import { useUser } from "./useUser";
import { useAppState } from "./useAppState";
import { Link, NavLink, Navigate } from "./navigation";

/**
 * Platform scope object containing all platform APIs
 *
 * This is merged with React hooks and UI components to create
 * the full scope available to user code.
 *
 * @example
 * ```typescript
 * // In app-code-runtime.ts
 * const scope = {
 *   ...createPlatformScope(),
 *   React,
 *   useState: React.useState,
 *   useEffect: React.useEffect,
 *   ...UIComponents,
 * };
 * ```
 */
export function createPlatformScope(): Record<string, unknown> {
	return {
		// Workflow execution
		useWorkflow,

		// React Router - ALL commonly used exports
		useLocation,
		useParams,
		useSearchParams,
		useMatch,
		useResolvedPath,
		useOutletContext,
		navigate,
		useNavigate,
		Outlet,
		Link,
		NavLink,
		Navigate,

		// User context
		useUser,

		// App state
		useAppState,
	};
}

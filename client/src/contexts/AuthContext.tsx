/**
 * Authentication Context
 *
 * Provides JWT-based authentication state throughout the application.
 * Handles token storage, refresh, and user state management.
 */

import {
	createContext,
	useContext,
	useCallback,
	useEffect,
	useState,
	type ReactNode,
} from "react";
import { useNavigate, useLocation } from "react-router-dom";

// User info extracted from JWT
export interface AuthUser {
	id: string;
	email: string;
	name: string;
	userType: "PLATFORM" | "ORG";
	isSuperuser: boolean;
	organizationId: string | null;
	roles: string[];
}

// Login response with MFA state
export interface LoginResult {
	success: boolean;
	mfaRequired?: boolean;
	mfaSetupRequired?: boolean;
	mfaToken?: string;
	availableMethods?: string[];
	expiresIn?: number;
}

interface AuthContextValue {
	// State
	user: AuthUser | null;
	isAuthenticated: boolean;
	isLoading: boolean;
	needsSetup: boolean;

	// Role helpers
	isPlatformAdmin: boolean;
	isOrgUser: boolean;
	hasRole: (role: string) => boolean;

	// Actions
	login: (email: string, password: string) => Promise<LoginResult>;
	loginWithMfa: (
		mfaToken: string,
		code: string,
		trustDevice?: boolean,
	) => Promise<void>;
	loginWithOAuth: (
		provider: string,
		code: string,
		state: string,
	) => Promise<void>;
	logout: () => void;
	refreshToken: () => Promise<boolean>;
	checkAuthStatus: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

// Token storage keys
const ACCESS_TOKEN_KEY = "bifrost_access_token";
const REFRESH_TOKEN_KEY = "bifrost_refresh_token";
const USER_KEY = "bifrost_user";

// JWT payload structure
interface JwtPayload {
	sub?: string;
	email?: string;
	name?: string;
	user_type?: "PLATFORM" | "ORG";
	is_superuser?: boolean;
	org_id?: string | null;
	roles?: string[];
	exp?: number;
}

// Parse JWT payload (without verification - server validates)
function parseJwt(token: string): JwtPayload | null {
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

// Extract user from JWT payload
function extractUser(payload: JwtPayload): AuthUser {
	return {
		id: payload.sub || "",
		email: payload.email || "",
		name: payload.name || "",
		userType: payload.user_type || "ORG",
		isSuperuser: payload.is_superuser || false,
		organizationId: payload.org_id || null,
		roles: payload.roles || [],
	};
}

// Check if token is expired (with 30s buffer)
function isTokenExpired(token: string): boolean {
	const payload = parseJwt(token);
	if (!payload || payload.exp === undefined) return true;
	return Date.now() >= (payload.exp - 30) * 1000;
}

interface AuthProviderProps {
	children: ReactNode;
}

export function AuthProvider({ children }: AuthProviderProps) {
	const [user, setUser] = useState<AuthUser | null>(null);
	const [isLoading, setIsLoading] = useState(true);
	const [needsSetup, setNeedsSetup] = useState(false);
	const navigate = useNavigate();
	const location = useLocation();

	// Check auth status on mount
	const checkAuthStatus = useCallback(async () => {
		try {
			// Check if system needs initial setup
			const statusRes = await fetch("/auth/status");
			if (statusRes.ok) {
				const status = await statusRes.json();
				setNeedsSetup(status.needs_setup);

				if (status.needs_setup) {
					setIsLoading(false);
					return;
				}
			}

			// Check for existing token
			const token = localStorage.getItem(ACCESS_TOKEN_KEY);
			if (!token) {
				setUser(null);
				setIsLoading(false);
				return;
			}

			// Check if token is expired
			if (isTokenExpired(token)) {
				// Try to refresh
				const refreshed = await refreshTokenInternal();
				if (!refreshed) {
					setUser(null);
					setIsLoading(false);
					return;
				}
			}

			// Parse user from token
			const payload = parseJwt(token);
			if (payload) {
				const extractedUser = extractUser(payload);
				setUser(extractedUser);

				// Store user ID for org context
				sessionStorage.setItem("userId", extractedUser.id);
			}
		} catch (error) {
			console.error("Auth check failed:", error);
			setUser(null);
		} finally {
			setIsLoading(false);
		}
	}, []);

	// Internal refresh function (no hooks)
	const refreshTokenInternal = async (): Promise<boolean> => {
		try {
			const refreshToken = localStorage.getItem(REFRESH_TOKEN_KEY);
			if (!refreshToken) return false;

			const res = await fetch("/api/auth/refresh", {
				method: "POST",
				headers: { "Content-Type": "application/json" },
				body: JSON.stringify({ refresh_token: refreshToken }),
			});

			if (!res.ok) return false;

			const data = await res.json();
			if (data.access_token) {
				localStorage.setItem(ACCESS_TOKEN_KEY, data.access_token);
				if (data.refresh_token) {
					localStorage.setItem(REFRESH_TOKEN_KEY, data.refresh_token);
				}

				const payload = parseJwt(data.access_token);
				if (payload) {
					const extractedUser = extractUser(payload);
					setUser(extractedUser);
					localStorage.setItem(
						USER_KEY,
						JSON.stringify(extractedUser),
					);
					sessionStorage.setItem("userId", extractedUser.id);
				}
				return true;
			}
			return false;
		} catch {
			return false;
		}
	};

	// Login with email/password
	const login = useCallback(
		async (email: string, password: string): Promise<LoginResult> => {
			const formData = new FormData();
			formData.append("username", email);
			formData.append("password", password);

			const res = await fetch("/auth/login", {
				method: "POST",
				body: formData,
			});

			if (!res.ok) {
				const error = await res.json().catch(() => ({}));
				throw new Error(error.detail || "Login failed");
			}

			const data = await res.json();

			// Check for MFA requirements
			if (data.mfa_required) {
				return {
					success: false,
					mfaRequired: true,
					mfaToken: data.mfa_token,
					availableMethods: data.available_methods,
					expiresIn: data.expires_in,
				};
			}

			if (data.mfa_setup_required) {
				return {
					success: false,
					mfaSetupRequired: true,
					mfaToken: data.mfa_token,
					expiresIn: data.expires_in,
				};
			}

			// Success - store tokens
			if (data.access_token) {
				localStorage.setItem(ACCESS_TOKEN_KEY, data.access_token);
				if (data.refresh_token) {
					localStorage.setItem(REFRESH_TOKEN_KEY, data.refresh_token);
				}

				const payload = parseJwt(data.access_token);
				if (payload) {
					const extractedUser = extractUser(payload);
					setUser(extractedUser);
					localStorage.setItem(
						USER_KEY,
						JSON.stringify(extractedUser),
					);
					sessionStorage.setItem("userId", extractedUser.id);
				}

				return { success: true };
			}

			throw new Error("No access token received");
		},
		[],
	);

	// Complete MFA verification during login (for users with MFA already set up)
	const loginWithMfa = useCallback(
		async (
			mfaToken: string,
			code: string,
			trustDevice: boolean = false,
		): Promise<void> => {
			const res = await fetch("/auth/mfa/login", {
				method: "POST",
				headers: { "Content-Type": "application/json" },
				body: JSON.stringify({
					mfa_token: mfaToken,
					code,
					trust_device: trustDevice,
				}),
			});

			if (!res.ok) {
				const error = await res.json().catch(() => ({}));
				throw new Error(error.detail || "MFA verification failed");
			}

			const data = await res.json();

			if (data.access_token) {
				localStorage.setItem(ACCESS_TOKEN_KEY, data.access_token);

				const payload = parseJwt(data.access_token);
				if (payload) {
					const extractedUser = extractUser(payload);
					setUser(extractedUser);
					localStorage.setItem(
						USER_KEY,
						JSON.stringify(extractedUser),
					);
					sessionStorage.setItem("userId", extractedUser.id);
				}
			}
		},
		[],
	);

	// Complete OAuth login
	// Note: code_verifier is now handled server-side (stored in Redis keyed by state)
	const loginWithOAuth = useCallback(
		async (
			provider: string,
			code: string,
			state: string,
		): Promise<void> => {
			const res = await fetch("/auth/oauth/callback", {
				method: "POST",
				headers: { "Content-Type": "application/json" },
				body: JSON.stringify({
					provider,
					code,
					state,
					// code_verifier not needed - server retrieves it from Redis using state
				}),
			});

			if (!res.ok) {
				const error = await res.json().catch(() => ({}));
				throw new Error(error.detail || "OAuth login failed");
			}

			const data = await res.json();

			if (data.access_token) {
				localStorage.setItem(ACCESS_TOKEN_KEY, data.access_token);

				const payload = parseJwt(data.access_token);
				if (payload) {
					const extractedUser = extractUser(payload);
					setUser(extractedUser);
					localStorage.setItem(
						USER_KEY,
						JSON.stringify(extractedUser),
					);
					sessionStorage.setItem("userId", extractedUser.id);
				}
			}
		},
		[],
	);

	// Logout
	const logout = useCallback(() => {
		localStorage.removeItem(ACCESS_TOKEN_KEY);
		localStorage.removeItem(USER_KEY);
		sessionStorage.removeItem("userId");
		sessionStorage.removeItem("current_org_id");
		setUser(null);
		navigate("/login");
	}, [navigate]);

	// Refresh token
	const refreshToken = useCallback(async (): Promise<boolean> => {
		return refreshTokenInternal();
	}, []);

	// Check auth on mount
	useEffect(() => {
		checkAuthStatus();
	}, [checkAuthStatus]);

	// Redirect unauthenticated users to login
	useEffect(() => {
		if (isLoading) return;

		// Public routes that don't require auth
		const publicRoutes = [
			"/login",
			"/setup",
			"/auth/callback",
			"/mfa-setup",
		];
		const isPublicRoute = publicRoutes.some((route) =>
			location.pathname.startsWith(route),
		);

		if (needsSetup && location.pathname !== "/setup") {
			navigate("/setup");
			return;
		}

		if (!user && !isPublicRoute && !needsSetup) {
			navigate("/login", { state: { from: location.pathname } });
		}
	}, [isLoading, user, needsSetup, location.pathname, navigate]);

	const value: AuthContextValue = {
		user,
		isAuthenticated: !!user,
		isLoading,
		needsSetup,
		isPlatformAdmin: user?.roles.includes("PlatformAdmin") ?? false,
		isOrgUser: user?.roles.includes("OrgUser") ?? false,
		hasRole: (role: string) => user?.roles.includes(role) ?? false,
		login,
		loginWithMfa,
		loginWithOAuth,
		logout,
		refreshToken,
		checkAuthStatus,
	};

	return (
		<AuthContext.Provider value={value}>{children}</AuthContext.Provider>
	);
}

export function useAuth() {
	const context = useContext(AuthContext);
	if (!context) {
		throw new Error("useAuth must be used within an AuthProvider");
	}
	return context;
}

// Export token getter for API client
export function getAccessToken(): string | null {
	return localStorage.getItem(ACCESS_TOKEN_KEY);
}

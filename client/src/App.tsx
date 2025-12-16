import { lazy, Suspense } from "react";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Layout } from "@/components/layout/Layout";
import { ContentLayout } from "@/components/layout/ContentLayout";
import { ProtectedRoute } from "@/components/ProtectedRoute";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { EditorOverlay } from "@/components/editor/EditorOverlay";
import { QuickAccess } from "@/components/quick-access/QuickAccess";
import { PageLoader } from "@/components/PageLoader";
import { useEditorStore } from "@/stores/editorStore";
import { useQuickAccessStore } from "@/stores/quickAccessStore";
import { AuthProvider } from "@/contexts/AuthContext";
import { OrgScopeProvider, useOrgScope } from "@/contexts/OrgScopeContext";
import {
	KeyboardProvider,
	useCmdCtrlShortcut,
} from "@/contexts/KeyboardContext";

// Lazy load all page components for code splitting
const Dashboard = lazy(() =>
	import("@/pages/Dashboard").then((m) => ({ default: m.Dashboard })),
);
const Config = lazy(() =>
	import("@/pages/Config").then((m) => ({ default: m.Config })),
);
const Roles = lazy(() =>
	import("@/pages/Roles").then((m) => ({ default: m.Roles })),
);
const Users = lazy(() =>
	import("@/pages/Users").then((m) => ({ default: m.Users })),
);
const Organizations = lazy(() =>
	import("@/pages/Organizations").then((m) => ({ default: m.Organizations })),
);
const Forms = lazy(() =>
	import("@/pages/Forms").then((m) => ({ default: m.Forms })),
);
const FormBuilder = lazy(() =>
	import("@/pages/FormBuilder").then((m) => ({ default: m.FormBuilder })),
);
const RunForm = lazy(() =>
	import("@/pages/RunForm").then((m) => ({ default: m.RunForm })),
);
const Workflows = lazy(() =>
	import("@/pages/Workflows").then((m) => ({ default: m.Workflows })),
);
const ExecuteWorkflow = lazy(() =>
	import("@/pages/ExecuteWorkflow").then((m) => ({
		default: m.ExecuteWorkflow,
	})),
);
const ExecutionHistory = lazy(() =>
	import("@/pages/ExecutionHistory").then((m) => ({
		default: m.ExecutionHistory,
	})),
);
const ExecutionDetails = lazy(() =>
	import("@/pages/ExecutionDetails").then((m) => ({
		default: m.ExecutionDetails,
	})),
);
const OAuthConnections = lazy(() =>
	import("@/pages/OAuthConnections").then((m) => ({
		default: m.OAuthConnections,
	})),
);
const OAuthCallback = lazy(() =>
	import("@/pages/OAuthCallback").then((m) => ({ default: m.OAuthCallback })),
);
const Docs = lazy(() =>
	import("@/pages/Docs").then((m) => ({ default: m.Docs })),
);
const Schedules = lazy(() =>
	import("@/pages/Schedules").then((m) => ({ default: m.Schedules })),
);
const Settings = lazy(() =>
	import("@/pages/Settings").then((m) => ({ default: m.Settings })),
);
const UserSettings = lazy(() =>
	import("@/pages/UserSettings").then((m) => ({ default: m.UserSettings })),
);
const SystemLogs = lazy(() => import("@/pages/SystemLogs"));
const Login = lazy(() =>
	import("@/pages/Login").then((m) => ({ default: m.Login })),
);
const Setup = lazy(() =>
	import("@/pages/Setup").then((m) => ({ default: m.Setup })),
);
const MFASetup = lazy(() =>
	import("@/pages/MFASetup").then((m) => ({ default: m.MFASetup })),
);
const AuthCallback = lazy(() =>
	import("@/pages/AuthCallback").then((m) => ({ default: m.AuthCallback })),
);
const DevRun = lazy(() =>
	import("@/pages/DevRun").then((m) => ({ default: m.DevRun })),
);
const CLI = lazy(() => import("@/pages/CLI").then((m) => ({ default: m.CLI })));
const Workbench = lazy(() =>
	import("@/pages/Workbench").then((m) => ({ default: m.Workbench })),
);

function AppRoutes() {
	const { brandingLoaded } = useOrgScope();
	const isQuickAccessOpen = useQuickAccessStore((state) => state.isOpen);
	const openQuickAccess = useQuickAccessStore(
		(state) => state.openQuickAccess,
	);
	const closeQuickAccess = useQuickAccessStore(
		(state) => state.closeQuickAccess,
	);
	const openEditor = useEditorStore((state) => state.openEditor);
	const isEditorOpen = useEditorStore((state) => state.isOpen);

	// Register Cmd+K shortcut for quick access
	useCmdCtrlShortcut("quick-access", "k", () => {
		openQuickAccess();
	});

	// Register Cmd+/ to toggle code editor
	useCmdCtrlShortcut("toggle-editor", "/", () => {
		if (!isEditorOpen) {
			openEditor();
		}
	});

	// Wait for branding colors to load before rendering
	// Logo component handles its own skeleton loading state
	if (!brandingLoaded) {
		return <PageLoader message="Loading application..." fullScreen />;
	}

	return (
		<>
			{/* Quick Access - Cmd+K search */}
			<QuickAccess
				isOpen={isQuickAccessOpen}
				onClose={closeQuickAccess}
			/>

			{/* Editor Overlay - Rendered globally on top of all pages */}
			<EditorOverlay />

			<Suspense fallback={<PageLoader />}>
				<Routes>
					{/* Public routes - no auth required */}
					<Route path="login" element={<Login />} />
					<Route path="setup" element={<Setup />} />
					<Route path="mfa-setup" element={<MFASetup />} />
					<Route path="auth/callback" element={<AuthCallback />} />

					{/* OAuth Callback - Public (no auth, no layout) */}
					<Route
						path="oauth/callback/:connectionName"
						element={<OAuthCallback />}
					/>

					<Route path="/" element={<Layout />}>
						{/* Dashboard - PlatformAdmin only (OrgUsers redirected to /forms) */}
						<Route index element={<Dashboard />} />

						{/* Workflows - PlatformAdmin only */}
						<Route
							path="workflows"
							element={
								<ProtectedRoute requirePlatformAdmin>
									<Workflows />
								</ProtectedRoute>
							}
						/>
						<Route
							path="workflows/:workflowName/execute"
							element={
								<ProtectedRoute requirePlatformAdmin>
									<ExecuteWorkflow />
								</ProtectedRoute>
							}
						/>

						{/* Forms - PlatformAdmin or OrgUser */}
						<Route
							path="forms"
							element={
								<ProtectedRoute requireOrgUser>
									<Forms />
								</ProtectedRoute>
							}
						/>
						<Route
							path="execute/:formId"
							element={
								<ProtectedRoute requireOrgUser>
									<RunForm />
								</ProtectedRoute>
							}
						/>

						{/* Form Builder - PlatformAdmin only */}
						<Route
							path="forms/new"
							element={
								<ProtectedRoute requirePlatformAdmin>
									<FormBuilder />
								</ProtectedRoute>
							}
						/>
						<Route
							path="forms/:formId/edit"
							element={
								<ProtectedRoute requirePlatformAdmin>
									<FormBuilder />
								</ProtectedRoute>
							}
						/>

						{/* History - PlatformAdmin or OrgUser */}
						<Route
							path="history"
							element={
								<ProtectedRoute requireOrgUser>
									<ExecutionHistory />
								</ProtectedRoute>
							}
						/>

						{/* Organizations - PlatformAdmin only */}
						<Route
							path="organizations"
							element={
								<ProtectedRoute requirePlatformAdmin>
									<Organizations />
								</ProtectedRoute>
							}
						/>

						{/* Users - PlatformAdmin only */}
						<Route
							path="users"
							element={
								<ProtectedRoute requirePlatformAdmin>
									<Users />
								</ProtectedRoute>
							}
						/>

						{/* Roles - PlatformAdmin only */}
						<Route
							path="roles"
							element={
								<ProtectedRoute requirePlatformAdmin>
									<Roles />
								</ProtectedRoute>
							}
						/>

						{/* Config - PlatformAdmin only */}
						<Route
							path="config"
							element={
								<ProtectedRoute requirePlatformAdmin>
									<Config />
								</ProtectedRoute>
							}
						/>

						{/* OAuth Connections - PlatformAdmin only */}
						<Route
							path="oauth"
							element={
								<ProtectedRoute requirePlatformAdmin>
									<OAuthConnections />
								</ProtectedRoute>
							}
						/>

						{/* Docs - PlatformAdmin only */}
						<Route
							path="docs/*"
							element={
								<ProtectedRoute requirePlatformAdmin>
									<Docs />
								</ProtectedRoute>
							}
						/>

						{/* Scheduled Workflows - PlatformAdmin only */}
						<Route
							path="schedules"
							element={
								<ProtectedRoute requirePlatformAdmin>
									<Schedules />
								</ProtectedRoute>
							}
						/>

						{/* Settings - PlatformAdmin only */}
						<Route
							path="settings"
							element={
								<ProtectedRoute requirePlatformAdmin>
									<Settings />
								</ProtectedRoute>
							}
						/>
						<Route
							path="settings/:tab"
							element={
								<ProtectedRoute requirePlatformAdmin>
									<Settings />
								</ProtectedRoute>
							}
						/>

						{/* System Logs - PlatformAdmin only */}
						<Route
							path="logs"
							element={
								<ProtectedRoute requirePlatformAdmin>
									<SystemLogs />
								</ProtectedRoute>
							}
						/>

						{/* User Settings - All authenticated users */}
						<Route
							path="user-settings"
							element={
								<ProtectedRoute>
									<UserSettings />
								</ProtectedRoute>
							}
						/>
						<Route
							path="user-settings/:tab"
							element={
								<ProtectedRoute>
									<UserSettings />
								</ProtectedRoute>
							}
						/>

						{/* Dev Run - PlatformAdmin only (CLI<->Web workflow execution) */}
						{/* Legacy route - kept for backwards compatibility */}
						<Route
							path="dev/run"
							element={
								<ProtectedRoute requirePlatformAdmin>
									<DevRun />
								</ProtectedRoute>
							}
						/>

						{/* CLI Sessions - PlatformAdmin only */}
						<Route
							path="cli"
							element={
								<ProtectedRoute requirePlatformAdmin>
									<CLI />
								</ProtectedRoute>
							}
						/>
					</Route>

					{/* ContentLayout - Pages without default padding */}
					<Route path="/" element={<ContentLayout />}>
						{/* Workbench (CLI Session Detail) - PlatformAdmin only */}
						<Route
							path="cli/:sessionId"
							element={
								<ProtectedRoute requirePlatformAdmin>
									<Workbench />
								</ProtectedRoute>
							}
						/>
						{/* Execution Details - PlatformAdmin or OrgUser */}
						<Route
							path="history/:executionId"
							element={
								<ProtectedRoute requireOrgUser>
									<ExecutionDetails />
								</ProtectedRoute>
							}
						/>
					</Route>
				</Routes>
			</Suspense>
		</>
	);
}

function App() {
	return (
		<ErrorBoundary>
			<BrowserRouter>
				<AuthProvider>
					<OrgScopeProvider>
						<KeyboardProvider>
							<AppRoutes />
						</KeyboardProvider>
					</OrgScopeProvider>
				</AuthProvider>
			</BrowserRouter>
		</ErrorBoundary>
	);
}

export default App;

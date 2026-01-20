import { lazy, Suspense } from "react";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Layout } from "@/components/layout/Layout";
import { ContentLayout } from "@/components/layout/ContentLayout";
import { ProtectedRoute } from "@/components/ProtectedRoute";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { EditorOverlay } from "@/components/editor/EditorOverlay";
import { UnifiedDock } from "@/components/layout/UnifiedDock";
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
const Agents = lazy(() =>
	import("@/pages/Agents").then((m) => ({ default: m.Agents })),
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
const OAuthCallback = lazy(() =>
	import("@/pages/OAuthCallback").then((m) => ({ default: m.OAuthCallback })),
);
const Integrations = lazy(() =>
	import("@/pages/Integrations").then((m) => ({ default: m.Integrations })),
);
const IntegrationDetail = lazy(() =>
	import("@/pages/IntegrationDetail").then((m) => ({
		default: m.IntegrationDetail,
	})),
);
const Docs = lazy(() =>
	import("@/pages/Docs").then((m) => ({ default: m.Docs })),
);
const Schedules = lazy(() =>
	import("@/pages/Schedules").then((m) => ({ default: m.Schedules })),
);
const Events = lazy(() =>
	import("@/pages/Events").then((m) => ({ default: m.Events })),
);
const Settings = lazy(() =>
	import("@/pages/Settings").then((m) => ({ default: m.Settings })),
);
const UserSettings = lazy(() =>
	import("@/pages/UserSettings").then((m) => ({ default: m.UserSettings })),
);
const SystemLogs = lazy(() => import("@/pages/SystemLogs"));
const DiagnosticsPage = lazy(() =>
	import("@/pages/diagnostics/DiagnosticsPage").then((m) => ({
		default: m.DiagnosticsPage,
	})),
);
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
const MCPCallback = lazy(() =>
	import("@/pages/MCPCallback").then((m) => ({ default: m.MCPCallback })),
);
const CLI = lazy(() => import("@/pages/CLI").then((m) => ({ default: m.CLI })));
const Workbench = lazy(() =>
	import("@/pages/Workbench").then((m) => ({ default: m.Workbench })),
);
const Chat = lazy(() =>
	import("@/pages/Chat").then((m) => ({ default: m.Chat })),
);
const ROIReports = lazy(() =>
	import("@/pages/ROIReports").then((m) => ({
		default: m.ROIReports,
	})),
);
const UsageReports = lazy(() =>
	import("@/pages/UsageReports").then((m) => ({
		default: m.UsageReports,
	})),
);
const DevicePage = lazy(() =>
	import("@/pages/DevicePage").then((m) => ({ default: m.DevicePage })),
);
const Tables = lazy(() =>
	import("@/pages/Tables").then((m) => ({ default: m.Tables })),
);
const TableDetail = lazy(() =>
	import("@/pages/TableDetail").then((m) => ({ default: m.TableDetail })),
);
const Applications = lazy(() =>
	import("@/pages/Applications").then((m) => ({ default: m.Applications })),
);
const AppCodeEditorPage = lazy(() =>
	import("@/pages/AppCodeEditorPage").then((m) => ({
		default: m.AppCodeEditorPage,
	})),
);
const ApplicationRunner = lazy(() =>
	import("@/pages/AppRouter").then((m) => ({
		default: m.AppPublished,
	})),
);
const ApplicationPreview = lazy(() =>
	import("@/pages/AppRouter").then((m) => ({
		default: m.AppPreview,
	})),
);
const EntityManagement = lazy(() =>
	import("@/pages/EntityManagement").then((m) => ({
		default: m.EntityManagement,
	})),
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

			{/* Unified Dock - Shows minimized editor */}
			<UnifiedDock />

			<Suspense fallback={<PageLoader />}>
				<Routes>
					{/* Public routes - no auth required */}
					<Route path="login" element={<Login />} />
					<Route path="setup" element={<Setup />} />
					<Route path="mfa-setup" element={<MFASetup />} />
					<Route
						path="auth/callback/:provider"
						element={<AuthCallback />}
					/>
					<Route path="mcp/callback" element={<MCPCallback />} />

					{/* Device authorization - requires auth, handles redirect internally */}
					<Route path="device" element={<DevicePage />} />

					{/* OAuth Callback - Public (no auth, no layout) */}
					<Route
						path="oauth/callback/:integrationId"
						element={<OAuthCallback />}
					/>

					{/* Application Preview - Full screen for developers */}
					<Route
						path="apps/:applicationId/preview/*"
						element={
							<ProtectedRoute requirePlatformAdmin>
								<ApplicationPreview />
							</ProtectedRoute>
						}
					/>

					{/* Application Runner - Published apps (full screen) */}
					<Route
						path="apps/:applicationId/*"
						element={
							<ProtectedRoute requireOrgUser>
								<ApplicationRunner />
							</ProtectedRoute>
						}
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

						{/* Data Tables - PlatformAdmin only */}
						<Route
							path="tables"
							element={
								<ProtectedRoute requirePlatformAdmin>
									<Tables />
								</ProtectedRoute>
							}
						/>
						<Route
							path="tables/:tableName"
							element={
								<ProtectedRoute requirePlatformAdmin>
									<TableDetail />
								</ProtectedRoute>
							}
						/>

						{/* Applications List & Editor - PlatformAdmin only (with sidebar) */}
						<Route
							path="apps"
							element={
								<ProtectedRoute requirePlatformAdmin>
									<Applications />
								</ProtectedRoute>
							}
						/>
						<Route
							path="apps/new"
							element={
								<ProtectedRoute requirePlatformAdmin>
									<AppCodeEditorPage />
								</ProtectedRoute>
							}
						/>
						<Route
							path="apps/:applicationId/edit/*"
							element={
								<ProtectedRoute requirePlatformAdmin>
									<AppCodeEditorPage />
								</ProtectedRoute>
							}
						/>

						{/* Agents - PlatformAdmin only */}
						<Route
							path="agents"
							element={
								<ProtectedRoute requirePlatformAdmin>
									<Agents />
								</ProtectedRoute>
							}
						/>

						{/* Entity Management - PlatformAdmin only */}
						<Route
							path="dependencies"
							element={
								<ProtectedRoute requirePlatformAdmin>
									<EntityManagement />
								</ProtectedRoute>
							}
						/>

						{/* Integrations - PlatformAdmin only */}
						<Route
							path="integrations"
							element={
								<ProtectedRoute requirePlatformAdmin>
									<Integrations />
								</ProtectedRoute>
							}
						/>
						<Route
							path="integrations/:id"
							element={
								<ProtectedRoute requirePlatformAdmin>
									<IntegrationDetail />
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

						{/* Event Sources - PlatformAdmin only */}
						<Route
							path="event-sources"
							element={
								<ProtectedRoute requirePlatformAdmin>
									<Events />
								</ProtectedRoute>
							}
						/>
						<Route
							path="event-sources/:sourceId"
							element={
								<ProtectedRoute requirePlatformAdmin>
									<Events />
								</ProtectedRoute>
							}
						/>
						<Route
							path="event-sources/:sourceId/events/:eventId"
							element={
								<ProtectedRoute requirePlatformAdmin>
									<Events />
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

						{/* Diagnostics - PlatformAdmin only */}
						<Route
							path="diagnostics"
							element={
								<ProtectedRoute requirePlatformAdmin>
									<DiagnosticsPage />
								</ProtectedRoute>
							}
						/>
						<Route
							path="diagnostics/:tab"
							element={
								<ProtectedRoute requirePlatformAdmin>
									<DiagnosticsPage />
								</ProtectedRoute>
							}
						/>

						{/* Legacy System Logs route - redirect to Diagnostics */}
						<Route
							path="logs"
							element={
								<ProtectedRoute requirePlatformAdmin>
									<SystemLogs />
								</ProtectedRoute>
							}
						/>

						{/* Reports - PlatformAdmin only */}
						<Route
							path="reports/roi"
							element={
								<ProtectedRoute requirePlatformAdmin>
									<ROIReports />
								</ProtectedRoute>
							}
						/>
						<Route
							path="reports/usage"
							element={
								<ProtectedRoute requirePlatformAdmin>
									<UsageReports />
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
						{/* Chat - All authenticated users */}
						<Route
							path="chat"
							element={
								<ProtectedRoute>
									<Chat />
								</ProtectedRoute>
							}
						/>
						<Route
							path="chat/:conversationId"
							element={
								<ProtectedRoute>
									<Chat />
								</ProtectedRoute>
							}
						/>
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

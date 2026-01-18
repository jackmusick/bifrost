/**
 * App Router
 *
 * Universal router for App Builder applications.
 * Renders JsxAppShell for file-based JSX apps.
 *
 * Routes:
 * - /apps/:slug/preview/* - Preview mode (uses draft_version_id)
 * - /apps/:slug/* - Published mode (uses active_version_id)
 */

import { useParams, useNavigate } from "react-router-dom";
import { AlertTriangle, ArrowLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { AppLoadingSkeleton } from "@/components/jsx-app/AppLoadingSkeleton";
import {
	Card,
	CardContent,
	CardDescription,
	CardHeader,
	CardTitle,
} from "@/components/ui/card";
import { useApplication } from "@/hooks/useApplications";
import { JsxAppShell } from "@/components/jsx-app/JsxAppShell";

interface AppRouterProps {
	/** Whether to render in preview mode (uses draft version) */
	preview?: boolean;
}

export function AppRouter({ preview = false }: AppRouterProps) {
	const { applicationId: slugParam } = useParams();
	const navigate = useNavigate();

	// Fetch application metadata
	const {
		data: application,
		isLoading,
		error,
	} = useApplication(slugParam);

	// Loading state
	if (isLoading) {
		return <AppLoadingSkeleton message="Loading application..." />;
	}

	// Error state
	if (error) {
		return (
			<div className="min-h-screen flex items-center justify-center p-4">
				<Card className="max-w-md w-full">
					<CardHeader>
						<div className="flex items-center gap-2 text-destructive">
							<AlertTriangle className="h-5 w-5" />
							<CardTitle>Application Error</CardTitle>
						</div>
						<CardDescription>
							{error instanceof Error
								? error.message
								: "Failed to load application"}
						</CardDescription>
					</CardHeader>
					<CardContent>
						<Button
							variant="outline"
							onClick={() => navigate("/apps")}
						>
							<ArrowLeft className="mr-2 h-4 w-4" />
							Back to Applications
						</Button>
					</CardContent>
				</Card>
			</div>
		);
	}

	// No application found
	if (!application) {
		return (
			<div className="min-h-screen flex items-center justify-center p-4">
				<Card className="max-w-md w-full">
					<CardHeader>
						<div className="flex items-center gap-2 text-muted-foreground">
							<AlertTriangle className="h-5 w-5" />
							<CardTitle>Application Not Found</CardTitle>
						</div>
						<CardDescription>
							The requested application does not exist or you
							don't have access to it.
						</CardDescription>
					</CardHeader>
					<CardContent>
						<Button
							variant="outline"
							onClick={() => navigate("/apps")}
						>
							<ArrowLeft className="mr-2 h-4 w-4" />
							Back to Applications
						</Button>
					</CardContent>
				</Card>
			</div>
		);
	}

	// Get the appropriate version ID
	const versionId = preview
		? application.draft_version_id
		: application.active_version_id;

	// Handle missing version
	if (!versionId) {
		return (
			<div className="min-h-screen flex items-center justify-center p-4">
				<Card className="max-w-md w-full">
					<CardHeader>
						<div className="flex items-center gap-2 text-muted-foreground">
							<AlertTriangle className="h-5 w-5" />
							<CardTitle>
								{preview ? "No Draft Version" : "Not Published"}
							</CardTitle>
						</div>
						<CardDescription>
							{preview
								? "No draft version is available for this application."
								: "This application has not been published yet."}
						</CardDescription>
					</CardHeader>
					<CardContent className="flex gap-2">
						<Button
							variant="outline"
							onClick={() => navigate("/apps")}
						>
							<ArrowLeft className="mr-2 h-4 w-4" />
							Back
						</Button>
						<Button
							onClick={() =>
								navigate(`/apps/${slugParam}/code`)
							}
						>
							Open Editor
						</Button>
					</CardContent>
				</Card>
			</div>
		);
	}

	// Render with preview banner if in preview mode
	if (preview) {
		return (
			<div className="h-full flex flex-col bg-background overflow-hidden">
				{/* Preview Banner */}
				<div className="z-50 bg-amber-500 text-amber-950 px-4 py-2 text-center text-sm font-medium shrink-0">
					Preview Mode - This is the draft version
					<Button
						variant="link"
						className="ml-2 text-amber-950 underline hover:no-underline p-0 h-auto"
						onClick={() => navigate(`/apps/${slugParam}/code`)}
					>
						Back to Editor
					</Button>
				</div>
				<div className="flex-1 overflow-auto">
					<JsxAppShell
						appId={application.id}
						appSlug={application.slug}
						versionId={versionId}
						isPreview
					/>
				</div>
			</div>
		);
	}

	// Production mode
	return (
		<JsxAppShell
			appId={application.id}
			appSlug={application.slug}
			versionId={versionId}
		/>
	);
}

/**
 * Published app view
 */
export function AppPublished() {
	return <AppRouter preview={false} />;
}

/**
 * Preview app view (draft version)
 */
export function AppPreview() {
	return <AppRouter preview />;
}

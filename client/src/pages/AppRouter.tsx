/**
 * App Router
 *
 * Universal router for App Builder applications.
 * Renders JsxAppShell for file-based JSX apps with AppLayout wrapper.
 *
 * Routes:
 * - /apps/:slug/preview/* - Preview mode (uses draft files)
 * - /apps/:slug/* - Published mode (uses live files)
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
import { useAuth } from "@/contexts/AuthContext";
import { JsxAppShell } from "@/components/jsx-app/JsxAppShell";
import { AppLayout } from "@/components/layout/AppLayout";

interface AppRouterProps {
	/** Whether to render in preview mode (uses draft version) */
	preview?: boolean;
}

export function AppRouter({ preview = false }: AppRouterProps) {
	const { applicationId: slugParam } = useParams();
	const navigate = useNavigate();
	const { hasRole } = useAuth();
	const isEmbed = hasRole("EmbedUser");

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

	// Handle not published (only for non-preview mode)
	if (!preview && !application.is_published) {
		return (
			<div className="min-h-screen flex items-center justify-center p-4">
				<Card className="max-w-md w-full">
					<CardHeader>
						<div className="flex items-center gap-2 text-muted-foreground">
							<AlertTriangle className="h-5 w-5" />
							<CardTitle>Not Published</CardTitle>
						</div>
						<CardDescription>
							This application has not been published yet.
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
								navigate(`/apps/${slugParam}/edit`)
							}
						>
							Open Editor
						</Button>
					</CardContent>
				</Card>
			</div>
		);
	}

	const shell = (
		<JsxAppShell
			appId={application.id}
			appSlug={application.slug}
			isPreview={preview}
		/>
	);

	if (isEmbed) {
		return <div className="h-screen overflow-auto">{shell}</div>;
	}

	return (
		<AppLayout appName={application.name} isPreview={preview}>
			{shell}
		</AppLayout>
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

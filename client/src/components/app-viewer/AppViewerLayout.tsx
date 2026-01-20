// client/src/components/app-viewer/AppViewerLayout.tsx

import { AppWindow, Minus, PictureInPicture2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { JsxAppShell } from "@/components/jsx-app/JsxAppShell";
import { useAppViewer } from "@/hooks/useAppViewer";

/**
 * App viewer layout with header bar and controls.
 * Rendered inside WindowOverlay when maximized.
 */
export function AppViewerLayout() {
	const {
		appId,
		appSlug,
		appName,
		versionId,
		isPreview,
		internalRoute,
		minimize,
		restoreToWindowed,
		closeApp,
	} = useAppViewer();

	if (!appId || !appSlug || !versionId) {
		return null;
	}

	return (
		<div className="flex h-screen w-screen flex-col overflow-hidden bg-background">
			{/* Header bar */}
			<div className="flex h-10 items-center justify-between border-b bg-muted/30 px-3 shrink-0">
				{/* Left side: App info */}
				<div className="flex items-center gap-2 min-w-0">
					<AppWindow className="h-4 w-4 text-muted-foreground shrink-0" />
					<span className="text-sm font-medium truncate">{appName}</span>
					<span className="text-sm text-muted-foreground truncate">
						{internalRoute}
					</span>
					{isPreview && (
						<Badge
							variant="outline"
							className="bg-amber-500/10 text-amber-600 border-amber-500/30 shrink-0"
						>
							Preview
						</Badge>
					)}
				</div>

				{/* Right side: Controls */}
				<div className="flex gap-1 shrink-0">
					<Button
						variant="ghost"
						size="icon"
						className="h-6 w-6"
						onClick={minimize}
						title="Minimize"
					>
						<Minus className="h-3 w-3" />
					</Button>
					<Button
						variant="ghost"
						size="icon"
						className="h-6 w-6"
						onClick={restoreToWindowed}
						title="Restore to window"
					>
						<PictureInPicture2 className="h-3 w-3" />
					</Button>
					<Button
						variant="ghost"
						size="icon"
						className="h-6 w-6"
						onClick={closeApp}
						title="Close"
					>
						<X className="h-3 w-3" />
					</Button>
				</div>
			</div>

			{/* App content */}
			<div className="flex-1 overflow-auto">
				<JsxAppShell
					appId={appId}
					appSlug={appSlug}
					versionId={versionId}
					isPreview={isPreview}
				/>
			</div>
		</div>
	);
}

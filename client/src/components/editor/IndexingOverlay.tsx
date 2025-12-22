import { useEditorStore } from "@/stores/editorStore";
import { Loader2 } from "lucide-react";

/**
 * Overlay that blocks the editor during ID injection/indexing operations.
 *
 * When saving a Python file for the first time, the server may inject
 * workflow/data_provider/tool IDs into decorators. During this operation,
 * the editor is blocked to prevent the user from typing while the content
 * is being modified server-side.
 *
 * The overlay displays:
 * - A semi-transparent background
 * - A spinner with a friendly message
 * - The message is customizable via the store
 */
export function IndexingOverlay() {
	const isIndexing = useEditorStore((state) => state.isIndexing);
	const indexingMessage = useEditorStore((state) => state.indexingMessage);

	if (!isIndexing) {
		return null;
	}

	return (
		<div className="absolute inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur-sm">
			<div className="flex flex-col items-center gap-3 p-6 rounded-lg bg-card border shadow-lg">
				<Loader2 className="h-8 w-8 animate-spin text-primary" />
				<div className="text-center">
					<p className="text-sm font-medium">
						{indexingMessage || "Indexing workflow..."}
					</p>
					<p className="text-xs text-muted-foreground mt-1">
						This only happens once per file
					</p>
				</div>
			</div>
		</div>
	);
}

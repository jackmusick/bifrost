import { useEffect, useRef, useState } from "react";
import { DiffEditor, type DiffOnMount } from "@monaco-editor/react";
import { useTheme } from "@/contexts/ThemeContext";
import type * as Monaco from "monaco-editor";
import { Button } from "@/components/ui/button";
import { Check } from "lucide-react";
import {
	AlertDialog,
	AlertDialogAction,
	AlertDialogCancel,
	AlertDialogContent,
	AlertDialogDescription,
	AlertDialogFooter,
	AlertDialogHeader,
	AlertDialogTitle,
} from "@/components/ui/alert-dialog";

interface ConflictInfo {
	current_content: string;
	incoming_content: string;
	current_etag: string;
	message: string;
}

interface ConflictDiffViewProps {
	conflict: ConflictInfo;
	filePath: string;
	onResolve: (choice: "current" | "incoming") => Promise<void>;
}

export function ConflictDiffView({
	conflict,
	filePath,
	onResolve,
}: ConflictDiffViewProps) {
	const { theme } = useTheme();
	const editorRef = useRef<Monaco.editor.IStandaloneDiffEditor | null>(null);
	const [showConfirm, setShowConfirm] = useState(false);
	const [choice, setChoice] = useState<"current" | "incoming" | null>(null);

	const handleMount: DiffOnMount = (editor) => {
		editorRef.current = editor;
	};

	useEffect(() => {
		return () => {
			editorRef.current?.dispose();
		};
	}, []);

	const confirmChoice = (selectedChoice: "current" | "incoming") => {
		setChoice(selectedChoice);
		setShowConfirm(true);
	};

	const handleConfirm = async () => {
		if (!choice) return;

		await onResolve(choice);
		setShowConfirm(false);
	};

	return (
		<>
			<div className="flex flex-col h-full bg-background rounded-lg border">
				<div className="flex items-center justify-between p-4 border-b">
					<div>
						<h3 className="text-lg font-semibold">
							Resolve Conflict
						</h3>
						<p className="text-sm text-muted-foreground">
							{filePath}
						</p>
						<p className="text-sm text-yellow-600 dark:text-yellow-500 mt-1">
							{conflict.message}
						</p>
					</div>
					<div className="flex gap-2">
						<Button
							variant="outline"
							onClick={() => confirmChoice("current")}
						>
							Keep Current (Server)
						</Button>
						<Button
							variant="outline"
							onClick={() => confirmChoice("incoming")}
						>
							Use Incoming (Local)
						</Button>
					</div>
				</div>

				<div className="flex-1 min-h-0">
					<DiffEditor
						height="100%"
						language={
							filePath.endsWith(".py")
								? "python"
								: filePath.endsWith(".json")
									? "json"
									: "plaintext"
						}
						theme={theme === "dark" ? "vs-dark" : "light"}
						original={conflict.current_content}
						modified={conflict.incoming_content}
						onMount={handleMount}
						options={{
							readOnly: true,
							minimap: { enabled: false },
							scrollBeyondLastLine: false,
						}}
					/>
				</div>
			</div>

			<AlertDialog open={showConfirm} onOpenChange={setShowConfirm}>
				<AlertDialogContent>
					<AlertDialogHeader>
						<AlertDialogTitle>Confirm Resolution</AlertDialogTitle>
						<AlertDialogDescription>
							Are you sure you want to{" "}
							{choice === "current"
								? "keep the server version"
								: "use your local version"}
							?
							<br />
							<br />
							This will overwrite the file on the server with the
							selected version.
						</AlertDialogDescription>
					</AlertDialogHeader>
					<AlertDialogFooter>
						<AlertDialogCancel>Cancel</AlertDialogCancel>
						<AlertDialogAction onClick={handleConfirm}>
							<Check className="mr-2 h-4 w-4" />
							Confirm
						</AlertDialogAction>
					</AlertDialogFooter>
				</AlertDialogContent>
			</AlertDialog>
		</>
	);
}

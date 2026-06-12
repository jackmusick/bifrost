import { useCallback, useState } from "react";
import {
	File,
	Folder,
	FilePlus,
	FolderPlus,
	Loader2,
	RefreshCw,
	ShieldCheck,
	AlertTriangle,
	XCircle,
	CheckCircle2,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { fileService } from "@/services/fileService";
import { WorkflowIdConflictDialog } from "./WorkflowIdConflictDialog";
import { runPreflight, registerWorkflow } from "@/hooks/useWorkflows";
import { useReloadWorkflowFile } from "@/hooks/useWorkflows";
import { useFileTreeActions } from "@/hooks/useFileTreeActions";
import { FileTreeNode } from "./FileTreeNode";
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
import {
	Dialog,
	DialogContent,
	DialogHeader,
	DialogTitle,
} from "@/components/ui/dialog";

type PreflightIssue = {
	level: string;
	category: string;
	detail: string;
	path?: string | null;
};

type PreflightResult = {
	valid: boolean;
	issues: PreflightIssue[];
	warnings: PreflightIssue[];
};

/**
 * File tree component with hierarchical navigation
 */
export function FileTree() {
	const {
		// File tree data
		files,
		isLoading,
		isFolderLoading,
		isFolderExpanded,
		openFile,

		// Create actions
		creatingItem,
		creatingInFolder,
		newItemName,
		setNewItemName,
		inputRef,
		handleCreateFile,
		handleCreateFolder,
		handleCancelNewItem: _handleCancelNewItem,
		handleNewItemKeyDown,
		handleInputMouseDown,

		// File/folder actions
		handleFileClick,
		handleFolderToggle,
		handleRefresh,

		// Delete actions
		fileToDelete,
		setFileToDelete,
		handleDelete,
		handleConfirmDelete,

		// Rename actions
		renamingFile,
		renameValue,
		setRenameValue,
		renameInputRef,
		handleRename,
		handleSaveRename: _handleSaveRename,
		handleRenameKeyDown,
		handleRenameInputMouseDown,

		// Drag and drop
		dragOverFolder,
		handleDragStart,
		handleDragOver,
		handleDragLeave,
		handleDrop,

		// Processing state
		isProcessing,

		// Upload conflicts
		uploadConflict,
		uploadWorkflowConflicts,
		setUploadWorkflowConflicts,
	} = useFileTreeActions();

	// Preflight state
	const [preflightLoading, setPreflightLoading] = useState(false);
	const [preflightResult, setPreflightResult] =
		useState<PreflightResult | null>(null);
	const [preflightRegistering, setPreflightRegistering] = useState<
		string | null
	>(null);
	const reloadWorkflows = useReloadWorkflowFile();

	const handlePreflight = useCallback(async () => {
		setPreflightLoading(true);
		try {
			const result = await runPreflight();
			if (
				result.valid &&
				result.warnings.length === 0 &&
				result.issues.length === 0
			) {
				toast.success("All checks passed");
			} else {
				setPreflightResult(result);
			}
		} catch (err) {
			toast.error("Preflight failed", {
				description:
					err instanceof Error ? err.message : String(err),
			});
		} finally {
			setPreflightLoading(false);
		}
	}, []);

	const handlePreflightRegister = useCallback(
		async (path: string, functionName: string) => {
			setPreflightRegistering(functionName);
			try {
				await registerWorkflow(path, functionName);
				toast.success(`Registered ${functionName}`);
				await reloadWorkflows.mutate();
				// Re-run preflight to refresh results
				const result = await runPreflight();
				setPreflightResult(result);
			} catch (err) {
				toast.error("Failed to register", {
					description:
						err instanceof Error ? err.message : String(err),
				});
			} finally {
				setPreflightRegistering(null);
			}
		},
		[reloadWorkflows],
	);

	return (
		<div className="flex h-full flex-col relative">
			{/* Loading overlay */}
			{isProcessing && (
				<div className="absolute inset-0 bg-background/80 backdrop-blur-sm z-50 flex items-center justify-center">
					<div className="flex flex-col items-center gap-2">
						<Loader2 className="h-8 w-8 animate-spin text-primary" />
						<p className="text-sm text-muted-foreground">
							Processing...
						</p>
					</div>
				</div>
			)}

			{/* Toolbar */}
			<div className="flex items-center gap-1 border-b p-2">
				<Button
					variant="ghost"
					size="sm"
					onClick={() => handleCreateFile()}
					title="New File"
					className="h-7 px-2"
				>
					<FilePlus className="h-4 w-4" />
				</Button>
				<Button
					variant="ghost"
					size="sm"
					onClick={() => handleCreateFolder()}
					title="New Folder"
					className="h-7 px-2"
				>
					<FolderPlus className="h-4 w-4" />
				</Button>
				<Button
					variant="ghost"
					size="sm"
					onClick={handleRefresh}
					title="Refresh"
					className="h-7 px-2"
				>
					<RefreshCw className="h-4 w-4" />
				</Button>
				<Button
					variant="ghost"
					size="sm"
					onClick={handlePreflight}
					disabled={preflightLoading}
					title="Preflight Check"
					className="h-7 px-2"
				>
					{preflightLoading ? (
						<Loader2 className="h-4 w-4 animate-spin" />
					) : (
						<ShieldCheck className="h-4 w-4" />
					)}
				</Button>
			</div>

			{/* File list */}
			<div
				className={cn(
					"flex-1 overflow-auto",
					dragOverFolder === "" &&
						"bg-primary/10 outline outline-2 outline-primary outline-dashed",
				)}
				onDragOver={(e) => handleDragOver(e)}
				onDragLeave={handleDragLeave}
				onDrop={(e) => handleDrop(e)}
			>
				{isLoading && files.length === 0 && !creatingItem ? (
					<div className="flex h-full items-center justify-center">
						<div className="text-sm text-muted-foreground">
							Loading files...
						</div>
					</div>
				) : files.length === 0 && !creatingItem ? (
					<div className="flex h-full items-center justify-center p-4">
						<div className="text-center text-sm text-muted-foreground">
							<p>No files found</p>
							<p className="mt-2 text-xs">
								Use the toolbar to create files and folders
							</p>
						</div>
					</div>
				) : (
					<div className="space-y-1 p-2">
						{/* Inline new item editor */}
						{creatingItem && !creatingInFolder && (
							<div className="flex items-center gap-2 rounded-md px-2 py-1 bg-muted/50">
								<div className="w-4" />
								{isProcessing ? (
									<Loader2 className="h-4 w-4 flex-shrink-0 animate-spin text-primary" />
								) : creatingItem === "folder" ? (
									<Folder className="h-4 w-4 flex-shrink-0 text-primary" />
								) : (
									<File className="h-4 w-4 flex-shrink-0 text-muted-foreground" />
								)}
								<input
									ref={inputRef}
									type="text"
									value={newItemName}
									onChange={(e) =>
										setNewItemName(e.target.value)
									}
									onKeyDown={handleNewItemKeyDown}
									onMouseDown={handleInputMouseDown}
									placeholder={
										creatingItem === "folder"
											? "Folder name"
											: "File name"
									}
									disabled={isProcessing}
									className="flex-1 bg-transparent text-sm outline-none disabled:opacity-50 disabled:cursor-not-allowed"
								/>
							</div>
						)}

						{/* Existing files */}
						{files.map((file) => (
							<FileTreeNode
								key={file.path}
								file={file}
								onFileClick={handleFileClick}
								onFolderToggle={handleFolderToggle}
								onDelete={handleDelete}
								onRename={handleRename}
								onCreateFile={handleCreateFile}
								onCreateFolder={handleCreateFolder}
								isExpanded={isFolderExpanded(file.path)}
								isLoadingContents={isFolderLoading(file.path)}
								isSelected={openFile?.path === file.path}
								onDragStart={handleDragStart}
								onDragOver={handleDragOver}
								onDragLeave={handleDragLeave}
								onDrop={handleDrop}
								isDragOver={dragOverFolder === file.path}
								creatingItem={creatingItem}
								creatingInFolder={creatingInFolder}
								newItemName={newItemName}
								setNewItemName={setNewItemName}
								inputRef={inputRef}
								handleNewItemKeyDown={handleNewItemKeyDown}
								handleInputMouseDown={handleInputMouseDown}
								handleCancelNewItem={_handleCancelNewItem}
								renamingFile={renamingFile}
								renameValue={renameValue}
								setRenameValue={setRenameValue}
								renameInputRef={renameInputRef}
								handleRenameKeyDown={handleRenameKeyDown}
								handleRenameInputMouseDown={handleRenameInputMouseDown}
								isProcessing={isProcessing}
							/>
						))}
					</div>
				)}
			</div>

			{/* Delete Confirmation Dialog */}
			<AlertDialog
				open={!!fileToDelete}
				onOpenChange={(open) => !open && setFileToDelete(null)}
			>
				<AlertDialogContent>
					<AlertDialogHeader>
						<AlertDialogTitle>
							Delete{" "}
							{fileToDelete?.type === "folder"
								? "Folder"
								: "File"}
						</AlertDialogTitle>
						<AlertDialogDescription>
							Are you sure you want to delete{" "}
							<strong>{fileToDelete?.name}</strong>?
							{fileToDelete?.type === "folder" &&
								" This will delete all contents inside the folder."}{" "}
							This action cannot be undone.
						</AlertDialogDescription>
					</AlertDialogHeader>
					<AlertDialogFooter>
						<AlertDialogCancel>Cancel</AlertDialogCancel>
						<AlertDialogAction
							onClick={handleConfirmDelete}
							className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
						>
							Delete
						</AlertDialogAction>
					</AlertDialogFooter>
				</AlertDialogContent>
			</AlertDialog>

			{/* Upload Conflict Dialog */}
			<AlertDialog
				open={!!uploadConflict}
				onOpenChange={(open) => {
					if (!open && uploadConflict) {
						uploadConflict.onCancel();
					}
				}}
			>
				<AlertDialogContent>
					<AlertDialogHeader>
						<AlertDialogTitle>
							Replace existing files?
						</AlertDialogTitle>
						<AlertDialogDescription>
							{uploadConflict?.count === 1
								? "1 file already exists and will be replaced."
								: `${uploadConflict?.count} files already exist and will be replaced.`}
						</AlertDialogDescription>
					</AlertDialogHeader>
					<AlertDialogFooter>
						<AlertDialogCancel onClick={uploadConflict?.onCancel}>
							Cancel
						</AlertDialogCancel>
						<AlertDialogAction
							onClick={uploadConflict?.onReplaceAll}
						>
							Replace All
						</AlertDialogAction>
					</AlertDialogFooter>
				</AlertDialogContent>
			</AlertDialog>

			{/* Workflow ID Conflict Dialog for Uploads */}
			<WorkflowIdConflictDialog
				conflicts={uploadWorkflowConflicts?.conflicts ?? []}
				open={uploadWorkflowConflicts !== null}
				onUseExisting={async () => {
					if (!uploadWorkflowConflicts) return;

					try {
						for (const file of uploadWorkflowConflicts.files) {
							await fileService.writeFile(
								file.filePath,
								file.content,
								file.encoding,
								undefined,
								true,
								file.conflictIds,
							);
						}
						toast.success("Existing workflow IDs preserved");
					} catch (error) {
						console.error("Failed to apply existing IDs:", error);
						toast.error("Failed to preserve workflow IDs");
					}

					setUploadWorkflowConflicts(null);
				}}
				onGenerateNew={() => {
					toast.info("New workflow IDs were generated");
					setUploadWorkflowConflicts(null);
				}}
				onCancel={() => {
					setUploadWorkflowConflicts(null);
				}}
			/>

			{/* Preflight Results Dialog */}
			<Dialog
				open={preflightResult !== null}
				onOpenChange={(open) => {
					if (!open) setPreflightResult(null);
				}}
			>
				<DialogContent className="max-w-lg">
					<DialogHeader>
						<DialogTitle className="flex items-center gap-2">
							{preflightResult?.valid ? (
								<CheckCircle2 className="h-5 w-5 text-green-500" />
							) : (
								<XCircle className="h-5 w-5 text-destructive" />
							)}
							Preflight Results
						</DialogTitle>
					</DialogHeader>
					<div className="max-h-80 overflow-y-auto space-y-2">
						{preflightResult?.issues.map((issue, idx) => (
							<div
								key={`issue-${idx}`}
								className="flex items-start gap-2 rounded-md bg-destructive/5 ring-1 ring-destructive/30 p-2 text-sm"
							>
								<XCircle className="h-4 w-4 mt-0.5 flex-shrink-0 text-destructive" />
								<div className="flex-1 min-w-0">
									{issue.path && (
										<div className="font-mono text-xs text-muted-foreground truncate">
											{issue.path}
										</div>
									)}
									<div>{issue.detail}</div>
								</div>
							</div>
						))}
						{preflightResult?.warnings.map((warning, idx) => {
							const fnMatch =
								warning.category === "unregistered_function"
									? warning.detail.match(
											/function '(\w+)'/,
										)
									: null;
							const fnName = fnMatch?.[1];

							return (
								<div
									key={`warn-${idx}`}
									className="flex items-start gap-2 rounded-md bg-amber-500/5 ring-1 ring-amber-500/30 p-2 text-sm"
								>
									<AlertTriangle className="h-4 w-4 mt-0.5 flex-shrink-0 text-amber-500" />
									<div className="flex-1 min-w-0">
										{warning.path && (
											<div className="font-mono text-xs text-muted-foreground truncate">
												{warning.path}
											</div>
										)}
										<div>{warning.detail}</div>
									</div>
									{fnName && warning.path && (
										<Button
											variant="outline"
											size="sm"
											className="h-7 text-xs flex-shrink-0"
											disabled={
												preflightRegistering ===
												fnName
											}
											onClick={() =>
												handlePreflightRegister(
													warning.path!,
													fnName,
												)
											}
										>
											{preflightRegistering ===
											fnName ? (
												<Loader2 className="h-3 w-3 animate-spin mr-1" />
											) : null}
											Register
										</Button>
									)}
								</div>
							);
						})}
						{preflightResult?.issues.length === 0 &&
							preflightResult?.warnings.length === 0 && (
								<div className="text-center text-sm text-muted-foreground py-4">
									All checks passed
								</div>
							)}
					</div>
				</DialogContent>
			</Dialog>
		</div>
	);
}

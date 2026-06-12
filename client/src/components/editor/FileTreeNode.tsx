import {
	ChevronRight,
	ChevronDown,
	File,
	Folder,
	Loader2,
	Workflow,
	FileText,
	AppWindow,
	Bot,
	FileCode,
	FileJson,
	FileImage,
	FileSpreadsheet,
	FileArchive,
	FileTerminal,
	Settings,
	FileType,
	Braces,
	type LucideIcon,
} from "lucide-react";
import type { FileTreeNode as FileTreeNodeType } from "@/hooks/useFileTree";
import type { FileMetadata } from "@/services/fileService";
import type { CreatingItemType } from "@/hooks/useFileTreeActions";
import { cn } from "@/lib/utils";
import { FileTreeContextMenu } from "./FileTreeContextMenu";

/**
 * Platform entity type icons and colors (highest priority)
 */
const ENTITY_TYPE_ICONS: Record<
	string,
	{ icon: LucideIcon; className: string }
> = {
	workflow: { icon: Workflow, className: "text-blue-500" },
	form: { icon: FileText, className: "text-green-500" },
	app: { icon: AppWindow, className: "text-purple-500" },
	agent: { icon: Bot, className: "text-orange-500" },
};

/**
 * File extension icons and colors (fallback when no entity type)
 */
const EXTENSION_ICONS: Record<string, { icon: LucideIcon; className: string }> =
	{
		// Code files
		py: { icon: FileCode, className: "text-yellow-500" },
		js: { icon: Braces, className: "text-yellow-400" },
		jsx: { icon: Braces, className: "text-cyan-400" },
		ts: { icon: Braces, className: "text-blue-400" },
		tsx: { icon: Braces, className: "text-blue-400" },
		html: { icon: FileCode, className: "text-orange-500" },
		css: { icon: FileCode, className: "text-blue-500" },
		scss: { icon: FileCode, className: "text-pink-400" },
		// Data files
		json: { icon: FileJson, className: "text-yellow-500" },
		yaml: { icon: FileJson, className: "text-red-400" },
		yml: { icon: FileJson, className: "text-red-400" },
		xml: { icon: FileCode, className: "text-orange-400" },
		csv: { icon: FileSpreadsheet, className: "text-green-500" },
		// Text/Docs
		txt: { icon: FileType, className: "text-gray-400" },
		md: { icon: FileText, className: "text-gray-500" },
		// Shell/Terminal
		sh: { icon: FileTerminal, className: "text-green-400" },
		bash: { icon: FileTerminal, className: "text-green-400" },
		zsh: { icon: FileTerminal, className: "text-green-400" },
		// Images
		png: { icon: FileImage, className: "text-purple-400" },
		jpg: { icon: FileImage, className: "text-purple-400" },
		jpeg: { icon: FileImage, className: "text-purple-400" },
		gif: { icon: FileImage, className: "text-purple-400" },
		svg: { icon: FileImage, className: "text-orange-400" },
		webp: { icon: FileImage, className: "text-purple-400" },
		ico: { icon: FileImage, className: "text-purple-400" },
		// Archives
		zip: { icon: FileArchive, className: "text-amber-500" },
		tar: { icon: FileArchive, className: "text-amber-500" },
		gz: { icon: FileArchive, className: "text-amber-500" },
		// Config
		toml: { icon: Settings, className: "text-gray-400" },
		ini: { icon: Settings, className: "text-gray-400" },
		env: { icon: Settings, className: "text-yellow-600" },
		gitignore: { icon: Settings, className: "text-gray-500" },
	};

/**
 * Get the appropriate icon and styling for a file based on its entity type or extension
 */
export function getFileIcon(
	entityType: string | null | undefined,
	extension: string | null | undefined,
): {
	icon: LucideIcon;
	className: string;
} {
	// Platform entity types take priority
	if (entityType && ENTITY_TYPE_ICONS[entityType]) {
		return ENTITY_TYPE_ICONS[entityType];
	}
	// Fall back to extension-based icons
	if (extension) {
		const ext = extension.toLowerCase();
		if (EXTENSION_ICONS[ext]) {
			return EXTENSION_ICONS[ext];
		}
	}
	// Default file icon
	return { icon: File, className: "text-muted-foreground" };
}

export interface FileTreeNodeProps {
	file: FileTreeNodeType;
	onFileClick: (file: FileMetadata) => void;
	onFolderToggle: (folder: FileMetadata) => void;
	onDelete: (file: FileMetadata) => void;
	onRename: (file: FileMetadata) => void;
	onCreateFile: (folderPath?: string) => void;
	onCreateFolder: (folderPath?: string) => void;
	isExpanded: boolean;
	isLoadingContents: boolean;
	isSelected: boolean;
	onDragStart: (e: React.DragEvent, file: FileMetadata) => void;
	onDragOver: (e: React.DragEvent, targetFolder?: string) => void;
	onDragLeave: () => void;
	onDrop: (e: React.DragEvent, targetFolder?: string) => void;
	isDragOver: boolean;
	creatingItem: CreatingItemType;
	creatingInFolder: string | null;
	newItemName: string;
	setNewItemName: (name: string) => void;
	inputRef: React.RefObject<HTMLInputElement | null>;
	handleNewItemKeyDown: (e: React.KeyboardEvent<HTMLInputElement>) => void;
	handleInputMouseDown: (e: React.MouseEvent) => void;
	handleCancelNewItem: () => void;
	renamingFile: FileMetadata | null;
	renameValue: string;
	setRenameValue: (name: string) => void;
	renameInputRef: React.RefObject<HTMLInputElement | null>;
	handleRenameKeyDown: (e: React.KeyboardEvent<HTMLInputElement>) => void;
	handleRenameInputMouseDown: (e: React.MouseEvent) => void;
	isProcessing: boolean;
}

export function FileTreeNode({
	file,
	onFileClick,
	onFolderToggle,
	onDelete,
	onRename,
	onCreateFile,
	onCreateFolder,
	isExpanded,
	isLoadingContents,
	isSelected,
	onDragStart,
	onDragOver,
	onDragLeave,
	onDrop,
	isDragOver,
	creatingItem,
	creatingInFolder,
	newItemName,
	setNewItemName,
	inputRef,
	handleNewItemKeyDown,
	handleInputMouseDown,
	handleCancelNewItem: _handleCancelNewItem,
	renamingFile,
	renameValue,
	setRenameValue,
	renameInputRef,
	handleRenameKeyDown,
	handleRenameInputMouseDown,
	isProcessing,
}: FileTreeNodeProps) {
	const isFolder = file.type === "folder";
	const level = file.level;
	const isRenaming = renamingFile?.path === file.path;

	return (
		<div>
			{isRenaming ? (
				// Inline rename editor
				<div
					className="flex items-center gap-2 rounded-md px-2 py-1 bg-muted/50"
					style={{ paddingLeft: `${level * 12 + 8}px` }}
				>
					{isFolder ? (
						<>
							{isLoadingContents ? (
								<Loader2 className="h-4 w-4 flex-shrink-0 animate-spin text-muted-foreground" />
							) : isExpanded ? (
								<ChevronDown className="h-4 w-4 flex-shrink-0 text-muted-foreground" />
							) : (
								<ChevronRight className="h-4 w-4 flex-shrink-0 text-muted-foreground" />
							)}
							<Folder className="h-4 w-4 flex-shrink-0 text-primary" />
						</>
					) : (
						(() => {
							const { icon: FileIcon, className } = getFileIcon(
								file.entity_type,
								file.extension,
							);
							return (
								<>
									<div className="w-4" />
									<FileIcon
										className={cn(
											"h-4 w-4 flex-shrink-0",
											className,
										)}
									/>
								</>
							);
						})()
					)}
					<input
						ref={renameInputRef}
						type="text"
						value={renameValue}
						onChange={(e) => setRenameValue(e.target.value)}
						onKeyDown={handleRenameKeyDown}
						onMouseDown={handleRenameInputMouseDown}
						disabled={isProcessing}
						className="flex-1 bg-transparent text-sm outline-none disabled:opacity-50 disabled:cursor-not-allowed"
					/>
				</div>
			) : (
				<FileTreeContextMenu
					file={file}
					isFolder={isFolder}
					onCreateFile={onCreateFile}
					onCreateFolder={onCreateFolder}
					onRename={onRename}
					onDelete={onDelete}
				>
					<button
						draggable
						onClick={() => {
							if (isFolder) {
								onFolderToggle(file);
							} else {
								onFileClick(file);
							}
						}}
						onDragStart={(e) => onDragStart(e, file)}
						onDragOver={(e) => {
							if (isFolder) {
								e.stopPropagation();
								onDragOver(e, file.path);
							}
						}}
						onDragLeave={onDragLeave}
						onDrop={(e) => {
							if (isFolder) {
								e.stopPropagation();
								onDrop(e, file.path);
							}
						}}
						className={cn(
							"flex w-full items-center gap-2 rounded-md px-2 py-1 text-left text-sm transition-colors outline-none",
							isSelected && !isDragOver
								? "bg-accent text-accent-foreground"
								: "",
							!isDragOver && !isSelected ? "hover:bg-muted" : "",
							isDragOver &&
								isFolder &&
								"bg-primary/30 border-2 border-primary",
						)}
						style={{ paddingLeft: `${level * 12 + 8}px` }}
					>
						{isFolder && (
							<>
								{isLoadingContents ? (
									<Loader2 className="h-4 w-4 flex-shrink-0 animate-spin text-muted-foreground" />
								) : isExpanded ? (
									<ChevronDown className="h-4 w-4 flex-shrink-0 text-muted-foreground" />
								) : (
									<ChevronRight className="h-4 w-4 flex-shrink-0 text-muted-foreground" />
								)}
								<Folder className="h-4 w-4 flex-shrink-0 text-primary" />
							</>
						)}
						{!isFolder &&
							(() => {
								const { icon: FileIcon, className } = getFileIcon(
									file.entity_type,
									file.extension,
								);
								return (
									<>
										<div className="w-4" />
										<FileIcon
											className={cn(
												"h-4 w-4 flex-shrink-0",
												className,
											)}
										/>
									</>
								);
							})()}
						<span className="flex-1 truncate">{file.name}</span>
					</button>
				</FileTreeContextMenu>
			)}

			{/* Inline new item editor (shown when creating in this folder) */}
			{creatingItem && creatingInFolder === file.path && (
				<div
					className="flex items-center gap-2 rounded-md px-2 py-1 bg-muted/50 mt-1"
					style={{ paddingLeft: `${(level + 1) * 12 + 8}px` }}
				>
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
						onChange={(e) => setNewItemName(e.target.value)}
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
		</div>
	);
}

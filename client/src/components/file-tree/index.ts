/**
 * Modular File Tree Component
 *
 * A reusable file tree that works with different backends through
 * dependency injection. Use this instead of hardcoded implementations.
 *
 * Usage:
 *
 * // For workspace files (code editor)
 * import { FileTree, workspaceOperations, defaultIconResolver } from '@/components/file-tree';
 *
 * <FileTree
 *   operations={workspaceOperations}
 *   iconResolver={defaultIconResolver}
 *   editor={{
 *     onFileOpen: (file, content) => openInEditor(file, content),
 *     isFileSelected: (path) => currentFile === path,
 *   }}
 * />
 *
 * // For app code files (app builder)
 * import { FileTree, createAppCodeOperations, appCodeIconResolver } from '@/components/file-tree';
 *
 * const operations = createAppCodeOperations(appId, versionId);
 * <FileTree
 *   operations={operations}
 *   iconResolver={appCodeIconResolver}
 * />
 */

// Main component
export { FileTree } from "./FileTree";

// Workspace-specific component (for code editor)
export { WorkspaceFileTree } from "./WorkspaceFileTree";

// Types
export type {
	FileNode,
	FileTreeNode,
	FileContent,
	FileOperations,
	FileIconConfig,
	FileIconResolver,
	EditorCallbacks,
	FileTreeConfig,
	FileTreeProps,
	PathValidator,
	PathValidationResult,
} from "./types";

// Validation
export {
	validateAppCodePath,
	createRelativePathValidator,
} from "./validation";

// Icon resolvers
export {
	defaultIconResolver,
	appCodeIconResolver,
	createCompositeResolver,
	ENTITY_TYPE_ICONS,
	EXTENSION_ICONS,
} from "./icons";

// Hook
export { useFileTree } from "./useFileTree";

// Adapters
export { workspaceOperations } from "./adapters/workspaceOperations";
export { createAppCodeOperations } from "./adapters/appCodeOperations";

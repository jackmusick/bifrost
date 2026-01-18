/**
 * File Tree Icon Resolvers
 *
 * Provides default and extensible icon resolution for file tree items.
 * Each implementation can customize icons based on their specific needs.
 */

import {
	File,
	Folder,
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
	Layout,
	Component,
	Route,
	Building2,
} from "lucide-react";
import type { FileNode, FileIconConfig, FileIconResolver } from "./types";

/**
 * Platform entity type icons (workflow, form, app, agent)
 * Highest priority - these represent Bifrost platform entities
 */
export const ENTITY_TYPE_ICONS: Record<string, FileIconConfig> = {
	workflow: { icon: Workflow, className: "text-blue-500" },
	form: { icon: FileText, className: "text-green-500" },
	app: { icon: AppWindow, className: "text-purple-500" },
	agent: { icon: Bot, className: "text-orange-500" },
};

/**
 * File extension icons
 * Used when no entity type is present
 */
export const EXTENSION_ICONS: Record<string, FileIconConfig> = {
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
 * Default file icon resolver
 *
 * Resolution order:
 * 1. Entity type (workflow, form, app, agent)
 * 2. File extension
 * 3. Folder (with open/closed state support)
 * 4. Default file icon
 */
export const defaultIconResolver: FileIconResolver = (file: FileNode): FileIconConfig => {
	// Platform entity types take priority
	if (file.entityType && ENTITY_TYPE_ICONS[file.entityType]) {
		return ENTITY_TYPE_ICONS[file.entityType];
	}

	// Folder icons
	if (file.type === "folder") {
		return { icon: Folder, className: "text-primary" };
	}

	// Extension-based icons
	if (file.extension) {
		const ext = file.extension.toLowerCase();
		if (EXTENSION_ICONS[ext]) {
			return EXTENSION_ICONS[ext];
		}
	}

	// Default file icon
	return { icon: File, className: "text-muted-foreground" };
};

/**
 * App Code Builder icon resolver
 *
 * Extends default resolver with app code-specific icons:
 * - _layout files (Layout icon)
 * - _providers file (Settings icon)
 * - Dynamic route segments [param] (Route icon)
 * - Pages (FileCode icon, green)
 * - Components (Component icon, cyan)
 * - Modules (Braces icon, blue)
 */
export const appCodeIconResolver: FileIconResolver = (file: FileNode): FileIconConfig => {
	// Special files at root
	if (file.name === "_layout") {
		return { icon: Layout, className: "text-purple-500" };
	}
	if (file.name === "_providers") {
		return { icon: Settings, className: "text-amber-500" };
	}

	// Dynamic route segments
	if (file.name.startsWith("[") && file.name.endsWith("]")) {
		if (file.type === "folder") {
			return { icon: Folder, className: "text-blue-500" };
		}
		return { icon: Route, className: "text-blue-500" };
	}

	// Path-based icons
	if (file.path.startsWith("pages/") || file.path === "pages") {
		if (file.type === "folder") {
			return { icon: Folder, className: "text-green-500" };
		}
		// Page files
		if (file.name === "index") {
			return { icon: FileCode, className: "text-green-500" };
		}
		return { icon: FileCode, className: "text-green-400" };
	}

	if (file.path.startsWith("components/") || file.path === "components") {
		if (file.type === "folder") {
			return { icon: Folder, className: "text-cyan-500" };
		}
		return { icon: Component, className: "text-cyan-500" };
	}

	if (file.path.startsWith("modules/") || file.path === "modules") {
		if (file.type === "folder") {
			return { icon: Folder, className: "text-blue-500" };
		}
		return { icon: Braces, className: "text-blue-400" };
	}

	// Fall back to default resolver
	return defaultIconResolver(file);
};

/**
 * Organization-scoped icon resolver
 *
 * Extends default resolver with organization container icons.
 * Uses metadata.isOrgContainer to identify org containers.
 */
export const orgScopedIconResolver: FileIconResolver = (file: FileNode): FileIconConfig => {
	// Organization container folders
	if (file.metadata?.isOrgContainer) {
		return { icon: Building2, className: "text-orange-500" };
	}

	// Fall back to default resolver
	return defaultIconResolver(file);
};

/**
 * Create a composite icon resolver that tries multiple resolvers in order
 *
 * @param resolvers - Array of resolvers to try (first match wins)
 * @returns Combined resolver function
 */
export function createCompositeResolver(
	...resolvers: FileIconResolver[]
): FileIconResolver {
	return (file: FileNode): FileIconConfig => {
		// Try each resolver - if it returns something other than the default,
		// use that. Otherwise, fall through to the next resolver.
		const defaultIcon = { icon: File, className: "text-muted-foreground" };

		for (const resolver of resolvers) {
			const result = resolver(file);
			// Check if this resolver returned a meaningful icon
			if (result.icon !== File || result.className !== "text-muted-foreground") {
				return result;
			}
		}

		return defaultIcon;
	};
}

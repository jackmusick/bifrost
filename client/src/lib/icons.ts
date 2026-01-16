/**
 * Dynamic Icon Utility
 *
 * Resolves icon names (kebab-case like "folder-open") to Lucide React components.
 */

import * as LucideIcons from "lucide-react";

/**
 * Get icon component by name from lucide-react
 *
 * @param iconName - Icon name in kebab-case (e.g., "folder-open", "alert-triangle")
 * @param fallback - Fallback icon if not found (defaults to Home)
 * @returns The Lucide icon component
 *
 * @example
 * const Icon = getIcon("folder-open");
 * return <Icon className="h-4 w-4" />;
 */
export function getIcon(
	iconName?: string | null,
	fallback: LucideIcons.LucideIcon = LucideIcons.Home,
): LucideIcons.LucideIcon {
	if (!iconName) return fallback;

	// Convert kebab-case to PascalCase (e.g., "folder-open" -> "FolderOpen")
	const pascalName = iconName
		.split("-")
		.map((part) => part.charAt(0).toUpperCase() + part.slice(1))
		.join("");

	const icons = LucideIcons as unknown as Record<
		string,
		LucideIcons.LucideIcon
	>;
	const IconComponent = icons[pascalName];
	return IconComponent || fallback;
}

/**
 * Check if an icon name is valid (exists in lucide-react)
 */
export function isValidIcon(iconName: string): boolean {
	const pascalName = iconName
		.split("-")
		.map((part) => part.charAt(0).toUpperCase() + part.slice(1))
		.join("");

	const icons = LucideIcons as unknown as Record<string, unknown>;
	return typeof icons[pascalName] === "function";
}

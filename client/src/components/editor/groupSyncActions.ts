/**
 * Groups sync actions by entity for UI display.
 *
 * - Forms, agents, workflows: individual items
 * - Apps: grouped with their files as children
 */

import type { SyncAction, SyncConflictInfo } from "@/hooks/useGitHub";

export interface GroupedEntity {
	/** The main entity action (or app metadata action) */
	action: SyncAction;
	/** Child files for app entities */
	childFiles: SyncAction[];
}

/**
 * Group sync actions by entity for display.
 *
 * Apps are grouped together with their files as children.
 * Other entities (forms, agents, workflows) remain individual.
 */
export function groupSyncActions(actions: SyncAction[]): GroupedEntity[] {
	const appGroups = new Map<string, GroupedEntity>();
	const standaloneEntities: GroupedEntity[] = [];

	for (const action of actions) {
		if (action.entity_type === "app" && action.parent_slug) {
			// App metadata (app.json) - create or update group
			const existing = appGroups.get(action.parent_slug);
			if (existing) {
				// Replace placeholder with actual app metadata
				existing.action = action;
			} else {
				appGroups.set(action.parent_slug, {
					action,
					childFiles: [],
				});
			}
		} else if (action.entity_type === "app_file" && action.parent_slug) {
			// App file - add to group
			const existing = appGroups.get(action.parent_slug);
			if (existing) {
				existing.childFiles.push(action);
			} else {
				// Create placeholder group (app.json may come later)
				appGroups.set(action.parent_slug, {
					action: {
						...action,
						entity_type: "app",
						display_name: action.parent_slug,
					},
					childFiles: [action],
				});
			}
		} else {
			// Standalone entity (form, agent, workflow, unknown)
			standaloneEntities.push({
				action,
				childFiles: [],
			});
		}
	}

	// Combine: apps first, then standalone entities
	// Sort apps by display name, standalone by display name
	const sortedApps = Array.from(appGroups.values()).sort((a, b) =>
		(a.action.display_name || "").localeCompare(b.action.display_name || "")
	);
	const sortedStandalone = standaloneEntities.sort((a, b) =>
		(a.action.display_name || "").localeCompare(b.action.display_name || "")
	);

	return [...sortedApps, ...sortedStandalone];
}

/**
 * A grouped conflict (for apps with child file conflicts)
 */
export interface GroupedConflict {
	/** The main conflict (app.json or standalone entity) */
	conflict: SyncConflictInfo;
	/** Child file conflicts for app entities */
	childConflicts: SyncConflictInfo[];
}

/**
 * Group conflicts by entity for display.
 *
 * Apps are grouped together with their child file conflicts.
 * Other entities (forms, agents, workflows) remain individual.
 */
export function groupConflicts(conflicts: SyncConflictInfo[]): GroupedConflict[] {
	const appGroups = new Map<string, GroupedConflict>();
	const standaloneConflicts: GroupedConflict[] = [];

	for (const conflict of conflicts) {
		if (conflict.entity_type === "app" && conflict.parent_slug) {
			// App metadata (app.json) - create or update group
			const existing = appGroups.get(conflict.parent_slug);
			if (existing) {
				// Replace placeholder with actual app metadata
				existing.conflict = conflict;
			} else {
				appGroups.set(conflict.parent_slug, {
					conflict,
					childConflicts: [],
				});
			}
		} else if (conflict.entity_type === "app_file" && conflict.parent_slug) {
			// App file - add to group
			const existing = appGroups.get(conflict.parent_slug);
			if (existing) {
				existing.childConflicts.push(conflict);
			} else {
				// Create placeholder group (app.json may come later or not be conflicted)
				appGroups.set(conflict.parent_slug, {
					conflict: {
						...conflict,
						entity_type: "app",
						display_name: conflict.parent_slug,
					} as SyncConflictInfo,
					childConflicts: [conflict],
				});
			}
		} else {
			// Standalone entity (form, agent, workflow, unknown)
			standaloneConflicts.push({
				conflict,
				childConflicts: [],
			});
		}
	}

	// Combine: apps first, then standalone entities
	// Sort apps by display name, standalone by display name
	const sortedApps = Array.from(appGroups.values()).sort((a, b) =>
		(a.conflict.display_name || "").localeCompare(b.conflict.display_name || "")
	);
	const sortedStandalone = standaloneConflicts.sort((a, b) =>
		(a.conflict.display_name || "").localeCompare(b.conflict.display_name || "")
	);

	return [...sortedApps, ...sortedStandalone];
}

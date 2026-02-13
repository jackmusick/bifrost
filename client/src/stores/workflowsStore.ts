import { create } from "zustand";
import type { components } from "@/lib/v1";

type WorkflowMetadata = components["schemas"]["WorkflowMetadata"];

/**
 * Workflows store using Zustand
 * Provides centralized state for workflows with incremental updates
 *
 * This complements React Query's useWorkflowsMetadata by providing:
 * 1. Global state for checking if a file is a workflow
 * 2. Incremental reload support for editor file saves
 * 3. File type detection for status bar
 */

interface WorkflowsState {
	// Workflows indexed by source_file_path for quick lookup
	workflowsByPath: Map<string, WorkflowMetadata>;

	// All workflows
	workflows: WorkflowMetadata[];

	// Loading state
	isLoading: boolean;
	lastUpdated: Date | null;

	// Actions
	setWorkflows: (workflows: WorkflowMetadata[]) => void;
	isWorkflowFile: (filePath: string) => boolean;
	getWorkflowByPath: (filePath: string) => WorkflowMetadata | undefined;
	getRegisteredFunctions: (filePath: string) => Set<string>;
}

export const useWorkflowsStore = create<WorkflowsState>((set, get) => ({
	workflowsByPath: new Map(),
	workflows: [],
	isLoading: false,
	lastUpdated: null,

	setWorkflows: (workflows) => {
		// Build path index for O(1) lookup using relative paths (consistent with editor)
		const workflowsByPath = new Map<string, WorkflowMetadata>();
		for (const workflow of workflows) {
			if (workflow.relative_file_path) {
				workflowsByPath.set(workflow.relative_file_path, workflow);
			}
		}

		set({
			workflows,
			workflowsByPath,
			isLoading: false,
			lastUpdated: new Date(),
		});
	},

	isWorkflowFile: (filePath) => {
		const { workflowsByPath } = get();
		return workflowsByPath.has(filePath);
	},

	getWorkflowByPath: (filePath) => {
		const { workflowsByPath } = get();
		return workflowsByPath.get(filePath);
	},

	getRegisteredFunctions: (filePath) => {
		const { workflows } = get();
		const names = new Set<string>();
		for (const wf of workflows) {
			if (wf.relative_file_path === filePath && wf.function_name) {
				names.add(wf.function_name);
			}
		}
		return names;
	},
}));

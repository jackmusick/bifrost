import { create } from "zustand";
import type { AgentRunStep } from "@/services/agentRuns";

interface AgentRunStepStreamState {
	steps: AgentRunStep[];
	isConnected: boolean;
}

interface AgentRunStepStore {
	streams: Record<string, AgentRunStepStreamState>;
	startStreaming: (runId: string) => void;
	appendStep: (runId: string, step: AgentRunStep) => void;
	setConnectionStatus: (runId: string, connected: boolean) => void;
	clearStream: (runId: string) => void;
}

export const useAgentRunStepStore = create<AgentRunStepStore>((set) => ({
	streams: {},

	startStreaming: (runId) =>
		set((state) => {
			if (state.streams[runId]) return state;
			return {
				streams: {
					...state.streams,
					[runId]: { steps: [], isConnected: false },
				},
			};
		}),

	appendStep: (runId, step) =>
		set((state) => {
			const stream = state.streams[runId];
			if (!stream) return state;
			// Deduplicate by step id
			if (stream.steps.some((s) => s.id === step.id)) return state;
			return {
				streams: {
					...state.streams,
					[runId]: { ...stream, steps: [...stream.steps, step] },
				},
			};
		}),

	setConnectionStatus: (runId, connected) =>
		set((state) => {
			const stream = state.streams[runId];
			if (!stream) return state;
			return {
				streams: {
					...state.streams,
					[runId]: { ...stream, isConnected: connected },
				},
			};
		}),

	clearStream: (runId) =>
		set((state) => {
			if (!state.streams[runId]) return state;
			const { [runId]: _, ...rest } = state.streams;
			return { streams: rest };
		}),
}));

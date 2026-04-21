/**
 * Component tests for ChatSidebar.
 *
 * Covers:
 *   - Loading state renders skeletons
 *   - Empty state renders the "No conversations yet" copy
 *   - Conversation list render + search filters by title/agent/preview
 *   - New Chat button triggers createConversation and navigates on success
 *   - Active conversation gets the bg-accent highlight class
 *   - Delete flow opens confirm dialog and triggers mutation on confirm
 *
 * useChat hooks, the chatStore, and useNavigate are mocked so nothing hits
 * real network or the browser history.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderWithProviders, screen, fireEvent } from "@/test-utils";

// --- mocks --------------------------------------------------------------

const conversationsRef: {
	data: Array<Record<string, unknown>> | undefined;
	isLoading: boolean;
} = { data: [], isLoading: false };

const mockCreateMutate = vi.fn();
const mockDeleteMutate = vi.fn();

vi.mock("@/hooks/useChat", () => ({
	useConversations: () => ({
		data: conversationsRef.data,
		isLoading: conversationsRef.isLoading,
	}),
	useCreateConversation: () => ({
		mutate: mockCreateMutate,
		isPending: false,
	}),
	useDeleteConversation: () => ({
		mutate: mockDeleteMutate,
		isPending: false,
	}),
}));

// Chat store: we only need a handful of selectors / setters.
const storeState = {
	activeConversationId: null as string | null,
	setActiveConversation: vi.fn(),
	setActiveAgent: vi.fn(),
};

vi.mock("@/stores/chatStore", () => ({
	useChatStore: <T,>(selector?: (s: typeof storeState) => T) =>
		selector ? selector(storeState) : storeState,
}));

const mockNavigate = vi.fn();
vi.mock("react-router-dom", async () => {
	const actual = await vi.importActual<typeof import("react-router-dom")>(
		"react-router-dom",
	);
	return { ...actual, useNavigate: () => mockNavigate };
});

import { ChatSidebar } from "./ChatSidebar";

function conv(overrides: Record<string, unknown>) {
	return {
		id: "conv-1",
		agent_id: "agent-1",
		agent_name: "SupportBot",
		title: "Test conversation",
		updated_at: new Date().toISOString(),
		last_message_preview: "Hello there",
		...overrides,
	};
}

beforeEach(() => {
	conversationsRef.data = [];
	conversationsRef.isLoading = false;
	storeState.activeConversationId = null;
	storeState.setActiveConversation.mockReset();
	storeState.setActiveAgent.mockReset();
	mockCreateMutate.mockReset();
	mockDeleteMutate.mockReset();
	mockNavigate.mockReset();
});

// --- tests --------------------------------------------------------------

describe("ChatSidebar — loading & empty states", () => {
	it("renders skeleton rows while conversations are loading", () => {
		conversationsRef.data = undefined;
		conversationsRef.isLoading = true;
		const { container } = renderWithProviders(<ChatSidebar />);
		// Skeleton rows use the "Skeleton" component; happy-dom renders them
		// as animated divs. We assert at least one placeholder row is present.
		expect(container.querySelectorAll(".animate-pulse").length).toBeGreaterThan(
			0,
		);
	});

	it("shows the 'No conversations yet' empty state", () => {
		renderWithProviders(<ChatSidebar />);
		expect(screen.getByText(/no conversations yet/i)).toBeInTheDocument();
	});
});

describe("ChatSidebar — conversation list", () => {
	it("lists conversations and applies the active highlight", () => {
		conversationsRef.data = [
			conv({ id: "c-1", title: "First" }),
			conv({ id: "c-2", title: "Second" }),
		];
		storeState.activeConversationId = "c-2";

		renderWithProviders(<ChatSidebar />);
		expect(screen.getByText("First")).toBeInTheDocument();
		const secondRow = screen.getByText("Second").closest("div.group");
		expect(secondRow?.className).toMatch(/bg-accent/);
	});

	it("filters by title via the search input", () => {
		conversationsRef.data = [
			conv({ id: "c-1", title: "Alpha" }),
			conv({ id: "c-2", title: "Beta" }),
		];
		renderWithProviders(<ChatSidebar />);

		fireEvent.change(
			screen.getByPlaceholderText(/search conversations/i),
			{ target: { value: "alp" } },
		);

		expect(screen.getByText("Alpha")).toBeInTheDocument();
		expect(screen.queryByText("Beta")).not.toBeInTheDocument();
	});

	it("navigates when an existing conversation is clicked", async () => {
		conversationsRef.data = [conv({ id: "c-1", title: "Alpha" })];
		const { user } = renderWithProviders(<ChatSidebar />);

		await user.click(screen.getByText("Alpha"));

		expect(storeState.setActiveConversation).toHaveBeenCalledWith("c-1");
		expect(mockNavigate).toHaveBeenCalledWith("/chat/c-1");
	});
});

describe("ChatSidebar — new chat", () => {
	it("calls createConversation.mutate and navigates on success", async () => {
		mockCreateMutate.mockImplementation((_body, opts) => {
			opts?.onSuccess?.({ id: "new-id" });
		});
		const { user } = renderWithProviders(<ChatSidebar />);

		await user.click(screen.getByRole("button", { name: /new chat/i }));

		expect(mockCreateMutate).toHaveBeenCalledTimes(1);
		expect(mockNavigate).toHaveBeenCalledWith("/chat/new-id");
	});
});

describe("ChatSidebar — delete flow", () => {
	it("opens the confirm dialog and triggers delete on confirm", async () => {
		conversationsRef.data = [conv({ id: "c-1", title: "Alpha" })];
		const { user, container } = renderWithProviders(<ChatSidebar />);

		// The trash icon button sits inside the row and is only visible on hover
		// (opacity-0 group-hover:opacity-100). It's still in the DOM and clickable.
		const row = screen.getByText("Alpha").closest("div.group")!;
		const deleteButton = row.querySelector("button");
		expect(deleteButton).not.toBeNull();
		await user.click(deleteButton!);

		// Confirm dialog surfaces the conversation title.
		expect(
			await screen.findByText(/delete conversation/i),
		).toBeInTheDocument();

		await user.click(screen.getByRole("button", { name: /^delete$/i }));

		expect(mockDeleteMutate).toHaveBeenCalledWith({
			params: { path: { conversation_id: "c-1" } },
		});

		// Avoid an unused-variable warning from the test harness.
		void container;
	});
});

/**
 * Component tests for AgentDialog.
 *
 * A big react-hook-form + zod dialog. We mock every hook at module scope
 * so we can exercise:
 *
 *   - Create mode: default values, name + prompt validation, happy-path
 *     submit calls useCreateAgent with the right payload
 *   - Edit mode: values from useAgent populate the form, submit goes
 *     through useUpdateAgent, loading state while the agent is fetched
 *   - Access-level conditional UI: role_based shows the Assigned Roles
 *     section; authenticated hides it
 *   - Platform-admin-only UI: Organization picker visibility
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderWithProviders, screen, waitFor } from "@/test-utils";

// -----------------------------------------------------------------------------
// Mocks
// -----------------------------------------------------------------------------

const mockAuth = vi.fn();
vi.mock("@/contexts/AuthContext", () => ({
	useAuth: () => mockAuth(),
}));

const mockUseAgent = vi.fn();
const mockUseAgents = vi.fn();
const mockCreateAgent = vi.fn();
const mockUpdateAgent = vi.fn();
const mockCreateMutation = vi.fn();
const mockUpdateMutation = vi.fn();
vi.mock("@/hooks/useAgents", () => ({
	useAgent: (id: string | undefined) => mockUseAgent(id),
	useAgents: () => mockUseAgents(),
	useCreateAgent: () => ({
		mutateAsync: mockCreateMutation,
		isPending: false,
	}),
	useUpdateAgent: () => ({
		mutateAsync: mockUpdateMutation,
		isPending: false,
	}),
}));
void mockCreateAgent;
void mockUpdateAgent;

const mockUseToolsGrouped = vi.fn();
vi.mock("@/hooks/useTools", () => ({
	useToolsGrouped: () => mockUseToolsGrouped(),
}));

const mockUseRoles = vi.fn();
vi.mock("@/hooks/useRoles", () => ({
	useRoles: () => mockUseRoles(),
}));

const mockUseKnowledge = vi.fn();
vi.mock("@/hooks/useKnowledge", () => ({
	useKnowledgeNamespaces: () => mockUseKnowledge(),
}));

const mockUseLLMModels = vi.fn();
vi.mock("@/hooks/useLLMConfig", () => ({
	useLLMModels: () => mockUseLLMModels(),
}));

// OrganizationSelect is a networked select; stub to a simple labeled control.
vi.mock("@/components/forms/OrganizationSelect", () => ({
	OrganizationSelect: ({
		value,
		onChange,
	}: {
		value: string | null | undefined;
		onChange: (v: string | null) => void;
	}) => (
		<select
			aria-label="organization"
			value={value ?? ""}
			onChange={(e) => onChange(e.target.value || null)}
		>
			<option value="">Global</option>
			<option value="org-1">Acme</option>
		</select>
	),
}));

// TiptapEditor is a rich-text editor with a huge dep tree; stub to a textarea
// bound to the same onChange/value contract so we can type a prompt.
vi.mock("@/components/ui/tiptap-editor", () => ({
	TiptapEditor: ({
		content,
		onChange,
		placeholder,
	}: {
		content: string;
		onChange: (v: string) => void;
		placeholder?: string;
	}) => (
		<textarea
			aria-label="system prompt"
			placeholder={placeholder}
			value={content}
			onChange={(e) => onChange(e.target.value)}
		/>
	),
}));

// -----------------------------------------------------------------------------
// Default fixtures
// -----------------------------------------------------------------------------

function resetMocks() {
	mockAuth.mockReturnValue({
		isPlatformAdmin: false,
		user: { organizationId: "org-1" },
	});
	mockUseAgent.mockReturnValue({ data: undefined, isLoading: false });
	mockUseAgents.mockReturnValue({ data: [] });
	mockUseToolsGrouped.mockReturnValue({
		data: { system: [], workflow: [] },
	});
	mockUseRoles.mockReturnValue({ data: [] });
	mockUseKnowledge.mockReturnValue({ data: [] });
	mockUseLLMModels.mockReturnValue({ models: [] });
	mockCreateMutation.mockReset();
	mockUpdateMutation.mockReset();
	mockCreateMutation.mockResolvedValue({});
	mockUpdateMutation.mockResolvedValue({});
}

beforeEach(() => {
	resetMocks();
});

async function renderDialog(
	overrides: Partial<{ agentId: string | null }> = {},
) {
	const { AgentDialog } = await import("./AgentDialog");
	const onOpenChange = vi.fn();
	const utils = renderWithProviders(
		<AgentDialog
			agentId={overrides.agentId ?? null}
			open={true}
			onOpenChange={onOpenChange}
		/>,
	);
	return { ...utils, onOpenChange };
}

// -----------------------------------------------------------------------------
// Tests
// -----------------------------------------------------------------------------

describe("AgentDialog — create mode validation", () => {
	it("shows required errors when submitting an empty form", async () => {
		const { user } = await renderDialog();

		await user.click(
			screen.getByRole("button", { name: /create agent/i }),
		);

		expect(
			await screen.findByText(/name is required/i),
		).toBeInTheDocument();
		expect(
			screen.getByText(/system prompt is required/i),
		).toBeInTheDocument();
		expect(mockCreateMutation).not.toHaveBeenCalled();
	});

	it("uses 'Create Agent' as the submit label", async () => {
		await renderDialog();
		expect(
			screen.getByRole("button", { name: /^create agent$/i }),
		).toBeInTheDocument();
	});
});

describe("AgentDialog — create mode submit", () => {
	it("submits with the form values on happy path", async () => {
		const { user } = await renderDialog();

		await user.type(
			screen.getByRole("textbox", { name: /^name$/i }),
			"Sales Bot",
		);
		await user.type(
			screen.getByLabelText(/system prompt/i),
			"Be helpful.",
		);
		await user.click(
			screen.getByRole("button", { name: /create agent/i }),
		);

		await waitFor(() =>
			expect(mockCreateMutation).toHaveBeenCalledTimes(1),
		);
		const payload = mockCreateMutation.mock.calls[0][0].body;
		expect(payload).toMatchObject({
			name: "Sales Bot",
			system_prompt: "Be helpful.",
			access_level: "role_based",
			channels: ["chat"],
			tool_ids: [],
			system_tools: [],
			delegated_agent_ids: [],
			role_ids: [],
			knowledge_sources: [],
		});
		// Non-platform-admin user defaults organization_id to their own org.
		expect(payload.organization_id).toBe("org-1");
	});
});

describe("AgentDialog — access level UI", () => {
	it("renders the Assigned Roles section under the default role_based access", async () => {
		await renderDialog();
		// The visible form label matches "Assigned Roles" exactly (a count
		// may be appended, which is why we use getAllByText) — but the
		// Select option description also contains "only assigned roles",
		// which is not what we want to match. Scope to form-label nodes.
		const labels = screen
			.getAllByText(/assigned roles/i)
			.filter((el) => el.getAttribute("data-slot") === "form-label");
		expect(labels.length).toBeGreaterThan(0);
	});

	it("hides the Assigned Roles section in edit mode when the agent has access_level=authenticated", async () => {
		// Radix Select is notoriously awkward to drive from tests, so we
		// observe the conditional via the edit-mode initial value instead.
		mockUseAgent.mockReturnValue({
			data: {
				id: "agent-1",
				name: "Agent",
				description: "",
				system_prompt: "hi",
				channels: ["chat"],
				access_level: "authenticated",
				tool_ids: [],
				delegated_agent_ids: [],
				role_ids: [],
				knowledge_sources: [],
				is_active: true,
			},
			isLoading: false,
		});

		await renderDialog({ agentId: "agent-1" });

		// The form label is gated on access_level; only the option description
		// ("Only assigned roles...") remains in the DOM.
		const labels = screen
			.queryAllByText(/assigned roles/i)
			.filter((el) => el.getAttribute("data-slot") === "form-label");
		expect(labels).toHaveLength(0);
	});
});

describe("AgentDialog — organization picker visibility", () => {
	it("does not show the Organization select for non-platform admins", async () => {
		await renderDialog();
		expect(screen.queryByLabelText(/organization/i)).not.toBeInTheDocument();
	});

	it("shows the Organization select for platform admins", async () => {
		mockAuth.mockReturnValue({
			isPlatformAdmin: true,
			user: { organizationId: null },
		});
		await renderDialog();
		expect(screen.getByLabelText(/organization/i)).toBeInTheDocument();
	});
});

describe("AgentDialog — edit mode", () => {
	const existing = {
		id: "agent-1",
		name: "Old Name",
		description: "desc",
		system_prompt: "old prompt",
		channels: ["chat"],
		access_level: "role_based",
		tool_ids: [],
		delegated_agent_ids: [],
		role_ids: [],
		knowledge_sources: [],
		is_active: true,
	};

	it("shows the loading spinner while the agent is being fetched", async () => {
		mockUseAgent.mockReturnValue({ data: undefined, isLoading: true });
		await renderDialog({ agentId: "agent-1" });
		// Title switches to edit mode.
		expect(
			screen.getByRole("heading", { name: /edit agent/i }),
		).toBeInTheDocument();
		// Form fields are NOT rendered while loading.
		expect(screen.queryByLabelText(/^name$/i)).not.toBeInTheDocument();
	});

	it("prepopulates the form from the fetched agent and submits via update", async () => {
		mockUseAgent.mockReturnValue({ data: existing, isLoading: false });

		const { user } = await renderDialog({ agentId: "agent-1" });

		// Field is pre-populated with the existing name.
		const nameInput = screen.getByRole("textbox", {
			name: /^name$/i,
		}) as HTMLInputElement;
		expect(nameInput.value).toBe("Old Name");

		// Rename and submit.
		await user.clear(nameInput);
		await user.type(nameInput, "New Name");

		await user.click(
			screen.getByRole("button", { name: /update agent/i }),
		);

		await waitFor(() =>
			expect(mockUpdateMutation).toHaveBeenCalledTimes(1),
		);
		const args = mockUpdateMutation.mock.calls[0][0];
		expect(args.params.path.agent_id).toBe("agent-1");
		expect(args.body.name).toBe("New Name");
		expect(args.body.system_prompt).toBe("old prompt");
		expect(mockCreateMutation).not.toHaveBeenCalled();
	});
});

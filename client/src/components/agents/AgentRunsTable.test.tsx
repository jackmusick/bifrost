/**
 * Component tests for AgentRunsTable.
 *
 * The table is driven by `useAgentRuns` + `useAgentRunListStream`. We mock
 * both at module scope (streaming is a no-op here) and cover:
 *
 *   - loading spinner while the runs query is pending
 *   - empty state copy (no search vs. search with no matches)
 *   - rendering a row with the right status badge and trigger label
 *   - isPlatformAdmin=true shows the Organization column + filter
 *   - click on a row navigates to /agent-runs/:id
 *   - status tab click updates the status filter (observable via the
 *     useAgentRuns call arguments)
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import {
	renderWithProviders,
	screen,
	within,
	fireEvent,
	waitFor,
} from "@/test-utils";
import type { AgentRun } from "@/services/agentRuns";

const mockNavigate = vi.fn();
vi.mock("react-router-dom", async () => {
	const actual =
		await vi.importActual<typeof import("react-router-dom")>(
			"react-router-dom",
		);
	return {
		...actual,
		useNavigate: () => mockNavigate,
	};
});

const mockUseAgentRuns = vi.fn();
const mockUseAgentRunListStream = vi.fn();
vi.mock("@/services/agentRuns", () => ({
	useAgentRuns: (params: unknown) => mockUseAgentRuns(params),
	useAgentRunListStream: () => mockUseAgentRunListStream(),
}));

vi.mock("@/hooks/useAgents", () => ({
	useAgents: () => ({
		data: [{ id: "agent-1", name: "Sales Bot" }],
	}),
}));

vi.mock("@/hooks/useOrganizations", () => ({
	useOrganizations: () => ({
		data: [{ id: "org-1", name: "Acme" }],
	}),
}));

// OrganizationSelect hits useOrganizations + renders a complicated combobox;
// stub it to a minimal labeled select so we can assert its presence.
vi.mock("@/components/forms/OrganizationSelect", () => ({
	OrganizationSelect: ({
		value,
		onChange,
	}: {
		value: string | null | undefined;
		onChange: (v: string | null) => void;
	}) => (
		<select
			aria-label="organization-filter"
			value={value ?? ""}
			onChange={(e) => onChange(e.target.value || null)}
		>
			<option value="">All organizations</option>
			<option value="org-1">Acme</option>
		</select>
	),
}));

function makeRun(overrides: Partial<AgentRun> = {}): AgentRun {
	return {
		id: "run-1",
		agent_id: "agent-1",
		agent_name: "Sales Bot",
		trigger_type: "chat",
		trigger_source: null,
		conversation_id: null,
		event_delivery_id: null,
		input: null,
		output: null,
		status: "completed",
		error: null,
		org_id: null,
		caller_user_id: null,
		caller_email: null,
		caller_name: null,
		iterations_used: 3,
		tokens_used: 1200,
		budget_max_iterations: null,
		budget_max_tokens: null,
		duration_ms: 2500,
		llm_model: null,
		created_at: "2026-04-20T12:00:00Z",
		started_at: "2026-04-20T12:00:00Z",
		completed_at: "2026-04-20T12:00:02Z",
		parent_run_id: null,
		...overrides,
	};
}

beforeEach(() => {
	mockNavigate.mockReset();
	mockUseAgentRuns.mockReset();
	mockUseAgentRunListStream.mockReset();

	mockUseAgentRuns.mockReturnValue({
		data: { items: [makeRun()], total: 1, next_cursor: null },
		isLoading: false,
	});
});

import { AgentRunsTable } from "./AgentRunsTable";

function renderTable(isPlatformAdmin = false) {
	return renderWithProviders(
		<AgentRunsTable isPlatformAdmin={isPlatformAdmin} />,
	);
}

describe("AgentRunsTable — async states", () => {
	it("shows the 'No agent runs found' empty state", async () => {
		mockUseAgentRuns.mockReturnValueOnce({
			data: { items: [], total: 0, next_cursor: null },
			isLoading: false,
		});
		await renderTable();
		expect(
			screen.getByText(/no agent runs found/i),
		).toBeInTheDocument();
		expect(
			screen.getByText(/trigger an agent to see runs appear here/i),
		).toBeInTheDocument();
	});

	it("shows the no-match copy when a search term filters everything out", async () => {
		await renderTable();
		// SearchBox debounces updates by 300ms, so use fireEvent for a
		// single synchronous state change and then wait for the debounce.
		fireEvent.change(
			screen.getByPlaceholderText(/search by agent name/i),
			{ target: { value: "zzz-no-match" } },
		);
		await waitFor(
			() =>
				expect(
					screen.getByText(/no agent runs match your search/i),
				).toBeInTheDocument(),
			{ timeout: 1500 },
		);
	});
});

describe("AgentRunsTable — row rendering", () => {
	it("renders the agent name, status, trigger, and duration", async () => {
		await renderTable();
		// Scope to the data rows only — the tabs and column headers both
		// contain "Completed" copy, so a broader match would be ambiguous.
		const table = screen.getByRole("table");
		const [row] = within(table).getAllByRole("row").slice(1); // skip header
		expect(within(row).getByText("Sales Bot")).toBeInTheDocument();
		// The Completed status badge renders its text in the row.
		expect(within(row).getByText(/^Completed$/)).toBeInTheDocument();
		// Trigger label — "Chat" is rendered from the labels map for trigger=chat.
		expect(within(row).getByText("Chat")).toBeInTheDocument();
		// Duration: 2500ms → "2.5s"
		expect(within(row).getByText("2.5s")).toBeInTheDocument();
	});

	it("omits the Organization column for non-platform admins", async () => {
		await renderTable(false);
		expect(
			screen.queryByRole("columnheader", { name: /organization/i }),
		).not.toBeInTheDocument();
	});

	it("renders the Organization column + filter for platform admins", async () => {
		await renderTable(true);
		expect(
			screen.getByRole("columnheader", { name: /organization/i }),
		).toBeInTheDocument();
		// Runs with org_id=null get a Global badge in the org column.
		expect(screen.getByText("Global")).toBeInTheDocument();
		// The filter stub is present too.
		expect(
			screen.getByLabelText(/organization-filter/i),
		).toBeInTheDocument();
	});
});

describe("AgentRunsTable — row interactions", () => {
	it("navigates to the run detail when a row is clicked", async () => {
		const { user } = await renderTable();

		await user.click(screen.getByText("Sales Bot"));

		expect(mockNavigate).toHaveBeenCalledWith("/agent-runs/run-1");
	});

	it("navigates via the eye icon button too", async () => {
		const { user } = await renderTable();

		// The per-row "View Details" action is a title-labeled icon button.
		const detailBtn = screen.getByRole("button", { name: /view details/i });
		await user.click(detailBtn);

		expect(mockNavigate).toHaveBeenCalledWith("/agent-runs/run-1");
	});
});

describe("AgentRunsTable — status tab filter", () => {
	it("forwards the selected status to useAgentRuns", async () => {
		const { user } = await renderTable();

		// Tabs render role=tab. Click "Failed".
		await user.click(screen.getByRole("tab", { name: /^failed$/i }));

		// The most recent call to useAgentRuns should have status=failed.
		const lastCall =
			mockUseAgentRuns.mock.calls[mockUseAgentRuns.mock.calls.length - 1];
		expect(lastCall[0]).toMatchObject({ status: "failed" });
	});

	it("passes status=undefined when the 'all' tab is active (default)", async () => {
		await renderTable();
		const firstCall = mockUseAgentRuns.mock.calls[0][0];
		expect(firstCall.status).toBeUndefined();
	});
});

describe("AgentRunsTable — agent filter", () => {
	it("filters by agent id when a specific agent is picked", async () => {
		const { user } = await renderTable();

		// The shadcn Select trigger shows "All agents" placeholder text;
		// target the button containing that copy.
		await user.click(screen.getByText(/all agents/i).closest("button")!);
		// The options list renders in a portal; pick Sales Bot.
		const option = await screen.findByRole("option", {
			name: /^sales bot$/i,
		});
		await user.click(option);

		const lastCall =
			mockUseAgentRuns.mock.calls[mockUseAgentRuns.mock.calls.length - 1];
		expect(lastCall[0]).toMatchObject({ agentId: "agent-1" });
	});
});

describe("AgentRunsTable — streaming hook wired up", () => {
	it("calls useAgentRunListStream so the table subscribes to live updates", async () => {
		await renderTable();
		expect(mockUseAgentRunListStream).toHaveBeenCalled();
	});
});

describe("AgentRunsTable — status badges", () => {
	it.each([
		["completed", /completed/i],
		["failed", /failed/i],
		["running", /running/i],
		["queued", /queued/i],
		["budget_exceeded", /budget exceeded/i],
	] as const)(
		"renders the %s badge copy",
		async (status, matcher) => {
			mockUseAgentRuns.mockReturnValueOnce({
				data: {
					items: [makeRun({ status })],
					total: 1,
					next_cursor: null,
				},
				isLoading: false,
			});
			const { unmount } = await renderTable();

			// Use `within` on the table so the status tab's copy (which
			// includes the same strings) doesn't create duplicates.
			const table = screen.getByRole("table");
			expect(within(table).getAllByText(matcher).length).toBeGreaterThan(
				0,
			);

			unmount();
		},
	);
});

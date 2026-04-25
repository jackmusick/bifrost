/**
 * Component tests for CreateEventSourceDialog.
 *
 * Covers the two source-type branches — webhook and schedule — plus the
 * required-field validation path. The auth context, event/integration
 * hooks, and authFetch (used for cron validation) are all mocked.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderWithProviders, screen, waitFor, fireEvent } from "@/test-utils";

const mockCreate = vi.fn();
const mockAuthFetch = vi.fn();

vi.mock("@/contexts/AuthContext", () => ({
	useAuth: () => ({ isPlatformAdmin: false }),
}));

vi.mock("@/components/forms/OrganizationSelect", () => ({
	OrganizationSelect: () => <div data-marker="org-select" />,
}));

vi.mock("@/lib/api-client", () => ({
	authFetch: (...args: unknown[]) => mockAuthFetch(...args),
	$api: {
		useQuery: vi.fn(() => ({ data: undefined, isLoading: false })),
		useMutation: vi.fn(() => ({ mutateAsync: vi.fn(), isPending: false })),
	},
}));

vi.mock("@/services/events", async () => {
	const actual = await vi.importActual<typeof import("@/services/events")>(
		"@/services/events",
	);
	return {
		...actual,
		useCreateEventSource: () => ({
			mutateAsync: mockCreate,
			isPending: false,
		}),
		useWebhookAdapters: () => ({
			data: {
				adapters: [
					{
						name: "generic",
						display_name: "Generic Webhook",
						description: "Generic webhook adapter",
						config_schema: {},
					},
				],
			},
		}),
	};
});

vi.mock("@/services/integrations", async () => {
	const actual =
		await vi.importActual<typeof import("@/services/integrations")>(
			"@/services/integrations",
		);
	return {
		...actual,
		useIntegrations: () => ({ data: { items: [] } }),
	};
});

import { CreateEventSourceDialog } from "./CreateEventSourceDialog";

beforeEach(() => {
	mockCreate.mockReset();
	mockCreate.mockResolvedValue({});
	mockAuthFetch.mockReset();
	mockAuthFetch.mockResolvedValue({
		ok: true,
		json: async () => ({
			valid: true,
			human_readable: "Every day at 9:00 AM",
			next_runs: [],
		}),
	});
});

describe("CreateEventSourceDialog — validation", () => {
	it("shows errors when the form is submitted with missing fields", async () => {
		const { user } = renderWithProviders(
			<CreateEventSourceDialog open onOpenChange={() => {}} />,
		);

		await user.click(
			screen.getByRole("button", { name: /create event source/i }),
		);

		// Alert role should surface the validation errors
		const alert = await screen.findByRole("alert");
		expect(alert).toHaveTextContent(/name is required/i);
		expect(alert).toHaveTextContent(/webhook adapter/i);
		expect(mockCreate).not.toHaveBeenCalled();
	});
});

describe("CreateEventSourceDialog — webhook happy path", () => {
	it("dispatches createMutation with webhook payload", async () => {
		const onOpenChange = vi.fn();
		const { user } = renderWithProviders(
			<CreateEventSourceDialog open onOpenChange={onOpenChange} />,
		);

		fireEvent.change(screen.getByLabelText(/^name$/i), {
			target: { value: "GitHub Hooks" },
		});

		// Select the adapter
		await user.click(screen.getByRole("combobox", { name: /webhook adapter/i }));
		await user.click(screen.getByRole("option", { name: /generic webhook/i }));

		await user.click(
			screen.getByRole("button", { name: /create event source/i }),
		);

		await waitFor(() => expect(mockCreate).toHaveBeenCalledTimes(1));
		const body = mockCreate.mock.calls[0]![0].body;
		expect(body.name).toBe("GitHub Hooks");
		expect(body.source_type).toBe("webhook");
		expect(body.webhook.adapter_name).toBe("generic");
	});
});

describe("CreateEventSourceDialog — schedule branch", () => {
	it("reveals cron + timezone inputs and validates the cron expression", async () => {
		const { user } = renderWithProviders(
			<CreateEventSourceDialog open onOpenChange={() => {}} />,
		);

		// Switch to schedule
		await user.click(screen.getByRole("combobox", { name: /source type/i }));
		await user.click(screen.getByRole("option", { name: /schedule/i }));

		expect(screen.getByLabelText(/cron expression/i)).toBeInTheDocument();
		expect(screen.getByLabelText(/timezone/i)).toBeInTheDocument();

		fireEvent.change(screen.getByLabelText(/cron expression/i), {
			target: { value: "0 9 * * *" },
		});

		await waitFor(() => expect(mockAuthFetch).toHaveBeenCalled());
		expect(
			await screen.findByText(/every day at 9:00 am/i),
		).toBeInTheDocument();
	});
});

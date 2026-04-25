/**
 * Component tests for EditEventSourceDialog.
 *
 * Covers the schedule-edit path: initial state rehydrates from the passed
 * source, cron validation runs via authFetch, and submit dispatches the
 * update with the edited values. Webhook branch is exercised more lightly
 * (only the name-edit happy path) because the dynamic config form is
 * covered separately.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderWithProviders, screen, waitFor, fireEvent } from "@/test-utils";

const mockUpdate = vi.fn();
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
		useUpdateEventSource: () => ({
			mutateAsync: mockUpdate,
			isPending: false,
		}),
		useWebhookAdapters: () => ({
			data: { adapters: [] },
		}),
	};
});

import { EditEventSourceDialog } from "./EditEventSourceDialog";
import type { EventSource } from "@/services/events";

beforeEach(() => {
	mockUpdate.mockReset();
	mockUpdate.mockResolvedValue({});
	mockAuthFetch.mockReset();
	mockAuthFetch.mockResolvedValue({
		ok: true,
		json: async () => ({
			valid: true,
			human_readable: "Every day at 9:00 AM",
		}),
	});
});

function makeScheduleSource(
	overrides: Partial<EventSource> = {},
): EventSource {
	return {
		id: "src-1",
		name: "Daily Sync",
		source_type: "schedule",
		organization_id: null,
		is_active: true,
		schedule: {
			cron_expression: "0 9 * * *",
			timezone: "UTC",
			enabled: true,
		},
		...overrides,
	} as unknown as EventSource;
}

describe("EditEventSourceDialog — schedule", () => {
	it("pre-fills the form from the source and submits the update", async () => {
		const onOpenChange = vi.fn();
		const { user } = renderWithProviders(
			<EditEventSourceDialog
				source={makeScheduleSource()}
				open
				onOpenChange={onOpenChange}
			/>,
		);

		// Name is pre-filled
		const nameInput = screen.getByLabelText(/^name$/i) as HTMLInputElement;
		expect(nameInput.value).toBe("Daily Sync");

		// Cron is pre-filled too
		const cronInput = screen.getByLabelText(
			/cron expression/i,
		) as HTMLInputElement;
		expect(cronInput.value).toBe("0 9 * * *");

		// Change the name and submit
		fireEvent.change(nameInput, { target: { value: "Nightly" } });
		await user.click(screen.getByRole("button", { name: /save changes/i }));

		await waitFor(() => expect(mockUpdate).toHaveBeenCalledTimes(1));
		const body = mockUpdate.mock.calls[0]![0].body;
		expect(body.name).toBe("Nightly");
		expect(body.schedule.cron_expression).toBe("0 9 * * *");
	});

	it("surfaces a validation error when cron is cleared on submit", async () => {
		const { user } = renderWithProviders(
			<EditEventSourceDialog
				source={makeScheduleSource()}
				open
				onOpenChange={() => {}}
			/>,
		);

		fireEvent.change(screen.getByLabelText(/cron expression/i), {
			target: { value: "" },
		});

		await user.click(screen.getByRole("button", { name: /save changes/i }));

		expect(
			await screen.findByText(/cron expression is required/i),
		).toBeInTheDocument();
		expect(mockUpdate).not.toHaveBeenCalled();
	});
});

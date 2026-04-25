/**
 * Component tests for EditSubscriptionDialog.
 *
 * Covers the pre-fill + update dispatch. The input mapping form is rendered
 * inline when the workflow has parameters; we verify it's present and that
 * save round-trips through the update mutation.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderWithProviders, screen, waitFor, fireEvent } from "@/test-utils";

const mockUpdate = vi.fn();

vi.mock("@/services/events", async () => {
	const actual = await vi.importActual<typeof import("@/services/events")>(
		"@/services/events",
	);
	return {
		...actual,
		useUpdateSubscription: () => ({
			mutateAsync: mockUpdate,
			isPending: false,
		}),
	};
});

vi.mock("@/hooks/useWorkflows", () => ({
	useWorkflows: () => ({
		data: [
			{
				id: "wf-1",
				name: "Onboard",
				parameters: [{ name: "ticket_id", type: "int" }],
			},
		],
	}),
}));

import { EditSubscriptionDialog } from "./EditSubscriptionDialog";
import type { EventSubscription } from "@/services/events";

function makeSub(overrides: Partial<EventSubscription> = {}): EventSubscription {
	return {
		id: "sub-1",
		source_id: "src-1",
		workflow_id: "wf-1",
		workflow_name: "Onboard",
		event_type: "ticket.created",
		input_mapping: { ticket_id: "{{ payload.id }}" },
		is_active: true,
		delivery_count: 0,
		success_count: 0,
		...overrides,
	} as unknown as EventSubscription;
}

beforeEach(() => {
	mockUpdate.mockReset();
	mockUpdate.mockResolvedValue({});
});

describe("EditSubscriptionDialog", () => {
	it("pre-fills the event type and input mapping from the subscription", () => {
		renderWithProviders(
			<EditSubscriptionDialog
				subscription={makeSub()}
				sourceId="src-1"
				open
				onOpenChange={() => {}}
			/>,
		);

		const eventTypeInput = screen.getByLabelText(
			/event type filter/i,
		) as HTMLInputElement;
		expect(eventTypeInput.value).toBe("ticket.created");

		const mappingInput = screen.getByLabelText(/ticket_id/i) as HTMLInputElement;
		expect(mappingInput.value).toBe("{{ payload.id }}");
	});

	it("submits the cleaned update payload", async () => {
		const { user } = renderWithProviders(
			<EditSubscriptionDialog
				subscription={makeSub()}
				sourceId="src-1"
				open
				onOpenChange={() => {}}
			/>,
		);

		fireEvent.change(screen.getByLabelText(/event type filter/i), {
			target: { value: "ticket.updated" },
		});

		await user.click(screen.getByRole("button", { name: /save changes/i }));

		await waitFor(() => expect(mockUpdate).toHaveBeenCalledTimes(1));
		const payload = mockUpdate.mock.calls[0]![0];
		expect(payload.params.path).toEqual({
			source_id: "src-1",
			subscription_id: "sub-1",
		});
		expect(payload.body.event_type).toBe("ticket.updated");
		expect(payload.body.input_mapping).toEqual({
			ticket_id: "{{ payload.id }}",
		});
	});

	it("emits null for event_type when the filter is cleared", async () => {
		const { user } = renderWithProviders(
			<EditSubscriptionDialog
				subscription={makeSub()}
				sourceId="src-1"
				open
				onOpenChange={() => {}}
			/>,
		);

		fireEvent.change(screen.getByLabelText(/event type filter/i), {
			target: { value: "" },
		});

		await user.click(screen.getByRole("button", { name: /save changes/i }));

		await waitFor(() => expect(mockUpdate).toHaveBeenCalledTimes(1));
		expect(mockUpdate.mock.calls[0]![0].body.event_type).toBeNull();
	});
});

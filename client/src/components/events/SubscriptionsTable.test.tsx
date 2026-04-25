/**
 * Component tests for SubscriptionsTable.
 *
 * Covers the empty/populated branches and the active-toggle wiring. Delete
 * confirmation dispatches the mutation; we verify both the confirm dialog
 * and the downstream call.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderWithProviders, screen, waitFor } from "@/test-utils";

const mockDelete = vi.fn();
const mockUpdate = vi.fn();
const useSubsMock = vi.fn();

vi.mock("@/services/events", async () => {
	const actual = await vi.importActual<typeof import("@/services/events")>(
		"@/services/events",
	);
	return {
		...actual,
		useSubscriptions: (...args: unknown[]) => useSubsMock(...args),
		useDeleteSubscription: () => ({
			mutateAsync: mockDelete,
			isPending: false,
		}),
		useUpdateSubscription: () => ({
			mutateAsync: mockUpdate,
			isPending: false,
		}),
	};
});

vi.mock("./CreateSubscriptionDialog", () => ({
	CreateSubscriptionDialog: () => <div data-marker="create-sub" />,
}));

vi.mock("./EditSubscriptionDialog", () => ({
	EditSubscriptionDialog: () => <div data-marker="edit-sub" />,
}));

import { SubscriptionsTable } from "./SubscriptionsTable";
import type { EventSubscription } from "@/services/events";

function makeSub(overrides: Partial<EventSubscription> = {}): EventSubscription {
	return {
		id: "sub-1",
		source_id: "src-1",
		workflow_id: "wf-1",
		workflow_name: "Onboard",
		event_type: null,
		input_mapping: null,
		is_active: true,
		delivery_count: 10,
		success_count: 9,
		failed_count: 1,
		...overrides,
	} as unknown as EventSubscription;
}

beforeEach(() => {
	mockDelete.mockReset();
	mockDelete.mockResolvedValue(undefined);
	mockUpdate.mockReset();
	mockUpdate.mockResolvedValue(undefined);
	useSubsMock.mockReset();
});

describe("SubscriptionsTable — empty", () => {
	it("shows the empty state with an Add button", () => {
		useSubsMock.mockReturnValue({
			data: { items: [] },
			isLoading: false,
			refetch: vi.fn(),
		});
		renderWithProviders(<SubscriptionsTable sourceId="src-1" />);
		expect(screen.getByText(/no subscriptions/i)).toBeInTheDocument();
		expect(
			screen.getAllByRole("button", { name: /add subscription/i }).length,
		).toBeGreaterThan(0);
	});
});

describe("SubscriptionsTable — populated", () => {
	it("renders a row with the workflow name and success rate", () => {
		useSubsMock.mockReturnValue({
			data: { items: [makeSub()] },
			isLoading: false,
			refetch: vi.fn(),
		});
		renderWithProviders(<SubscriptionsTable sourceId="src-1" />);

		expect(screen.getByText("Onboard")).toBeInTheDocument();
		expect(screen.getByText("90%")).toBeInTheDocument();
	});

	it("toggles the active switch and dispatches the update", async () => {
		useSubsMock.mockReturnValue({
			data: { items: [makeSub()] },
			isLoading: false,
			refetch: vi.fn(),
		});
		const { user } = renderWithProviders(
			<SubscriptionsTable sourceId="src-1" />,
		);

		await user.click(screen.getByRole("switch"));

		await waitFor(() => expect(mockUpdate).toHaveBeenCalledTimes(1));
		expect(mockUpdate.mock.calls[0]![0].body).toEqual({ is_active: false });
	});

	it("asks for delete confirmation before deleting", async () => {
		useSubsMock.mockReturnValue({
			data: { items: [makeSub()] },
			isLoading: false,
			refetch: vi.fn(),
		});
		const { user } = renderWithProviders(
			<SubscriptionsTable sourceId="src-1" />,
		);

		await user.click(
			screen.getByRole("button", { name: /delete subscription/i }),
		);

		// Alert dialog shows before dispatch
		expect(
			screen.getByRole("heading", { name: /delete subscription/i }),
		).toBeInTheDocument();
		expect(mockDelete).not.toHaveBeenCalled();

		await user.click(screen.getByRole("button", { name: /^delete$/i }));

		await waitFor(() => expect(mockDelete).toHaveBeenCalledTimes(1));
		expect(mockDelete.mock.calls[0]![0].params.path).toEqual({
			source_id: "src-1",
			subscription_id: "sub-1",
		});
	});
});

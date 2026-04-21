/**
 * Component tests for EventDetailDialog.
 *
 * Covers the loading / not-found / populated branches. The embedded
 * DeliveriesTable + VariablesTreeView are stubbed — this spec is about the
 * dialog's composition, not those children.
 */

import { describe, it, expect, vi } from "vitest";
import { renderWithProviders, screen } from "@/test-utils";

const useEventMock = vi.fn();
const useDeliveriesMock = vi.fn();

vi.mock("@/services/events", async () => {
	const actual = await vi.importActual<typeof import("@/services/events")>(
		"@/services/events",
	);
	return {
		...actual,
		useEvent: (...args: unknown[]) => useEventMock(...args),
		useDeliveries: (...args: unknown[]) => useDeliveriesMock(...args),
	};
});

vi.mock("./DeliveriesTable", () => ({
	DeliveriesTable: () => <div data-marker="deliveries" />,
}));

vi.mock("@/components/ui/variables-tree-view", () => ({
	VariablesTreeView: ({ data }: { data: unknown }) => (
		<pre data-marker="variables-tree">{JSON.stringify(data)}</pre>
	),
}));

import { EventDetailDialog } from "./EventDetailDialog";
import type { Event } from "@/services/events";

function makeEvent(overrides: Partial<Event> = {}): Event {
	return {
		id: "evt-1",
		source_id: "src-1",
		event_type: "ticket.created",
		status: "completed",
		received_at: "2026-04-20T12:00:00Z",
		source_ip: "10.0.0.1",
		headers: { "X-Test": "1" },
		data: { hello: "world" },
		...overrides,
	} as unknown as Event;
}

describe("EventDetailDialog", () => {
	it("renders metadata when the event is loaded", () => {
		useEventMock.mockReturnValue({ data: makeEvent(), isLoading: false });
		useDeliveriesMock.mockReturnValue({
			data: { items: [], total: 0 },
			isLoading: false,
		});
		renderWithProviders(
			<EventDetailDialog event={makeEvent()} onClose={() => {}} />,
		);

		expect(screen.getByText("ticket.created")).toBeInTheDocument();
		expect(screen.getByText("Completed")).toBeInTheDocument();
		expect(screen.getByText("10.0.0.1")).toBeInTheDocument();
	});

	it("renders the not-found state when the event load returns null", () => {
		useEventMock.mockReturnValue({ data: null, isLoading: false });
		useDeliveriesMock.mockReturnValue({
			data: { items: [], total: 0 },
			isLoading: false,
		});
		renderWithProviders(
			<EventDetailDialog event={makeEvent()} onClose={() => {}} />,
		);
		expect(screen.getByText(/event not found/i)).toBeInTheDocument();
	});

	it("renders skeletons while loading", () => {
		useEventMock.mockReturnValue({ data: undefined, isLoading: true });
		useDeliveriesMock.mockReturnValue({
			data: { items: [], total: 0 },
			isLoading: false,
		});
		renderWithProviders(
			<EventDetailDialog event={makeEvent()} onClose={() => {}} />,
		);
		// Radix portals DialogContent outside the container — query from document.
		expect(document.querySelector(".animate-pulse")).toBeTruthy();
	});

	it("is hidden when event=null", () => {
		useEventMock.mockReturnValue({ data: undefined, isLoading: false });
		useDeliveriesMock.mockReturnValue({
			data: { items: [], total: 0 },
			isLoading: false,
		});
		renderWithProviders(
			<EventDetailDialog event={null} onClose={() => {}} />,
		);
		expect(
			screen.queryByRole("heading", { name: /event details/i }),
		).not.toBeInTheDocument();
	});
});

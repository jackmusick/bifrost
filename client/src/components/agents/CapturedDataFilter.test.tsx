/**
 * Tests for CapturedDataFilter.
 *
 * Covers the serializer (pure fn) plus the component's add/remove/edit flow
 * with the metadata-keys and metadata-values hooks mocked at module scope.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { fireEvent } from "@testing-library/react";

import { renderWithProviders, screen } from "@/test-utils";
import {
	CapturedDataFilter,
	conditionsToQueryParam,
	type MetadataFilterCondition,
} from "./CapturedDataFilter";

const mockUseMetadataKeys = vi.fn();
const mockUseMetadataValues = vi.fn();

vi.mock("@/services/agentRuns", () => ({
	useMetadataKeys: (agentId: string | undefined) =>
		mockUseMetadataKeys(agentId),
	useMetadataValues: (agentId: string | undefined, key: string | undefined) =>
		mockUseMetadataValues(agentId, key),
}));

beforeEach(() => {
	mockUseMetadataKeys.mockReturnValue({
		data: {
			keys: ["customer", "billing_status", "service_category"],
		},
		isLoading: false,
	});
	mockUseMetadataValues.mockReturnValue({
		data: { values: ["Billable", "Non-billable"] },
		isLoading: false,
	});
});

describe("conditionsToQueryParam", () => {
	it("returns undefined for empty input", () => {
		expect(conditionsToQueryParam([])).toBeUndefined();
	});

	it("drops incomplete rows (missing key or value)", () => {
		// A row with only a key isn't a real filter — dropping it means the
		// user can click 'Add' without immediately firing a broken query.
		const out = conditionsToQueryParam([
			{ key: "customer", op: "eq", value: "" },
			{ key: "", op: "contains", value: "x" },
		]);
		expect(out).toBeUndefined();
	});

	it("serializes complete rows to the backend shape", () => {
		const out = conditionsToQueryParam([
			{ key: "billing_status", op: "eq", value: "Billable" },
			{ key: "service_category", op: "contains", value: "security" },
		]);
		expect(out).toBeDefined();
		expect(JSON.parse(out!)).toEqual([
			{ key: "billing_status", op: "eq", value: "Billable" },
			{ key: "service_category", op: "contains", value: "security" },
		]);
	});

	it("mixes complete + incomplete rows — keeps only complete", () => {
		const out = conditionsToQueryParam([
			{ key: "customer", op: "eq", value: "Acme" },
			{ key: "", op: "contains", value: "" },
		]);
		expect(JSON.parse(out!)).toEqual([
			{ key: "customer", op: "eq", value: "Acme" },
		]);
	});
});

describe("CapturedDataFilter", () => {
	it("renders 'Filter captured data' when no rows", () => {
		renderWithProviders(
			<CapturedDataFilter
				agentId="agent-1"
				value={[]}
				onChange={() => {}}
			/>,
		);
		expect(
			screen.getByRole("button", { name: /add captured data filter/i }),
		).toBeInTheDocument();
	});

	it("add button calls onChange with a new empty row (op=contains default)", () => {
		const onChange = vi.fn();
		renderWithProviders(
			<CapturedDataFilter
				agentId="agent-1"
				value={[]}
				onChange={onChange}
			/>,
		);
		fireEvent.click(
			screen.getByRole("button", { name: /add captured data filter/i }),
		);
		expect(onChange).toHaveBeenCalledWith([
			{ key: "", op: "contains", value: "" },
		]);
	});

	it("renders a row with op picker and a free-text value input when op=contains", () => {
		const rows: MetadataFilterCondition[] = [
			{ key: "customer", op: "contains", value: "acme" },
		];
		renderWithProviders(
			<CapturedDataFilter
				agentId="agent-1"
				value={rows}
				onChange={() => {}}
			/>,
		);
		expect(
			screen.getByLabelText(/captured data filter value/i),
		).toHaveValue("acme");
	});

	it("remove button strips the row out of the condition array", () => {
		const onChange = vi.fn();
		const rows: MetadataFilterCondition[] = [
			{ key: "customer", op: "eq", value: "Acme" },
			{ key: "billing_status", op: "eq", value: "Billable" },
		];
		renderWithProviders(
			<CapturedDataFilter
				agentId="agent-1"
				value={rows}
				onChange={onChange}
			/>,
		);
		const removeButtons = screen.getAllByRole("button", {
			name: /remove filter row/i,
		});
		fireEvent.click(removeButtons[0]);
		expect(onChange).toHaveBeenCalledWith([
			{ key: "billing_status", op: "eq", value: "Billable" },
		]);
	});

	it("guards useMetadataValues: only fires when op=eq and key is set", () => {
		// Contains row should NOT request values (nothing to show — free-text).
		const rows: MetadataFilterCondition[] = [
			{ key: "customer", op: "contains", value: "" },
		];
		renderWithProviders(
			<CapturedDataFilter
				agentId="agent-1"
				value={rows}
				onChange={() => {}}
			/>,
		);
		expect(mockUseMetadataValues).toHaveBeenCalledWith(
			"agent-1",
			undefined,
		);
	});

	it("eq with a selected key triggers the values lookup for that key", () => {
		const rows: MetadataFilterCondition[] = [
			{ key: "billing_status", op: "eq", value: "" },
		];
		renderWithProviders(
			<CapturedDataFilter
				agentId="agent-1"
				value={rows}
				onChange={() => {}}
			/>,
		);
		expect(mockUseMetadataValues).toHaveBeenCalledWith(
			"agent-1",
			"billing_status",
		);
	});
});

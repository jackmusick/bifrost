/**
 * Component tests for PolicyEditorRow.
 *
 * Monaco can't run in jsdom — we stub @monaco-editor/react to a textarea so
 * value/onChange behaviour can be exercised without launching a real editor.
 *
 * Covers:
 * - name input fires onChange with the new name
 * - description input writes back as null when cleared
 * - action checkboxes add/remove from the actions array
 * - JSON in the When editor commits to onChange when valid
 * - invalid JSON in the When editor surfaces a parse error and does NOT commit
 * - remove button calls onRemove
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderWithProviders, screen, fireEvent } from "@/test-utils";

// Monaco: stub to a textarea labelled by the path prop so we can find the
// editor for the row under test.
vi.mock("@monaco-editor/react", () => ({
	default: ({
		value,
		onChange,
		path,
	}: {
		value?: string;
		onChange?: (v: string | undefined) => void;
		path?: string;
	}) => (
		<textarea
			aria-label={path ?? "monaco-editor"}
			value={value ?? ""}
			onChange={(e) => onChange?.(e.target.value)}
		/>
	),
}));

vi.mock("@/contexts/ThemeContext", () => ({
	useTheme: () => ({ theme: "light" }),
}));

import { PolicyEditorRow } from "./PolicyEditorRow";
import type { Policy } from "./policy-templates";

const baseValue: Policy = {
	name: "own_row",
	description: "Owner can edit",
	actions: ["read", "update"],
	when: { eq: [{ row: "created_by" }, { user: "user_id" }] },
};

// Typed mocks: Vitest's vi.fn() returns a generic Mock that doesn't satisfy
// strict prop function types. Use vi.fn<...>() with the prop signature so the
// holder is both a Mock (.mock.calls usable) and assignable to the prop type.
let onChange: ReturnType<typeof vi.fn<(next: Policy) => void>>;
let onRemove: ReturnType<typeof vi.fn<() => void>>;

beforeEach(() => {
	onChange = vi.fn<(next: Policy) => void>();
	onRemove = vi.fn<() => void>();
});

describe("PolicyEditorRow — name + description", () => {
	it("emits onChange with the new name on each keystroke", async () => {
		const { user } = renderWithProviders(
			<PolicyEditorRow
				rowKey="row-1"
				value={baseValue}
				onChange={onChange}
				onRemove={onRemove}
			/>,
		);
		const nameInput = screen.getByLabelText(/^name$/i);
		// Component is fully controlled: the parent owns `value`, so clear()
		// fires onChange("") but the input keeps showing the original name
		// until the parent re-renders. Type after clear fires onChange("...X")
		// — the last call's name is what we assert against.
		await user.clear(nameInput);
		await user.type(nameInput, "X");
		const last = onChange.mock.calls.at(-1)?.[0] as Policy;
		expect(last.name).toContain("X");
		expect(onChange).toHaveBeenCalled();
	});

	it("clearing description writes back null", async () => {
		const { user } = renderWithProviders(
			<PolicyEditorRow
				rowKey="row-1"
				value={baseValue}
				onChange={onChange}
				onRemove={onRemove}
			/>,
		);
		await user.clear(screen.getByLabelText(/^description$/i));
		const last = onChange.mock.calls.at(-1)?.[0] as Policy;
		expect(last.description).toBeNull();
	});
});

describe("PolicyEditorRow — actions", () => {
	it("toggling an unchecked action appends it", async () => {
		const { user } = renderWithProviders(
			<PolicyEditorRow
				rowKey="row-1"
				value={baseValue}
				onChange={onChange}
				onRemove={onRemove}
			/>,
		);
		// "create" is not in baseValue.actions
		await user.click(screen.getByLabelText("create"));
		const last = onChange.mock.calls.at(-1)?.[0] as Policy;
		expect(last.actions).toEqual(
			expect.arrayContaining(["read", "update", "create"]),
		);
	});

	it("toggling a checked action removes it", async () => {
		const { user } = renderWithProviders(
			<PolicyEditorRow
				rowKey="row-1"
				value={baseValue}
				onChange={onChange}
				onRemove={onRemove}
			/>,
		);
		await user.click(screen.getByLabelText("read"));
		const last = onChange.mock.calls.at(-1)?.[0] as Policy;
		expect(last.actions).toEqual(["update"]);
	});
});

describe("PolicyEditorRow — when JSON", () => {
	it("commits parsed JSON to onChange when valid", () => {
		renderWithProviders(
			<PolicyEditorRow
				rowKey="row-1"
				value={baseValue}
				onChange={onChange}
				onRemove={onRemove}
			/>,
		);
		const editor = screen.getByLabelText("policy-row-1.json");
		fireEvent.change(editor, {
			target: { value: '{"user": "is_platform_admin"}' },
		});
		const last = onChange.mock.calls.at(-1)?.[0] as Policy;
		expect(last.when).toEqual({ user: "is_platform_admin" });
	});

	it("surfaces a parse error and does NOT call onChange when invalid", () => {
		renderWithProviders(
			<PolicyEditorRow
				rowKey="row-1"
				value={baseValue}
				onChange={onChange}
				onRemove={onRemove}
			/>,
		);
		const editor = screen.getByLabelText("policy-row-1.json");
		// Reset onChange so we only see post-mount calls
		onChange.mockClear();
		fireEvent.change(editor, { target: { value: "{not json" } });
		expect(
			screen.getByTestId("policy-when-error-row-1"),
		).toBeInTheDocument();
		expect(onChange).not.toHaveBeenCalled();
	});

	it("empty when text commits null", () => {
		renderWithProviders(
			<PolicyEditorRow
				rowKey="row-1"
				value={baseValue}
				onChange={onChange}
				onRemove={onRemove}
			/>,
		);
		const editor = screen.getByLabelText("policy-row-1.json");
		fireEvent.change(editor, { target: { value: "" } });
		const last = onChange.mock.calls.at(-1)?.[0] as Policy;
		expect(last.when).toBeNull();
	});
});

describe("PolicyEditorRow — remove", () => {
	it("calls onRemove when the trash button is clicked", async () => {
		const { user } = renderWithProviders(
			<PolicyEditorRow
				rowKey="row-1"
				value={baseValue}
				onChange={onChange}
				onRemove={onRemove}
			/>,
		);
		await user.click(
			screen.getByRole("button", { name: /remove policy/i }),
		);
		expect(onRemove).toHaveBeenCalled();
	});
});

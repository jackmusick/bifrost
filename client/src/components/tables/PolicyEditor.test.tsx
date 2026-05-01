/**
 * Component tests for PolicyEditor.
 *
 * Monaco is stubbed (PolicyEditorRow's own tests cover the editor
 * behaviour). Here we focus on the container's responsibilities:
 * - rendering one row per policy
 * - "Add policy" button appends a blank policy
 * - inserting a template adds the template's shape (via the Select)
 * - removing a row drops it from the list and (when empty) emits null
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderWithProviders, screen, within } from "@/test-utils";
import type { ReactNode } from "react";

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

// Radix Select uses pointer events that jsdom doesn't fully implement; swap
// for a native <select> wired through a context so SelectItem children can
// register their values into the parent's <option> list.
vi.mock("@/components/ui/select", async () => {
	const React = await import("react");
	type Item = { value: string; label: string };
	const Ctx = React.createContext<{
		register: (it: Item) => void;
	} | null>(null);

	function Select({
		value,
		onValueChange,
		children,
	}: {
		value?: string;
		onValueChange?: (v: string) => void;
		children: ReactNode;
	}) {
		const [items, setItems] = React.useState<Item[]>([]);
		const register = React.useCallback((it: Item) => {
			setItems((prev) =>
				prev.some((p) => p.value === it.value) ? prev : [...prev, it],
			);
		}, []);
		return (
			<Ctx.Provider value={{ register }}>
				<select
					aria-label="Insert template"
					value={value ?? ""}
					onChange={(e) => onValueChange?.(e.target.value)}
				>
					<option value="">Insert template...</option>
					{items.map((it) => (
						<option key={it.value} value={it.value}>
							{it.label}
						</option>
					))}
				</select>
				{/* Children are rendered (invisibly) so SelectItem can register. */}
				<div style={{ display: "none" }}>{children}</div>
			</Ctx.Provider>
		);
	}
	const Pass = ({ children }: { children: ReactNode }) => <>{children}</>;
	function SelectItem({
		value,
		children,
	}: {
		value: string;
		children: ReactNode;
	}) {
		const ctx = React.useContext(Ctx);
		React.useEffect(() => {
			ctx?.register({ value, label: String(children) });
		}, [ctx, value, children]);
		return null;
	}
	return {
		Select,
		SelectContent: Pass,
		SelectGroup: Pass,
		SelectItem,
		SelectLabel: Pass,
		SelectScrollDownButton: () => null,
		SelectScrollUpButton: () => null,
		SelectSeparator: () => null,
		SelectTrigger: Pass,
		SelectValue: () => null,
	};
});

import { PolicyEditor } from "./PolicyEditor";
import type { components } from "@/lib/v1";

type TablePolicies = components["schemas"]["TablePolicies"];
type Policy = components["schemas"]["Policy"];

let onChange: ReturnType<
	typeof vi.fn<(next: TablePolicies | null) => void>
>;

beforeEach(() => {
	onChange = vi.fn<(next: TablePolicies | null) => void>();
});

function lastEmitted(): TablePolicies | null {
	return onChange.mock.calls.at(-1)?.[0] as TablePolicies | null;
}

describe("PolicyEditor — empty state", () => {
	it("renders an empty hint and no rows when value is null", () => {
		renderWithProviders(
			<PolicyEditor value={null} onChange={onChange} />,
		);
		expect(screen.getByText(/no policies/i)).toBeInTheDocument();
		expect(screen.queryByRole("textbox", { name: /^name$/i })).toBeNull();
	});

	it("Add policy emits a single-policy TablePolicies object", async () => {
		const { user } = renderWithProviders(
			<PolicyEditor value={null} onChange={onChange} />,
		);
		await user.click(screen.getByRole("button", { name: /add policy/i }));
		const emitted = lastEmitted();
		expect(emitted).not.toBeNull();
		expect(emitted!.policies).toHaveLength(1);
		expect(emitted!.policies![0]!.name).toBe("new_policy");
		expect(emitted!.policies![0]!.actions).toEqual(["read"]);
	});
});

describe("PolicyEditor — rendering rows", () => {
	it("renders one row per policy in value.policies", () => {
		const value: TablePolicies = {
			policies: [
				{ name: "p1", actions: ["read"], when: null },
				{ name: "p2", actions: ["update"], when: null },
			],
		};
		renderWithProviders(
			<PolicyEditor value={value} onChange={onChange} />,
		);
		const nameInputs = screen.getAllByLabelText(/^name$/i);
		expect(nameInputs).toHaveLength(2);
		expect(nameInputs[0]).toHaveValue("p1");
		expect(nameInputs[1]).toHaveValue("p2");
	});
});

describe("PolicyEditor — templates", () => {
	it("selecting a template inserts the template's policy", () => {
		renderWithProviders(
			<PolicyEditor value={null} onChange={onChange} />,
		);
		const select = screen.getByLabelText(
			/insert template/i,
		) as HTMLSelectElement;
		// fireEvent.change for native <select>
		select.value = "own_row";
		select.dispatchEvent(new Event("change", { bubbles: true }));
		const emitted = lastEmitted();
		expect(emitted!.policies).toHaveLength(1);
		const inserted = emitted!.policies![0]!;
		expect(inserted.name).toBe("own_row");
		expect(inserted.actions).toEqual(["read", "update", "delete"]);
		expect(inserted.when).toEqual({
			eq: [{ row: "created_by" }, { user: "user_id" }],
		});
	});

	it("template insertion is a deep copy (mutating result doesn't affect template)", () => {
		renderWithProviders(
			<PolicyEditor value={null} onChange={onChange} />,
		);
		const select = screen.getByLabelText(
			/insert template/i,
		) as HTMLSelectElement;
		select.value = "admin_bypass";
		select.dispatchEvent(new Event("change", { bubbles: true }));
		const inserted = lastEmitted()!.policies![0]! as Policy;
		(inserted.actions as string[]).push("mutate-test");
		// Insert the template again and verify the new copy is clean.
		select.value = "admin_bypass";
		select.dispatchEvent(new Event("change", { bubbles: true }));
		const second = onChange.mock.calls.at(-1)?.[0] as TablePolicies;
		const fresh = second.policies![1] ?? second.policies![0];
		expect(fresh!.actions).toEqual([
			"read",
			"create",
			"update",
			"delete",
		]);
	});
});

describe("PolicyEditor — remove", () => {
	it("removing the last row collapses to null", async () => {
		const value: TablePolicies = {
			policies: [{ name: "lone", actions: ["read"], when: null }],
		};
		const { user } = renderWithProviders(
			<PolicyEditor value={value} onChange={onChange} />,
		);
		const row = screen.getByTestId(/^policy-row-/);
		await user.click(
			within(row).getByRole("button", { name: /remove policy/i }),
		);
		expect(lastEmitted()).toBeNull();
	});

	it("removing one of N rows leaves the rest", async () => {
		const value: TablePolicies = {
			policies: [
				{ name: "a", actions: ["read"], when: null },
				{ name: "b", actions: ["update"], when: null },
			],
		};
		const { user } = renderWithProviders(
			<PolicyEditor value={value} onChange={onChange} />,
		);
		const rows = screen.getAllByTestId(/^policy-row-/);
		await user.click(
			within(rows[0]!).getByRole("button", { name: /remove policy/i }),
		);
		const emitted = lastEmitted();
		expect(emitted!.policies).toHaveLength(1);
		expect(emitted!.policies![0]!.name).toBe("b");
	});
});

describe("PolicyEditor — reference panel", () => {
	it("Reference button opens the side sheet", async () => {
		const { user } = renderWithProviders(
			<PolicyEditor value={null} onChange={onChange} />,
		);
		await user.click(screen.getByRole("button", { name: /reference/i }));
		expect(screen.getByText(/policy reference/i)).toBeInTheDocument();
		expect(screen.getByText(/USER fields/i)).toBeInTheDocument();
		expect(screen.getByText(/Operators/i)).toBeInTheDocument();
	});
});

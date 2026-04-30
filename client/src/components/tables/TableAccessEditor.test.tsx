import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { TableAccessEditor } from "./TableAccessEditor";

describe("TableAccessEditor", () => {
	it("renders 8 base checkboxes (Everyone + Creator × 4 each)", () => {
		render(<TableAccessEditor value={null} roles={[]} onChange={() => {}} />);
		expect(screen.getByText(/Everyone/)).toBeInTheDocument();
		expect(screen.getByText(/Creator/)).toBeInTheDocument();
		// 4 for Everyone + 4 for Creator = 8 base checkboxes (no role grant rows)
		expect(screen.getAllByRole("checkbox").length).toBe(8);
	});

	it("toggling Everyone—Read calls onChange with everyone.read=true", () => {
		const handler = vi.fn();
		render(<TableAccessEditor value={null} roles={[]} onChange={handler} />);
		const checkbox = screen.getByLabelText(/Everyone — read/i);
		fireEvent.click(checkbox);
		expect(handler).toHaveBeenCalled();
		const arg = handler.mock.calls[0][0];
		expect(arg.everyone.read).toBe(true);
	});

	it("Add row button appends a role grant row with 4 more checkboxes", () => {
		const handler = vi.fn();
		render(<TableAccessEditor value={null} roles={[]} onChange={handler} />);
		const addBtn = screen.getByText("+ Add row");
		fireEvent.click(addBtn);
		expect(handler).toHaveBeenCalled();
		const arg = handler.mock.calls[0][0];
		expect(Array.isArray(arg.roles)).toBe(true);
		expect(arg.roles).toHaveLength(1);
		expect(arg.roles[0].read).toBe(false);
	});

	it("renders role grant rows when value has roles", () => {
		render(
			<TableAccessEditor
				value={{
					everyone: { read: false, create: false, update: false, delete: false },
					roles: [
						{
							roles: ["r1"],
							read: true,
							create: false,
							update: false,
							delete: false,
						},
					],
					creator: {
						read: false,
						create: false,
						update: false,
						delete: false,
					},
				}}
				roles={[{ id: "r1", name: "Admins" }]}
				onChange={() => {}}
			/>,
		);
		// 8 base + 4 from 1 role grant = 12
		expect(screen.getAllByRole("checkbox").length).toBe(12);
	});

	it("two role grants produce roles with 2 entries", () => {
		const handler = vi.fn();
		const initialAccess = {
			everyone: { read: false, create: false, update: false, delete: false },
			roles: [
				{ roles: [], read: false, create: false, update: false, delete: false },
				{ roles: [], read: false, create: false, update: false, delete: false },
			],
			creator: { read: false, create: false, update: false, delete: false },
		};
		render(
			<TableAccessEditor
				value={initialAccess}
				roles={[]}
				onChange={handler}
			/>,
		);
		// 8 base + 4+4 = 16 checkboxes
		expect(screen.getAllByRole("checkbox").length).toBe(16);

		// Toggle first grant's "read" checkbox (aria-label "Role grant 1 — read")
		const firstRead = screen.getByLabelText(/Role grant 1 — read/i);
		fireEvent.click(firstRead);
		expect(handler).toHaveBeenCalled();
		const arg = handler.mock.calls[0][0];
		expect(arg.roles).toHaveLength(2);
		expect(arg.roles[0].read).toBe(true);
		expect(arg.roles[1].read).toBe(false);
	});
});

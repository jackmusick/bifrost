/**
 * Component tests for TodoList.
 *
 * Cover: empty state (renders null), progress count, per-status rendering
 * (pending / in_progress / completed), and in-progress uses active_form
 * label rather than content.
 *
 * We stub framer-motion to plain divs so animation refs don't delay assertions.
 */

import React from "react";
import { describe, it, expect, vi } from "vitest";
import { renderWithProviders, screen } from "@/test-utils";

vi.mock("framer-motion", () => {
	const passthrough = ({
		children,
		initial: _i,
		animate: _a,
		exit: _e,
		transition: _t,
		...rest
	}: Record<string, unknown> & { children?: React.ReactNode }) => (
		<div {...(rest as Record<string, unknown>)}>{children}</div>
	);
	return {
		motion: new Proxy({}, { get: () => passthrough }),
		AnimatePresence: ({ children }: { children: React.ReactNode }) => (
			<>{children}</>
		),
	};
});

import { TodoList } from "./TodoList";
import type { TodoItem } from "@/services/websocket";

function makeTodo(overrides: Partial<TodoItem>): TodoItem {
	return {
		content: "Do the thing",
		status: "pending",
		active_form: "Doing the thing",
		...overrides,
	};
}

describe("TodoList", () => {
	it("renders null when the list is empty", () => {
		const { container } = renderWithProviders(<TodoList todos={[]} />);
		expect(container.firstChild).toBeNull();
	});

	it("renders each todo's content and header progress", () => {
		renderWithProviders(
			<TodoList
				todos={[
					makeTodo({ content: "Task A", status: "pending" }),
					makeTodo({ content: "Task B", status: "completed" }),
					makeTodo({ content: "Task C", status: "completed" }),
				]}
			/>,
		);
		expect(screen.getByText(/task progress/i)).toBeInTheDocument();
		// Completed 2/3.
		expect(screen.getByText("2/3")).toBeInTheDocument();
		expect(screen.getByText("Task A")).toBeInTheDocument();
		expect(screen.getByText("Task B")).toBeInTheDocument();
		expect(screen.getByText("Task C")).toBeInTheDocument();
	});

	it("shows the active_form label for an in_progress item instead of content", () => {
		renderWithProviders(
			<TodoList
				todos={[
					makeTodo({
						content: "Run tests",
						active_form: "Running tests",
						status: "in_progress",
					}),
				]}
			/>,
		);
		expect(screen.getByText("Running tests")).toBeInTheDocument();
		expect(screen.queryByText("Run tests")).not.toBeInTheDocument();
	});

	it("adds the line-through styling for completed items", () => {
		renderWithProviders(
			<TodoList
				todos={[makeTodo({ content: "Done", status: "completed" })]}
			/>,
		);
		const item = screen.getByText("Done");
		expect(item.className).toMatch(/line-through/);
	});
});

/**
 * Pins the DialogContent sizing/scroll contract and the CommandDialog
 * backward-compat contract.
 *
 * Why these exist (spike/shadcn-luma regressions):
 *   - The Rhea base originally used `sm:max-w-md`, which tailwind-merge does
 *     NOT merge against consumers' unprefixed `max-w-2xl`/`max-w-[90vw]` —
 *     the media-scoped rule won at >=640px and every wide dialog rendered
 *     448px. Sizing must stay in unprefixed classes (see dialog.tsx comment).
 *   - The base lost `max-h-[90vh] overflow-y-auto`; ~54 call sites rely on
 *     internal scrolling for tall content.
 *   - CommandDialog stopped auto-wrapping children in <Command>, crashing
 *     already-built v2 app bundles (bifrost-runtime contract), and flipped
 *     the showCloseButton default from true to false.
 */

import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

import { Dialog, DialogContent, DialogTitle, DialogDescription } from "./dialog";
import { CommandDialog, CommandInput, CommandList, CommandItem } from "./command";

function renderDialogContent(className?: string) {
	render(
		<Dialog open>
			<DialogContent className={className}>
				<DialogTitle>Title</DialogTitle>
				<DialogDescription>Description</DialogDescription>
			</DialogContent>
		</Dialog>,
	);
	const content = document.querySelector('[data-slot="dialog-content"]');
	expect(content).not.toBeNull();
	return (content as HTMLElement).className.split(/\s+/);
}

describe("DialogContent sizing contract", () => {
	it("defaults: unprefixed max-w, viewport gutter on the w- group, internal scrolling", () => {
		const classes = renderDialogContent();
		expect(classes).toContain("max-w-md");
		expect(classes).toContain("w-[calc(100%-2rem)]");
		expect(classes).toContain("max-h-[90vh]");
		expect(classes).toContain("overflow-y-auto");
		// The landmine: a breakpoint-scoped max-w default silently beats
		// consumers' unprefixed max-w overrides at >=640px.
		expect(classes.filter((c) => c.startsWith("sm:max-w"))).toEqual([]);
	});

	it("consumer unprefixed max-w override wins and keeps the mobile gutter", () => {
		const classes = renderDialogContent("max-w-4xl");
		expect(classes).toContain("max-w-4xl");
		expect(classes).not.toContain("max-w-md");
		// Gutter survives because it lives on w-, not max-w-.
		expect(classes).toContain("w-[calc(100%-2rem)]");
	});

	it("consumer arbitrary max-w override wins", () => {
		const classes = renderDialogContent("max-w-[90vw] h-[80vh]");
		expect(classes).toContain("max-w-[90vw]");
		expect(classes).not.toContain("max-w-md");
	});

	it("consumer sm:-scoped max-w coexists with the mobile default", () => {
		const classes = renderDialogContent("sm:max-w-[760px]");
		expect(classes).toContain("sm:max-w-[760px]");
		// Below sm the base default still applies.
		expect(classes).toContain("max-w-md");
	});

	it("consumer max-h / overflow overrides win over the internal-scroll default", () => {
		const classes = renderDialogContent("max-h-[85vh] overflow-hidden flex flex-col");
		expect(classes).toContain("max-h-[85vh]");
		expect(classes).not.toContain("max-h-[90vh]");
		expect(classes).toContain("overflow-hidden");
		expect(classes).not.toContain("overflow-y-auto");
		expect(classes).toContain("flex");
		expect(classes).not.toContain("grid");
	});
});

describe("CommandDialog backward-compat contract", () => {
	it("auto-wraps children in a single <Command> so bare CommandInput/List children get cmdk context", () => {
		render(
			<CommandDialog open title="Palette" description="desc">
				<CommandInput placeholder="type here" />
				<CommandList>
					<CommandItem value="one">Item one</CommandItem>
				</CommandList>
			</CommandDialog>,
		);
		// Would throw before render if the cmdk context were missing.
		expect(screen.getByPlaceholderText("type here")).toBeInTheDocument();
		expect(screen.getByText("Item one")).toBeInTheDocument();
		const content = document.querySelector('[data-slot="dialog-content"]');
		expect(content).not.toBeNull();
		expect(
			(content as HTMLElement).querySelectorAll('[data-slot="command"]'),
		).toHaveLength(1);
	});

	it("does not double-wrap when commandProps are forwarded", () => {
		render(
			<CommandDialog open commandProps={{ shouldFilter: false }}>
				<CommandList>
					<CommandItem value="one">Item one</CommandItem>
				</CommandList>
			</CommandDialog>,
		);
		expect(
			document.querySelectorAll('[data-slot="command"]'),
		).toHaveLength(1);
	});

	it("defaults showCloseButton to true (the published runtime default)", () => {
		render(
			<CommandDialog open>
				<CommandList />
			</CommandDialog>,
		);
		expect(screen.getByText("Close")).toBeInTheDocument();
	});

	it("renders the sr-only header INSIDE DialogContent (absent from the a11y tree when closed)", () => {
		const { rerender } = render(
			<CommandDialog open={false} title="Quick access">
				<CommandList />
			</CommandDialog>,
		);
		expect(screen.queryByText("Quick access")).not.toBeInTheDocument();

		rerender(
			<CommandDialog open title="Quick access">
				<CommandList />
			</CommandDialog>,
		);
		const title = screen.getByText("Quick access");
		expect(title.closest('[data-slot="dialog-content"]')).not.toBeNull();
	});
});

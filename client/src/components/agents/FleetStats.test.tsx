import { describe, it, expect, vi } from "vitest";
import { renderWithProviders, screen } from "@/test-utils";
import type { components } from "@/lib/v1";

import { FleetStats } from "./FleetStats";

type FleetStatsResponse = components["schemas"]["FleetStatsResponse"];

const baseStats: FleetStatsResponse = {
	total_runs: 1234,
	avg_success_rate: 0.92,
	total_cost_7d: "8.47",
	active_agents: 5,
	needs_review: 3,
};

describe("FleetStats", () => {
	it("renders the runs label and formatted total", () => {
		renderWithProviders(<FleetStats stats={baseStats} />);
		expect(screen.getByText(/runs \(7d\)/i)).toBeInTheDocument();
		expect(screen.getByText("1,234")).toBeInTheDocument();
	});

	it("renders the success-rate percentage", () => {
		renderWithProviders(<FleetStats stats={baseStats} />);
		expect(screen.getByText("92%")).toBeInTheDocument();
	});

	it("renders the spend card with formatted currency", () => {
		renderWithProviders(<FleetStats stats={baseStats} />);
		expect(screen.getByText(/spend \(7d\)/i)).toBeInTheDocument();
		expect(screen.getByText("$8.47")).toBeInTheDocument();
	});

	it("renders the active agents count", () => {
		renderWithProviders(<FleetStats stats={baseStats} />);
		expect(screen.getByText(/active agents/i)).toBeInTheDocument();
		expect(screen.getByText("5")).toBeInTheDocument();
	});

	it("renders needs-review and is clickable when count > 0", async () => {
		const onClick = vi.fn();
		const { user } = renderWithProviders(
			<FleetStats stats={baseStats} onNeedsReviewClick={onClick} />,
		);
		expect(screen.getByText(/needs review/i)).toBeInTheDocument();
		expect(screen.getByText("3")).toBeInTheDocument();
		// Find the parent button (needs-review card is interactive)
		await user.click(screen.getByRole("button", { name: /needs review/i }));
		expect(onClick).toHaveBeenCalled();
	});

	it("does not make needs-review interactive when count is 0", () => {
		const stats = { ...baseStats, needs_review: 0 };
		renderWithProviders(
			<FleetStats stats={stats} onNeedsReviewClick={() => {}} />,
		);
		expect(
			screen.queryByRole("button", { name: /needs review/i }),
		).not.toBeInTheDocument();
	});

	it("renders sparkline when runsByDay has multiple values", () => {
		const { container } = renderWithProviders(
			<FleetStats stats={baseStats} runsByDay={[1, 2, 3, 4, 5]} />,
		);
		// SVG sparkline rendered for the runs card
		expect(container.querySelector("svg")).not.toBeNull();
	});
});

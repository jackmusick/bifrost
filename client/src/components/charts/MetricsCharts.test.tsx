import { describe, expect, it, vi } from "vitest";
import { renderWithProviders, screen } from "@/test-utils";
import { ResourceTrendChart } from "./ResourceTrendChart";
import { ExecutionsByOrgChart } from "./ExecutionsByOrgChart";
import { HeaviestWorkflowsTable } from "./HeaviestWorkflowsTable";

describe("Platform analytics charts", () => {
	it("ResourceTrendChart shows an error alert when the query fails", () => {
		renderWithProviders(
			<ResourceTrendChart
				data={[]}
				isError
				error={new Error("metrics unavailable")}
			/>,
		);

		expect(
			screen.getByText(/Failed to load resource metrics: metrics unavailable/i),
		).toBeInTheDocument();
		expect(
			screen.queryByText(/No resource data available/i),
		).not.toBeInTheDocument();
	});

	it("ResourceTrendChart shows empty state only after a successful query", () => {
		renderWithProviders(<ResourceTrendChart data={[]} />);

		expect(
			screen.getByText(/No resource data available/i),
		).toBeInTheDocument();
	});

	it("ExecutionsByOrgChart shows an error alert when the query fails", () => {
		renderWithProviders(
			<ExecutionsByOrgChart
				data={[]}
				isError
				error={new Error("forbidden")}
			/>,
		);

		expect(
			screen.getByText(/Failed to load organization metrics: forbidden/i),
		).toBeInTheDocument();
		expect(
			screen.queryByText(/No organization data available/i),
		).not.toBeInTheDocument();
	});

	it("HeaviestWorkflowsTable shows an error alert when the query fails", () => {
		renderWithProviders(
			<HeaviestWorkflowsTable
				data={[]}
				isError
				error={new Error("upstream timeout")}
				sortBy="memory"
				onSortChange={vi.fn()}
			/>,
		);

		expect(
			screen.getByText(
				/Failed to load workflow metrics: upstream timeout/i,
			),
		).toBeInTheDocument();
		expect(
			screen.queryByText(/No workflow data available/i),
		).not.toBeInTheDocument();
	});
});

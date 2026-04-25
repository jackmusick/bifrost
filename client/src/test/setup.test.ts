import { describe, expect, it } from "vitest";

/**
 * Smoke test proving the Vitest + happy-dom + jest-dom setup is wired up.
 * Keep this file tiny. Real component tests live next to their components.
 */
describe("test infrastructure", () => {
	it("has a DOM available", () => {
		const el = document.createElement("div");
		el.textContent = "ok";
		document.body.appendChild(el);
		expect(el).toBeInTheDocument();
		expect(el.textContent).toBe("ok");
	});
});

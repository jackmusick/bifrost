import { describe, expect, it } from "vitest";
import {
	DEFAULT_TERMINOLOGY,
	mergeTerminology,
	term,
} from "./terminology";

describe("terminology", () => {
	it("uses default platform nouns when branding does not override them", () => {
		const terminology = mergeTerminology(null);

		expect(terminology).toEqual(DEFAULT_TERMINOLOGY);
		expect(term(terminology, "app", "singular")).toBe("App");
		expect(term(terminology, "app", "formalPlural")).toBe("Applications");
		expect(term(terminology, "agent", "plural")).toBe("Agents");
		expect(term(terminology, "form", "plural")).toBe("Forms");
	});

	it("merges fixed branding terminology without losing unspecified labels", () => {
		const terminology = mergeTerminology({
			app: { singular: "Game", plural: "Games" },
			agent: { singular: "Character", plural: "Characters" },
			form: { singular: "Quest", plural: "Quests" },
		});

		expect(term(terminology, "app", "singular")).toBe("Game");
		expect(term(terminology, "app", "formalSingular")).toBe("Game");
		expect(term(terminology, "app", "formalPlural")).toBe("Games");
		expect(term(terminology, "agent", "plural")).toBe("Characters");
		expect(term(terminology, "form", "singularLower")).toBe("quest");
	});
});

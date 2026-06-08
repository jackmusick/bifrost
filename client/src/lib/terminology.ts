import { createContext, useContext } from "react";

export type ProductTermKey = "app" | "agent" | "form";

export type ProductTerm = {
	singular: string;
	plural: string;
	formalSingular: string;
	formalPlural: string;
	singularLower: string;
	pluralLower: string;
	formalSingularLower: string;
	formalPluralLower: string;
};

export type Terminology = Record<ProductTermKey, ProductTerm>;

export type BrandingTerminologyInput = Partial<
	Record<ProductTermKey, { singular?: string | null; plural?: string | null }>
>;

function buildTerm(
	singular: string,
	plural: string,
	formalSingular = singular,
	formalPlural = plural,
): ProductTerm {
	return {
		singular,
		plural,
		formalSingular,
		formalPlural,
		singularLower: singular.toLowerCase(),
		pluralLower: plural.toLowerCase(),
		formalSingularLower: formalSingular.toLowerCase(),
		formalPluralLower: formalPlural.toLowerCase(),
	};
}

export const DEFAULT_TERMINOLOGY: Terminology = {
	app: buildTerm("App", "Apps", "Application", "Applications"),
	agent: buildTerm("Agent", "Agents"),
	form: buildTerm("Form", "Forms"),
};

function cleanLabel(value: string | null | undefined): string | null {
	const trimmed = value?.trim();
	return trimmed ? trimmed : null;
}

export function mergeTerminology(
	brandingTerminology: BrandingTerminologyInput | null | undefined,
): Terminology {
	if (!brandingTerminology) {
		return DEFAULT_TERMINOLOGY;
	}

	const appSingular =
		cleanLabel(brandingTerminology.app?.singular) ??
		DEFAULT_TERMINOLOGY.app.singular;
	const appPlural =
		cleanLabel(brandingTerminology.app?.plural) ??
		DEFAULT_TERMINOLOGY.app.plural;
	const agentSingular =
		cleanLabel(brandingTerminology.agent?.singular) ??
		DEFAULT_TERMINOLOGY.agent.singular;
	const agentPlural =
		cleanLabel(brandingTerminology.agent?.plural) ??
		DEFAULT_TERMINOLOGY.agent.plural;
	const formSingular =
		cleanLabel(brandingTerminology.form?.singular) ??
		DEFAULT_TERMINOLOGY.form.singular;
	const formPlural =
		cleanLabel(brandingTerminology.form?.plural) ??
		DEFAULT_TERMINOLOGY.form.plural;

	return {
		app: buildTerm(appSingular, appPlural, appSingular, appPlural),
		agent: buildTerm(agentSingular, agentPlural),
		form: buildTerm(formSingular, formPlural),
	};
}

export function serializeTerminology(
	terminology: Terminology,
): Required<BrandingTerminologyInput> {
	return {
		app: {
			singular: terminology.app.singular,
			plural: terminology.app.plural,
		},
		agent: {
			singular: terminology.agent.singular,
			plural: terminology.agent.plural,
		},
		form: {
			singular: terminology.form.singular,
			plural: terminology.form.plural,
		},
	};
}

export function term(
	terminology: Terminology,
	key: ProductTermKey,
	variant: keyof ProductTerm,
): string {
	return terminology[key][variant];
}

export const TerminologyContext =
	createContext<Terminology>(DEFAULT_TERMINOLOGY);

export function useTerminology() {
	return useContext(TerminologyContext);
}

/**
 * ModelPicker — subtle inline model selector for the chat composer.
 *
 * Pulls the user's effective model context from /api/chat/model-context
 * (org allowlist + resolved default), and renders a compact ghost-styled
 * <ModelSelect /> filtered per the rules:
 *
 *   - Empty allowlist → only the resolved default is selectable. This is
 *     the cost-protection guardrail when no admin has configured one.
 *   - Non-empty allowlist → only those models are selectable.
 *
 * `value` (the conversation's current_model) defaults to whatever the
 * resolver's default would land on, so the trigger always shows something.
 */

import { useEffect, useMemo, useState } from "react";

import {
	listPlatformModels,
	resellerForEndpoint,
	type PlatformModel,
} from "@/services/platformModels";
import { $api } from "@/lib/api-client";
import { ModelSelect, type ModelSelectModel } from "./ModelSelect";

interface ModelPickerProps {
	value: string | null | undefined;
	onChange: (modelId: string) => void;
	disabled?: boolean;
}

export function ModelPicker({
	value,
	onChange,
	disabled = false,
}: ModelPickerProps) {
	const [catalog, setCatalog] = useState<PlatformModel[]>([]);
	useEffect(() => {
		let cancelled = false;
		listPlatformModels()
			.then((res) => {
				if (!cancelled) setCatalog(res.models);
			})
			.catch(() => {
				/* ignore — picker still works without enriched info */
			});
		return () => {
			cancelled = true;
		};
	}, []);

	const llmConfigQuery = $api.useQuery(
		"get",
		"/api/admin/llm/config",
		undefined,
		{ staleTime: 5 * 60 * 1000 },
	);
	const reseller = resellerForEndpoint(llmConfigQuery.data?.endpoint ?? null);

	const providerModelsQuery = $api.useQuery(
		"get",
		"/api/admin/llm/models",
		undefined,
		{ retry: false, staleTime: 5 * 60 * 1000 },
	);
	const providerModels: ModelSelectModel[] =
		providerModelsQuery.data?.models ?? [];

	const contextQuery = $api.useQuery(
		"get",
		"/api/chat/model-context",
		undefined,
		{ staleTime: 60 * 1000 },
	);

	const allowlist = contextQuery.data?.allowed_chat_models ?? [];
	const defaultId = contextQuery.data?.default_chat_model ?? null;

	// Apply the picker rules:
	//   non-empty allowlist → restrict to those entries
	//   empty allowlist     → restrict to just the default (one row)
	//   no default + no allowlist → don't restrict (provider's full catalog,
	//   though the chat probably can't be created in that state anyway).
	const restrictToIds: string[] | undefined = useMemo(() => {
		if (allowlist.length > 0) return allowlist;
		if (defaultId) return [defaultId];
		return undefined;
	}, [allowlist, defaultId]);

	const catalogById = useMemo(() => {
		const idx: Record<string, PlatformModel> = {};
		for (const m of catalog) idx[m.model_id] = m;
		return idx;
	}, [catalog]);

	// Show the resolved default in the trigger when the conversation hasn't
	// pinned a different model yet.
	const effectiveValue = value ?? defaultId ?? null;

	return (
		<ModelSelect
			compact
			models={providerModels}
			catalog={catalogById}
			reseller={reseller}
			restrictToIds={restrictToIds}
			value={effectiveValue}
			onChange={(v) => v && onChange(v)}
			disabled={disabled}
			placeholder="Model"
		/>
	);
}

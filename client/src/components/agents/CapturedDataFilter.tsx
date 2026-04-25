/**
 * Captured Data filter — key/op/value repeater for the agent runs list.
 *
 * Each row: key combobox (populated from the agent's known metadata keys)
 * + op picker (contains / equals, default contains) + value input. When op
 * is 'equals', the value input becomes a combobox of known values for the
 * chosen key. All rows AND together. Scope is per-agent.
 *
 * Parent owns the condition array via `value` / `onChange`; this component
 * is pure UI. Use `conditionsToQueryParam` to serialize into the
 * `metadataFilter` string the runs-list service expects.
 */

import { Plus, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Combobox } from "@/components/ui/combobox";
import { Input } from "@/components/ui/input";
import {
	Select,
	SelectContent,
	SelectItem,
	SelectTrigger,
	SelectValue,
} from "@/components/ui/select";
import { useMetadataKeys, useMetadataValues } from "@/services/agentRuns";

export type MetadataFilterOp = "eq" | "contains";

export interface MetadataFilterCondition {
	key: string;
	op: MetadataFilterOp;
	value: string;
}

export interface CapturedDataFilterProps {
	agentId: string;
	value: MetadataFilterCondition[];
	onChange: (conditions: MetadataFilterCondition[]) => void;
}

/** Serialize conditions into the `metadata_filter` query-string value. */
export function conditionsToQueryParam(
	conditions: MetadataFilterCondition[],
): string | undefined {
	const complete = conditions.filter((c) => c.key && c.value);
	if (complete.length === 0) return undefined;
	return JSON.stringify(complete);
}

export function CapturedDataFilter({
	agentId,
	value,
	onChange,
}: CapturedDataFilterProps) {
	function addRow() {
		onChange([...value, { key: "", op: "contains", value: "" }]);
	}
	function updateRow(i: number, patch: Partial<MetadataFilterCondition>) {
		const next = value.map((row, idx) =>
			idx === i ? { ...row, ...patch } : row,
		);
		onChange(next);
	}
	function removeRow(i: number) {
		onChange(value.filter((_, idx) => idx !== i));
	}

	return (
		<div className="flex flex-col gap-2" data-testid="captured-data-filter">
			{value.map((row, i) => (
				<ConditionRow
					key={i}
					agentId={agentId}
					condition={row}
					onChange={(patch) => updateRow(i, patch)}
					onRemove={() => removeRow(i)}
				/>
			))}
			<div>
				<Button
					type="button"
					variant="outline"
					size="sm"
					onClick={addRow}
					className="gap-1.5"
					aria-label="Add captured data filter"
				>
					<Plus className="h-3.5 w-3.5" />
					{value.length === 0
						? "Filter captured data"
						: "Add another"}
				</Button>
			</div>
		</div>
	);
}

interface ConditionRowProps {
	agentId: string;
	condition: MetadataFilterCondition;
	onChange: (patch: Partial<MetadataFilterCondition>) => void;
	onRemove: () => void;
}

function ConditionRow({
	agentId,
	condition,
	onChange,
	onRemove,
}: ConditionRowProps) {
	const { data: keysResp, isLoading: keysLoading } = useMetadataKeys(agentId);
	const { data: valuesResp, isLoading: valuesLoading } = useMetadataValues(
		agentId,
		condition.op === "eq" ? condition.key : undefined,
	);
	const keyOptions = (keysResp?.keys ?? []).map((k) => ({
		value: k,
		label: k,
	}));
	const valueOptions = (valuesResp?.values ?? []).map((v) => ({
		value: v,
		label: v,
	}));

	return (
		<div className="flex flex-wrap items-center gap-2">
			<Combobox
				options={keyOptions}
				value={condition.key || undefined}
				onValueChange={(v) => onChange({ key: v })}
				placeholder="Pick key…"
				searchPlaceholder="Search keys…"
				emptyText={
					keysLoading ? "Loading…" : "No metadata keys yet for this agent."
				}
				isLoading={keysLoading}
				className="w-[180px]"
			/>
			<Select
				value={condition.op}
				onValueChange={(v) => onChange({ op: v as MetadataFilterOp })}
			>
				<SelectTrigger
					className="w-[120px]"
					aria-label="Captured data filter operator"
				>
					<SelectValue />
				</SelectTrigger>
				<SelectContent>
					<SelectItem value="contains">contains</SelectItem>
					<SelectItem value="eq">equals</SelectItem>
				</SelectContent>
			</Select>
			{condition.op === "eq" ? (
				<Combobox
					options={valueOptions}
					value={condition.value || undefined}
					onValueChange={(v) => onChange({ value: v })}
					placeholder="Pick value…"
					searchPlaceholder="Search values…"
					emptyText={
						valuesLoading
							? "Loading…"
							: condition.key
								? "No values recorded."
								: "Pick a key first."
					}
					isLoading={valuesLoading}
					className="w-[220px]"
				/>
			) : (
				<Input
					value={condition.value}
					onChange={(e) => onChange({ value: e.target.value })}
					placeholder="substring…"
					className="w-[220px]"
					aria-label="Captured data filter value"
				/>
			)}
			<Button
				type="button"
				variant="ghost"
				size="sm"
				onClick={onRemove}
				aria-label="Remove filter row"
				className="h-8 w-8 p-0"
			>
				<X className="h-3.5 w-3.5" />
			</Button>
		</div>
	);
}

/**
 * Top-level policy editor — renders a list of `PolicyEditorRow`s plus a
 * template picker, an "Add policy" button, and a "Reference" button that
 * opens the side `PolicyReferencePanel`.
 *
 * Owns no submission concern of its own; the parent (e.g. `TableDialog`)
 * passes the current `TablePolicies | null` and a setter, and is responsible
 * for shipping the resulting structure in the create/update request body.
 */

import { useId, useState } from "react";
import { Plus } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
	Select,
	SelectContent,
	SelectItem,
	SelectTrigger,
	SelectValue,
} from "@/components/ui/select";

import { PolicyEditorRow } from "./PolicyEditorRow";
import { PolicyReferencePanel } from "./PolicyReferencePanel";
import {
	POLICY_TEMPLATES,
	instantiateTemplate,
	type Policy,
	type PolicyTemplateKey,
} from "./policy-templates";
import type { components } from "@/lib/v1";

type TablePolicies = components["schemas"]["TablePolicies"];

export interface PolicyEditorProps {
	value: TablePolicies | null;
	onChange: (next: TablePolicies | null) => void;
}

export function PolicyEditor({ value, onChange }: PolicyEditorProps) {
	const policies: Policy[] = value?.policies ?? [];
	const [showRef, setShowRef] = useState(false);
	const [templateKey, setTemplateKey] = useState<string>("");
	const idPrefix = useId();

	function commit(next: Policy[]) {
		// Empty policy list collapses back to null so we don't persist
		// `{policies: []}` and accidentally lock the table down for everyone.
		onChange(next.length === 0 ? null : { policies: next });
	}

	function handleTemplate(key: string) {
		if (!key) return;
		const tpl = instantiateTemplate(key as PolicyTemplateKey);
		commit([...policies, tpl]);
		// Reset the trigger so the same template can be re-inserted next time.
		setTemplateKey("");
	}

	function addBlank() {
		commit([
			...policies,
			{
				name: "new_policy",
				description: null,
				actions: ["read"],
				when: null,
			},
		]);
	}

	function update(index: number, next: Policy) {
		commit(policies.map((p, i) => (i === index ? next : p)));
	}

	function remove(index: number) {
		commit(policies.filter((_, i) => i !== index));
	}

	return (
		<div className="space-y-3">
			<div className="flex justify-between items-center">
				<h3 className="text-sm font-medium">Policies</h3>
				<div className="flex gap-2">
					<Select value={templateKey} onValueChange={handleTemplate}>
						<SelectTrigger
							className="w-[200px]"
							aria-label="Insert template"
						>
							<SelectValue placeholder="Insert template..." />
						</SelectTrigger>
						<SelectContent>
							{Object.keys(POLICY_TEMPLATES).map((k) => (
								<SelectItem key={k} value={k}>
									{k}
								</SelectItem>
							))}
						</SelectContent>
					</Select>
					<Button
						type="button"
						variant="ghost"
						size="sm"
						onClick={() => setShowRef(true)}
					>
						Reference
					</Button>
				</div>
			</div>

			{policies.length === 0 ? (
				<p className="text-sm text-muted-foreground">
					No policies. Without a policy, only the table owner and
					platform admins can access rows. Use a template or click
					"Add policy" to start.
				</p>
			) : (
				<div className="space-y-3">
					{policies.map((p, i) => (
						<PolicyEditorRow
							key={`${idPrefix}-${i}`}
							rowKey={`${idPrefix}-${i}`}
							value={p}
							onChange={(next) => update(i, next)}
							onRemove={() => remove(i)}
						/>
					))}
				</div>
			)}

			<Button
				type="button"
				variant="outline"
				size="sm"
				onClick={addBlank}
			>
				<Plus className="h-4 w-4 mr-1" />
				Add policy
			</Button>

			<PolicyReferencePanel
				open={showRef}
				onClose={() => setShowRef(false)}
			/>
		</div>
	);
}

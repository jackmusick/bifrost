/**
 * One row of the PolicyEditor — name + description + actions checkboxes +
 * Monaco JSON editor for the `when` expression.
 *
 * The Monaco component is schema-bound via the imported policy-schema.json
 * (see `client/src/lib/app-sdk/policy-schema.json`). The schema gives the
 * editor a baseline of completion and validation hints, even though the
 * authoritative validator is the Pydantic AST on the server.
 */

import { useState, useMemo } from "react";
import Editor, { type OnMount } from "@monaco-editor/react";
import type * as Monaco from "monaco-editor";
import { Trash2 } from "lucide-react";

import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { useTheme } from "@/contexts/ThemeContext";

import schema from "@/lib/app-sdk/policy-schema.json";
import type { Policy } from "./policy-templates";

const ACTIONS = ["read", "create", "update", "delete"] as const;
type Action = (typeof ACTIONS)[number];

const SCHEMA_URI = "inmemory://policy-schema.json";

interface MonacoJsonDefaults {
	diagnosticsOptions: {
		schemas?: { uri: string; fileMatch?: string[]; schema: unknown }[];
	};
	setDiagnosticsOptions: (options: {
		validate?: boolean;
		allowComments?: boolean;
		schemas?: { uri: string; fileMatch?: string[]; schema: unknown }[];
	}) => void;
}

function configureMonacoSchema(monaco: typeof Monaco) {
	// monaco.languages.json is marked deprecated in the type defs but is the
	// runtime API for JSON language features. Cast through to access it.
	const json = (
		monaco.languages as unknown as { json: { jsonDefaults: MonacoJsonDefaults } }
	).json;
	const existing = json.jsonDefaults.diagnosticsOptions.schemas ?? [];
	if (existing.some((s) => s.uri === SCHEMA_URI)) return;
	json.jsonDefaults.setDiagnosticsOptions({
		validate: true,
		allowComments: false,
		schemas: [
			...existing,
			{
				uri: SCHEMA_URI,
				fileMatch: ["*"],
				schema,
			},
		],
	});
}

export interface PolicyEditorRowProps {
	value: Policy;
	onChange: (next: Policy) => void;
	onRemove: () => void;
	/** Stable id — used as the Monaco label so multiple rows don't fight. */
	rowKey: string;
}

export function PolicyEditorRow({
	value,
	onChange,
	onRemove,
	rowKey,
}: PolicyEditorRowProps) {
	const { theme } = useTheme();

	// Local text buffer so an in-progress invalid edit doesn't get reverted
	// out from under the user (we only commit when JSON.parse succeeds).
	const initialText = useMemo(
		() => JSON.stringify(value.when ?? null, null, 2),
		// Initial value only — external `value.when` resets are reconciled in
		// the render-phase block below. Recomputing this memo on every change
		// would clobber the editor mid-typing.
		// eslint-disable-next-line react-hooks/exhaustive-deps
		[],
	);
	const [whenText, setWhenText] = useState(initialText);
	const [parseError, setParseError] = useState<string | null>(null);
	// Tracks the most recent canonical text we either emitted ourselves or
	// last synced from props. Stored as state (not a ref) so the render-phase
	// reset below doesn't trip the no-refs-in-render lint.
	const [lastSynced, setLastSynced] = useState(initialText);

	// Render-phase: when the parent hands us a different `value.when` than
	// the one we last reconciled, reset the local editor buffer. Self-driven
	// commits update lastSynced inside handleWhenChange so we don't loop.
	const externalText = useMemo(
		() => JSON.stringify(value.when ?? null, null, 2),
		[value.when],
	);
	if (externalText !== lastSynced && externalText !== whenText) {
		setLastSynced(externalText);
		setWhenText(externalText);
		setParseError(null);
	}

	const handleEditorMount: OnMount = (_editor, monaco) => {
		configureMonacoSchema(monaco);
	};

	function handleWhenChange(next: string | undefined) {
		const text = next ?? "";
		setWhenText(text);
		try {
			const parsed = text.trim() ? JSON.parse(text) : null;
			setParseError(null);
			// Record the canonical form of what we just emitted, so the
			// parent's echo of the same value doesn't trigger a reset.
			setLastSynced(JSON.stringify(parsed, null, 2));
			onChange({ ...value, when: parsed });
		} catch (err) {
			setParseError(err instanceof Error ? err.message : "Invalid JSON");
		}
	}

	function toggleAction(action: Action, checked: boolean) {
		const next = checked
			? Array.from(new Set([...value.actions, action]))
			: value.actions.filter((a) => a !== action);
		onChange({ ...value, actions: next });
	}

	const monacoTheme = theme === "dark" ? "vs-dark" : "light";

	return (
		<div
			className="border rounded-md p-4 space-y-3"
			data-testid={`policy-row-${rowKey}`}
		>
			<div className="flex gap-2 items-start">
				<div className="flex-1 space-y-1">
					<Label
						htmlFor={`policy-name-${rowKey}`}
						className="text-xs font-medium"
					>
						Name
					</Label>
					<Input
						id={`policy-name-${rowKey}`}
						value={value.name}
						onChange={(e) =>
							onChange({ ...value, name: e.target.value })
						}
						placeholder="Policy name"
					/>
				</div>
				<Button
					type="button"
					variant="ghost"
					size="icon"
					onClick={onRemove}
					aria-label={`Remove policy ${value.name || rowKey}`}
					className="mt-5"
				>
					<Trash2 className="h-4 w-4" />
				</Button>
			</div>

			<div className="space-y-1">
				<Label
					htmlFor={`policy-desc-${rowKey}`}
					className="text-xs font-medium"
				>
					Description
				</Label>
				<Input
					id={`policy-desc-${rowKey}`}
					value={value.description ?? ""}
					onChange={(e) =>
						onChange({
							...value,
							description: e.target.value || null,
						})
					}
					placeholder="Description (optional)"
				/>
			</div>

			<div className="space-y-1">
				<span className="text-xs font-medium block">Actions</span>
				<div className="flex flex-wrap gap-3">
					{ACTIONS.map((a) => {
						const id = `policy-action-${rowKey}-${a}`;
						const checked = value.actions.includes(a);
						return (
							<label
								key={a}
								htmlFor={id}
								className="flex items-center gap-1.5 text-sm cursor-pointer"
							>
								<Checkbox
									id={id}
									checked={checked}
									onCheckedChange={(c) =>
										toggleAction(a, c === true)
									}
								/>
								{a}
							</label>
						);
					})}
				</div>
			</div>

			<div className="space-y-1">
				<Label className="text-xs font-medium">
					When (JSON expression)
				</Label>
				<div className="border rounded-md overflow-hidden h-[180px]">
					<Editor
						height="100%"
						language="json"
						value={whenText}
						onChange={handleWhenChange}
						onMount={handleEditorMount}
						theme={monacoTheme}
						path={`policy-${rowKey}.json`}
						options={{
							minimap: { enabled: false },
							scrollBeyondLastLine: false,
							fontSize: 12,
							fontFamily:
								"ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
							wordWrap: "on",
							automaticLayout: true,
							tabSize: 2,
							formatOnPaste: true,
						}}
					/>
				</div>
				{parseError && (
					<p
						className="text-xs text-destructive"
						role="alert"
						data-testid={`policy-when-error-${rowKey}`}
					>
						{parseError}
					</p>
				)}
			</div>
		</div>
	);
}

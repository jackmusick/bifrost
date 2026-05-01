/**
 * Side panel that documents the policy AST: USER fields, ROW field examples,
 * available functions, and operators. Lives inside the PolicyEditor and is
 * toggled via the "Reference" button.
 *
 * Sourced from `api/src/models/contracts/policies.py` (KNOWN_USER_FIELDS,
 * _ALL_OPS) and `api/shared/policies/functions.py` (FUNCTIONS). Keep this in
 * sync if those constants change.
 */

import {
	Sheet,
	SheetContent,
	SheetDescription,
	SheetHeader,
	SheetTitle,
} from "@/components/ui/sheet";

interface RefRow {
	term: string;
	def: string;
}

const USER_FIELDS: RefRow[] = [
	{ term: "user_id", def: "UUID of the calling user." },
	{ term: "email", def: "Email address of the calling user." },
	{ term: "organization_id", def: "Org UUID the user belongs to." },
	{ term: "is_platform_admin", def: "Boolean. True for platform admins." },
	{ term: "role_ids", def: "List of role UUIDs the user holds." },
	{ term: "role_names", def: "List of role names the user holds." },
];

const ROW_FIELDS: RefRow[] = [
	{ term: "id", def: "Document UUID." },
	{ term: "created_by", def: "UUID of the user who created the row." },
	{
		term: "organization_id",
		def: "Org UUID of the row (set when the row is org-scoped).",
	},
	{
		term: "data.<field>",
		def: "Any nested field in the document body, e.g. `data.status`, `data.priority`.",
	},
];

const FUNCTIONS: RefRow[] = [
	{
		term: "has_role(role_name)",
		def: "True when the calling user has a role whose name matches the literal string argument.",
	},
];

const OPERATORS: RefRow[] = [
	{ term: "and", def: "Logical AND. Array of 2+ operands." },
	{ term: "or", def: "Logical OR. Array of 2+ operands." },
	{ term: "not", def: "Logical NOT. Single operand." },
	{ term: "eq", def: "Equality. [left, right]." },
	{ term: "neq", def: "Inequality. [left, right]." },
	{ term: "lt / lte / gt / gte", def: "Numeric / lexical comparison. [left, right]." },
	{ term: "in", def: "Membership. [operand, [literal, ...]]." },
	{ term: "is_null", def: "True when the operand is null. Single operand." },
	{ term: "call", def: "Invoke a function. { call: name, args: [...] }." },
];

function RefSection({ title, rows }: { title: string; rows: RefRow[] }) {
	return (
		<section className="space-y-2">
			<h4 className="text-sm font-semibold">{title}</h4>
			<dl className="grid grid-cols-[max-content_1fr] gap-x-3 gap-y-1 text-sm">
				{rows.map((r) => (
					<div key={r.term} className="contents">
						<dt className="font-mono text-xs pt-0.5 text-muted-foreground">
							{r.term}
						</dt>
						<dd>{r.def}</dd>
					</div>
				))}
			</dl>
		</section>
	);
}

export interface PolicyReferencePanelProps {
	open: boolean;
	onClose: () => void;
}

export function PolicyReferencePanel({
	open,
	onClose,
}: PolicyReferencePanelProps) {
	return (
		<Sheet open={open} onOpenChange={(v) => !v && onClose()}>
			<SheetContent
				side="right"
				className="w-[420px] sm:w-[480px] overflow-y-auto"
				aria-label="Policy reference"
			>
				<SheetHeader>
					<SheetTitle>Policy reference</SheetTitle>
					<SheetDescription>
						Building blocks for the <code>when</code> expression.
						Each policy is a JSON expression evaluated per row;
						true means the action is allowed.
					</SheetDescription>
				</SheetHeader>
				<div className="space-y-6 px-4 pb-6">
					<RefSection title="USER fields" rows={USER_FIELDS} />
					<RefSection title="ROW fields" rows={ROW_FIELDS} />
					<RefSection title="Functions" rows={FUNCTIONS} />
					<RefSection title="Operators" rows={OPERATORS} />
				</div>
			</SheetContent>
		</Sheet>
	);
}

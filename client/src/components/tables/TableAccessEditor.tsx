import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { MultiCombobox } from "@/components/ui/multi-combobox";
import type { components } from "@/lib/v1";
import { X } from "lucide-react";

type TableAccess = components["schemas"]["TableAccess"];
type TableAccessScopeCRUD = components["schemas"]["TableAccessScopeCRUD"];
type TableAccessRoleScope = components["schemas"]["TableAccessRoleScope"];

const EMPTY_CRUD: TableAccessScopeCRUD = {
	read: false,
	create: false,
	update: false,
	delete: false,
};

const EMPTY_ROLE_GRANT: TableAccessRoleScope = {
	roles: [],
	read: false,
	create: false,
	update: false,
	delete: false,
};

const ACTIONS: Array<keyof TableAccessScopeCRUD> = [
	"read",
	"create",
	"update",
	"delete",
];

export interface TableAccessEditorProps {
	value: TableAccess | null;
	roles: Array<{ id: string; name: string }>;
	onChange: (next: TableAccess) => void;
}

export function TableAccessEditor({
	value,
	roles,
	onChange,
}: TableAccessEditorProps) {
	const everyone = value?.everyone ?? { ...EMPTY_CRUD };
	const roleGrants: TableAccessRoleScope[] = value?.roles ?? [];
	const creator = value?.creator ?? { ...EMPTY_CRUD };

	const roleOptions = roles.map((r) => ({ value: r.id, label: r.name }));

	function emit(patch: Partial<TableAccess>) {
		onChange({
			everyone,
			roles: roleGrants,
			creator,
			...patch,
		});
	}

	function toggleEveryone(action: keyof TableAccessScopeCRUD) {
		emit({ everyone: { ...everyone, [action]: !everyone[action] } });
	}

	function toggleCreator(action: keyof TableAccessScopeCRUD) {
		emit({ creator: { ...creator, [action]: !creator[action] } });
	}

	function updateRoleGrant(
		index: number,
		patch: Partial<TableAccessRoleScope>,
	) {
		const next = roleGrants.map((g, i) =>
			i === index ? { ...g, ...patch } : g,
		);
		emit({ roles: next });
	}

	function addRoleGrant() {
		emit({ roles: [...roleGrants, { ...EMPTY_ROLE_GRANT }] });
	}

	function removeRoleGrant(index: number) {
		emit({ roles: roleGrants.filter((_, i) => i !== index) });
	}

	return (
		<div className="space-y-3">
			{/* Header + base rows */}
			<div
				className="grid items-center gap-x-4 gap-y-1 text-xs text-muted-foreground"
				style={{ gridTemplateColumns: "120px repeat(4, 52px)" }}
			>
				{/* Header row */}
				<span />
				{ACTIONS.map((a) => (
					<span key={a} className="text-center capitalize font-medium">
						{a}
					</span>
				))}

				{/* Everyone row */}
				<span className="text-sm text-foreground font-medium">Everyone</span>
				{ACTIONS.map((action) => (
					<div key={action} className="flex justify-center">
						<Checkbox
							checked={everyone[action]}
							onCheckedChange={() => toggleEveryone(action)}
							aria-label={`Everyone — ${action}`}
							className="h-4 w-4"
						/>
					</div>
				))}

				{/* Creator row */}
				<span className="text-sm text-foreground font-medium">Creator</span>
				{ACTIONS.map((action) => (
					<div key={action} className="flex justify-center">
						<Checkbox
							checked={creator[action]}
							onCheckedChange={() => toggleCreator(action)}
							aria-label={`Creator — ${action}`}
							className="h-4 w-4"
						/>
					</div>
				))}
			</div>

			{/* Role grants section */}
			<div className="space-y-1.5">
				<div className="flex items-center justify-between">
					<span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
						Role grants
					</span>
					<Button
						type="button"
						variant="ghost"
						size="sm"
						className="h-6 text-xs px-2"
						onClick={addRoleGrant}
					>
						+ Add row
					</Button>
				</div>

				{roleGrants.length > 0 && (
					<div className="border rounded-md divide-y">
						{roleGrants.map((grant, index) => (
							<div
								key={index}
								className="flex items-center gap-3 px-3 py-2"
							>
								<div className="flex-1 min-w-0">
									<MultiCombobox
										options={roleOptions}
										value={grant.roles as string[]}
										onValueChange={(ids) =>
											updateRoleGrant(index, { roles: ids })
										}
										placeholder="Select roles..."
										searchPlaceholder="Search roles..."
										emptyText="No roles found."
									/>
								</div>
								{ACTIONS.map((action) => (
									<div
										key={action}
										className="flex flex-col items-center gap-0.5 w-[52px]"
									>
										<span className="text-[10px] text-muted-foreground capitalize">
											{action}
										</span>
										<Checkbox
											checked={grant[action] as boolean}
											onCheckedChange={() =>
												updateRoleGrant(index, {
													[action]: !grant[action],
												})
											}
											aria-label={`Role grant ${index + 1} — ${action}`}
											className="h-4 w-4"
										/>
									</div>
								))}
								<Button
									type="button"
									variant="ghost"
									size="sm"
									className="h-6 w-6 p-0 text-muted-foreground hover:text-destructive shrink-0"
									onClick={() => removeRoleGrant(index)}
									aria-label={`Remove role grant ${index + 1}`}
								>
									<X className="h-3 w-3" />
								</Button>
							</div>
						))}
					</div>
				)}
			</div>
		</div>
	);
}

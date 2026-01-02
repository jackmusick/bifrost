import { FileCode } from "lucide-react";
import {
	Dialog,
	DialogContent,
	DialogDescription,
	DialogFooter,
	DialogHeader,
	DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { useForms } from "@/hooks/useForms";
import { useAssignFormsToRole } from "@/hooks/useRoles";
import { useMultiSelect } from "@/hooks/useMultiSelect";
import type { components } from "@/lib/v1";
type Role = components["schemas"]["RolePublic"];
type FormResponse = components["schemas"]["FormPublic"];

interface AssignFormsDialogProps {
	role?: Role | undefined;
	open: boolean;
	onClose: () => void;
}

export function AssignFormsDialog({
	role,
	open,
	onClose,
}: AssignFormsDialogProps) {
	const { selectedIds, toggle, clear, isSelected, count } = useMultiSelect();

	const { data: forms, isLoading } = useForms();
	const assignForms = useAssignFormsToRole();

	const handleAssign = async (e: React.FormEvent) => {
		e.preventDefault();
		if (!role || count === 0) return;

		await assignForms.mutateAsync({
			params: { path: { role_id: role.id } },
			body: { form_ids: selectedIds },
		});

		clear();
		onClose();
	};

	const handleClose = () => {
		clear();
		onClose();
	};

	if (!role) return null;

	return (
		<Dialog open={open} onOpenChange={handleClose}>
			<DialogContent className="sm:max-w-[600px]">
				<form onSubmit={handleAssign}>
					<DialogHeader>
						<DialogTitle>Assign Forms to Role</DialogTitle>
						<DialogDescription>
							Select forms that users with "{role.name}" role can
							access
						</DialogDescription>
					</DialogHeader>

					<div className="max-h-[400px] overflow-y-auto py-4">
						{isLoading ? (
							<div className="space-y-2">
								{[...Array(5)].map((_, i) => (
									<Skeleton key={i} className="h-16 w-full" />
								))}
							</div>
						) : forms && forms.length > 0 ? (
							<div className="space-y-2">
								{forms.map((form: FormResponse) => {
									const selected = isSelected(form.id);
									return (
										<button
											key={form.id}
											onClick={() => toggle(form.id)}
											className={`w-full rounded-lg border p-4 text-left transition-colors ${
												selected
													? "border-primary bg-primary/5"
													: "border-border hover:bg-accent"
											}`}
										>
											<div className="flex items-center justify-between">
												<div>
													<p className="font-medium">
														{form.name}
													</p>
													<p className="text-sm text-muted-foreground">
														{form.description ||
															(form.workflow_id
																? `Workflow ID: ${form.workflow_id}`
																: "No workflow linked")}
													</p>
													<div className="mt-1 flex gap-2">
														{form.organization_id ===
															null && (
															<Badge
																variant="secondary"
																className="text-xs"
															>
																Global
															</Badge>
														)}
														<Badge
															variant={
																form.is_active
																	? "default"
																	: "outline"
															}
															className="text-xs"
														>
															{form.is_active
																? "Active"
																: "Inactive"}
														</Badge>
													</div>
												</div>
												{selected && (
													<Badge>Selected</Badge>
												)}
											</div>
										</button>
									);
								})}
							</div>
						) : (
							<div className="flex flex-col items-center justify-center py-8 text-center">
								<FileCode className="h-12 w-12 text-muted-foreground" />
								<p className="mt-2 text-sm text-muted-foreground">
									No forms available
								</p>
							</div>
						)}
					</div>

					<DialogFooter>
						<Button
							type="button"
							variant="outline"
							onClick={handleClose}
						>
							Cancel
						</Button>
						<Button
							type="submit"
							disabled={count === 0 || assignForms.isPending}
						>
							{assignForms.isPending
								? "Assigning..."
								: `Assign ${count} Form${count !== 1 ? "s" : ""}`}
						</Button>
					</DialogFooter>
				</form>
			</DialogContent>
		</Dialog>
	);
}

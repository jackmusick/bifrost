import { useState } from "react";
import { Pencil, Plus, Trash2, UserCog, RefreshCw, Users } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
	DataTable,
	DataTableBody,
	DataTableCell,
	DataTableHead,
	DataTableHeader,
	DataTableRow,
} from "@/components/ui/data-table";
import {
	AlertDialog,
	AlertDialogAction,
	AlertDialogCancel,
	AlertDialogContent,
	AlertDialogDescription,
	AlertDialogFooter,
	AlertDialogHeader,
	AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { SearchBox } from "@/components/search/SearchBox";
import { useSearch } from "@/hooks/useSearch";
import { useRoles, useDeleteRole } from "@/hooks/useRoles";
import { RoleDialog } from "@/components/roles/RoleDialog";
import { RoleDetailsDialog } from "@/components/roles/RoleDetailsDialog";
import type { components } from "@/lib/v1";
type Role = components["schemas"]["RolePublic"];

export function Roles() {
	const [selectedRole, setSelectedRole] = useState<Role | undefined>();
	const [isDialogOpen, setIsDialogOpen] = useState(false);
	const [detailsRole, setDetailsRole] = useState<Role | undefined>();
	const [isDetailsOpen, setIsDetailsOpen] = useState(false);
	const [isDeleteDialogOpen, setIsDeleteDialogOpen] = useState(false);
	const [roleToDelete, setRoleToDelete] = useState<Role | undefined>();
	const [searchTerm, setSearchTerm] = useState("");

	const { data: roles, isLoading, refetch } = useRoles();
	const deleteRole = useDeleteRole();

	// Apply search filter
	const filteredRoles = useSearch(roles || [], searchTerm, [
		"name",
		"description",
	]);

	const handleEdit = (role: Role) => {
		setSelectedRole(role);
		setIsDialogOpen(true);
	};

	const handleAdd = () => {
		setSelectedRole(undefined);
		setIsDialogOpen(true);
	};

	const handleDelete = (role: Role) => {
		setRoleToDelete(role);
		setIsDeleteDialogOpen(true);
	};

	const handleConfirmDelete = async () => {
		if (!roleToDelete) return;
		deleteRole.mutate({
			params: { path: { role_id: roleToDelete.id } },
		});
		setIsDeleteDialogOpen(false);
		setRoleToDelete(undefined);
	};

	const handleViewDetails = (role: Role) => {
		setDetailsRole(role);
		setIsDetailsOpen(true);
	};

	const handleDialogClose = () => {
		setIsDialogOpen(false);
		setSelectedRole(undefined);
	};

	const handleDetailsClose = () => {
		setIsDetailsOpen(false);
		setDetailsRole(undefined);
	};

	return (
		<div className="h-[calc(100vh-8rem)] flex flex-col space-y-6">
			{/* Header */}
			<div className="flex items-center justify-between">
				<div>
					<h1 className="text-4xl font-extrabold tracking-tight">
						Roles
					</h1>
					<p className="mt-2 text-muted-foreground">
						Manage roles for organization users and control form
						access
					</p>
				</div>
				<div className="flex gap-2">
					<Button
						variant="outline"
						size="icon"
						onClick={() => refetch()}
						title="Refresh"
					>
						<RefreshCw className="h-4 w-4" />
					</Button>
					<Button
						variant="outline"
						size="icon"
						onClick={handleAdd}
						title="Create Role"
					>
						<Plus className="h-4 w-4" />
					</Button>
				</div>
			</div>

			{/* Search and Filters */}
			<div className="flex items-center gap-4">
				<SearchBox
					value={searchTerm}
					onChange={setSearchTerm}
					placeholder="Search roles by name or description..."
					className="max-w-md"
				/>
			</div>

			{/* Content */}
			{isLoading ? (
				<div className="space-y-2">
					{[...Array(5)].map((_, i) => (
						<Skeleton key={i} className="h-12 w-full" />
					))}
				</div>
			) : filteredRoles && filteredRoles.length > 0 ? (
				<div className="flex-1 min-h-0">
					<DataTable className="max-h-full">
						<DataTableHeader>
							<DataTableRow>
								<DataTableHead>Name</DataTableHead>
								<DataTableHead>Description</DataTableHead>
								<DataTableHead>Status</DataTableHead>
								<DataTableHead>Created</DataTableHead>
								<DataTableHead className="text-right">
									Actions
								</DataTableHead>
							</DataTableRow>
						</DataTableHeader>
						<DataTableBody>
							{filteredRoles.map((role) => (
								<DataTableRow key={role.id}>
									<DataTableCell className="font-medium">
										{role.name}
									</DataTableCell>
									<DataTableCell className="max-w-xs truncate text-muted-foreground">
										{role.description || "-"}
									</DataTableCell>
									<DataTableCell>
										<Badge
											variant={
												role.is_active
													? "default"
													: "secondary"
											}
										>
											{role.is_active
												? "Active"
												: "Inactive"}
										</Badge>
									</DataTableCell>
									<DataTableCell className="text-sm text-muted-foreground">
										{role.created_at
											? new Date(
													role.created_at,
												).toLocaleDateString()
											: "N/A"}
									</DataTableCell>
									<DataTableCell className="text-right">
										<div className="flex justify-end gap-2">
											<Button
												variant="ghost"
												size="icon"
												onClick={() =>
													handleViewDetails(role)
												}
												title="View users and forms"
											>
												<Users className="h-4 w-4" />
											</Button>
											<Button
												variant="ghost"
												size="icon"
												onClick={() => handleEdit(role)}
											>
												<Pencil className="h-4 w-4" />
											</Button>
											<Button
												variant="ghost"
												size="icon"
												onClick={() =>
													handleDelete(role)
												}
											>
												<Trash2 className="h-4 w-4" />
											</Button>
										</div>
									</DataTableCell>
								</DataTableRow>
							))}
						</DataTableBody>
					</DataTable>
				</div>
			) : (
				// Empty State
				<Card>
					<CardContent className="flex flex-col items-center justify-center py-12 text-center">
						<UserCog className="h-12 w-12 text-muted-foreground" />
						<h3 className="mt-4 text-lg font-semibold">
							{searchTerm
								? "No roles match your search"
								: "No roles found"}
						</h3>
						<p className="mt-2 text-sm text-muted-foreground">
							{searchTerm
								? "Try adjusting your search term or clear the filter"
								: "Get started by creating your first role"}
						</p>
						<Button
							variant="outline"
							size="icon"
							onClick={handleAdd}
							title="Create Role"
							className="mt-4"
						>
							<Plus className="h-4 w-4" />
						</Button>
					</CardContent>
				</Card>
			)}

			<RoleDialog
				role={selectedRole}
				open={isDialogOpen}
				onClose={handleDialogClose}
			/>

			<RoleDetailsDialog
				role={detailsRole}
				open={isDetailsOpen}
				onClose={handleDetailsClose}
			/>

			{/* Delete Confirmation Dialog */}
			<AlertDialog
				open={isDeleteDialogOpen}
				onOpenChange={setIsDeleteDialogOpen}
			>
				<AlertDialogContent>
					<AlertDialogHeader>
						<AlertDialogTitle>Delete Role</AlertDialogTitle>
						<AlertDialogDescription>
							Are you sure you want to delete the role "
							{roleToDelete?.name}"? This action cannot be undone.
						</AlertDialogDescription>
					</AlertDialogHeader>
					<AlertDialogFooter>
						<AlertDialogCancel>Cancel</AlertDialogCancel>
						<AlertDialogAction
							onClick={handleConfirmDelete}
							className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
						>
							{deleteRole.isPending
								? "Deleting..."
								: "Delete Role"}
						</AlertDialogAction>
					</AlertDialogFooter>
				</AlertDialogContent>
			</AlertDialog>
		</div>
	);
}

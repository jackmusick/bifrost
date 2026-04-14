import { useState, useMemo } from "react";
import { Pencil, Plus, Trash2, UserCog, RefreshCw, ArrowUp, ArrowDown } from "lucide-react";
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
import { Skeleton } from "@/components/ui/skeleton";
import { SearchBox } from "@/components/search/SearchBox";
import { useSearch } from "@/hooks/useSearch";
import { useRoles, useDeleteRole } from "@/hooks/useRoles";
import { RoleDialog } from "@/components/roles/RoleDialog";
import { RoleDetailsDialog } from "@/components/roles/RoleDetailsDialog";
import type { components } from "@/lib/v1";
type Role = components["schemas"]["RolePublic"];

type SortColumn = "name" | "created";
type SortDirection = "asc" | "desc";

function SortIcon({ column, sortColumn, sortDirection }: { column: SortColumn; sortColumn: SortColumn; sortDirection: SortDirection }) {
	if (sortColumn !== column) return null;
	return sortDirection === "asc" ? (
		<ArrowUp className="inline ml-1 h-3 w-3" />
	) : (
		<ArrowDown className="inline ml-1 h-3 w-3" />
	);
}

export function Roles() {
	const [selectedRole, setSelectedRole] = useState<Role | undefined>();
	const [isDialogOpen, setIsDialogOpen] = useState(false);
	const [detailsRole, setDetailsRole] = useState<Role | undefined>();
	const [isDetailsOpen, setIsDetailsOpen] = useState(false);
	const [isDeleteDialogOpen, setIsDeleteDialogOpen] = useState(false);
	const [roleToDelete, setRoleToDelete] = useState<Role | undefined>();
	const [searchTerm, setSearchTerm] = useState("");
	const [sortColumn, setSortColumn] = useState<SortColumn>("name");
	const [sortDirection, setSortDirection] = useState<SortDirection>("asc");

	const { data: roles, isLoading, refetch } = useRoles();
	const deleteRole = useDeleteRole();

	// Apply search filter
	const filteredRoles = useSearch(roles || [], searchTerm, [
		"name",
		"description",
	]);

	// Apply sorting
	const sortedRoles = useMemo(() => {
		if (!filteredRoles) return [];
		return [...filteredRoles].sort((a, b) => {
			const dir = sortDirection === "asc" ? 1 : -1;
			switch (sortColumn) {
				case "name":
					return dir * (a.name || "").localeCompare(b.name || "");
				case "created": {
					const aDate = a.created_at ? new Date(a.created_at).getTime() : 0;
					const bDate = b.created_at ? new Date(b.created_at).getTime() : 0;
					return dir * (aDate - bDate);
				}
				default:
					return 0;
			}
		});
	}, [filteredRoles, sortColumn, sortDirection]);

	const handleSort = (column: SortColumn) => {
		if (sortColumn === column) {
			setSortDirection((d) => (d === "asc" ? "desc" : "asc"));
		} else {
			setSortColumn(column);
			setSortDirection("asc");
		}
	};

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
		<div className="h-full flex flex-col space-y-6 max-w-7xl mx-auto">
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
					className="flex-1"
				/>
			</div>

			{/* Content */}
			{isLoading ? (
				<div className="space-y-2">
					{[...Array(5)].map((_, i) => (
						<Skeleton key={i} className="h-12 w-full" />
					))}
				</div>
			) : sortedRoles && sortedRoles.length > 0 ? (
				<div className="flex-1 min-h-0">
					<DataTable className="max-h-full">
						<DataTableHeader>
							<DataTableRow>
								<DataTableHead
									className="cursor-pointer select-none"
									onClick={() => handleSort("name")}
								>
									Name
									<SortIcon column="name" sortColumn={sortColumn} sortDirection={sortDirection} />
								</DataTableHead>
								<DataTableHead>Description</DataTableHead>
								<DataTableHead
									className="w-0 whitespace-nowrap cursor-pointer select-none"
									onClick={() => handleSort("created")}
								>
									Created
									<SortIcon column="created" sortColumn={sortColumn} sortDirection={sortDirection} />
								</DataTableHead>
								<DataTableHead className="w-0 whitespace-nowrap text-right">
									Actions
								</DataTableHead>
							</DataTableRow>
						</DataTableHeader>
						<DataTableBody>
							{sortedRoles.map((role) => (
								<DataTableRow
									key={role.id}
									clickable
									onClick={() => handleViewDetails(role)}
								>
									<DataTableCell className="font-medium">
										{role.name}
									</DataTableCell>
									<DataTableCell className="max-w-xs truncate text-muted-foreground">
										{role.description || "-"}
									</DataTableCell>
									<DataTableCell className="w-0 whitespace-nowrap text-sm text-muted-foreground">
										{role.created_at
											? new Date(
													role.created_at,
												).toLocaleDateString()
											: "N/A"}
									</DataTableCell>
									<DataTableCell className="w-0 whitespace-nowrap text-right">
										<div className="flex justify-end gap-2">
											<Button
												variant="ghost"
												size="icon"
												onClick={(e) => {
													e.stopPropagation();
													handleEdit(role);
												}}
												title="Edit role"
											>
												<Pencil className="h-4 w-4" />
											</Button>
											<Button
												variant="ghost"
												size="icon"
												onClick={(e) => {
													e.stopPropagation();
													handleDelete(role);
												}}
												title="Delete role"
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

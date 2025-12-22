import { useState } from "react";
import {
	Shield,
	Users as UsersIcon,
	RefreshCw,
	UserCog,
	Edit,
	Plus,
	Trash2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
	Card,
	CardContent,
	CardDescription,
	CardHeader,
	CardTitle,
} from "@/components/ui/card";
import {
	DataTable,
	DataTableBody,
	DataTableCell,
	DataTableHead,
	DataTableHeader,
	DataTableRow,
} from "@/components/ui/data-table";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
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
import { SearchBox } from "@/components/search/SearchBox";
import { useSearch } from "@/hooks/useSearch";
import { useUsers, useDeleteUser } from "@/hooks/useUsers";
import { useAuth } from "@/contexts/AuthContext";
import { useOrgScope } from "@/contexts/OrgScopeContext";
import { CreateUserDialog } from "@/components/users/CreateUserDialog";
import { EditUserDialog } from "@/components/users/EditUserDialog";
import { toast } from "sonner";
import type { components } from "@/lib/v1";
type User = components["schemas"]["UserPublic"];

export function Users() {
	const [selectedUser, setSelectedUser] = useState<User | undefined>();
	const [isCreateOpen, setIsCreateOpen] = useState(false);
	const [isEditOpen, setIsEditOpen] = useState(false);
	const [isDeleteOpen, setIsDeleteOpen] = useState(false);
	const [searchTerm, setSearchTerm] = useState("");

	const { scope } = useOrgScope();
	const { user: currentUser } = useAuth();

	// Fetch users based on current scope
	// Scope is sent via X-Organization-Id header (managed by api client from sessionStorage)
	const { data: users, isLoading, refetch } = useUsers();
	const deleteMutation = useDeleteUser();

	// React Query automatically refetches when scope changes (via orgId in query key)

	// Apply search filter
	const filteredUsers = useSearch(users || [], searchTerm, ["email", "name"]);

	const handleEditUser = (user: User) => {
		setSelectedUser(user);
		setIsEditOpen(true);
	};

	const handleDeleteUser = (user: User) => {
		setSelectedUser(user);
		setIsDeleteOpen(true);
	};

	const handleConfirmDelete = async () => {
		if (!selectedUser) return;

		try {
			await deleteMutation.mutateAsync({
				params: { path: { user_id: selectedUser.id } },
			});
			toast.success("User deleted successfully", {
				description: `${selectedUser.name || selectedUser.email} has been removed from the platform`,
			});
			setIsDeleteOpen(false);
			setSelectedUser(undefined);
		} catch (error) {
			const errorMessage =
				error instanceof Error
					? error.message
					: "Unknown error occurred";
			toast.error("Failed to delete user", {
				description: errorMessage,
			});
		}
	};

	const handleEditClose = () => {
		setIsEditOpen(false);
		setSelectedUser(undefined);
	};

	const getUserTypeBadge = (type: string) => {
		return type === "PLATFORM" ? (
			<Badge variant="default">
				<Shield className="mr-1 h-3 w-3" />
				Platform Admin
			</Badge>
		) : (
			<Badge variant="secondary">
				<UsersIcon className="mr-1 h-3 w-3" />
				Organization User
			</Badge>
		);
	};

	return (
		<div className="space-y-6">
			<div className="flex items-center justify-between">
				<div>
					<h1 className="text-4xl font-extrabold tracking-tight">
						Users
					</h1>
					<p className="mt-2 text-muted-foreground">
						{scope.type === "global"
							? "Manage platform administrators and organization users"
							: `Users for ${scope.orgName}`}
					</p>
				</div>
				<div className="flex items-center gap-2">
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
						onClick={() => setIsCreateOpen(true)}
						title="Create User"
					>
						<Plus className="h-4 w-4" />
					</Button>
				</div>
			</div>

			{/* Search Box */}
			<SearchBox
				value={searchTerm}
				onChange={setSearchTerm}
				placeholder="Search users by email or name..."
				className="max-w-md"
			/>

			<Card>
				<CardHeader>
					<CardTitle>All Users</CardTitle>
					<CardDescription>
						Platform administrators and organization users
					</CardDescription>
				</CardHeader>
				<CardContent>
					{isLoading ? (
						<div className="space-y-2">
							{[...Array(5)].map((_, i) => (
								<Skeleton key={i} className="h-12 w-full" />
							))}
						</div>
					) : filteredUsers && filteredUsers.length > 0 ? (
						<div className="max-h-[calc(100vh-28rem)] overflow-auto rounded-md border">
							<DataTable>
								<DataTableHeader className="sticky top-0 bg-background z-10">
									<DataTableRow>
										<DataTableHead>Name</DataTableHead>
										<DataTableHead>Email</DataTableHead>
										<DataTableHead>Type</DataTableHead>
										<DataTableHead>Status</DataTableHead>
										<DataTableHead>Created</DataTableHead>
										<DataTableHead>Last Login</DataTableHead>
										<DataTableHead className="text-right"></DataTableHead>
									</DataTableRow>
								</DataTableHeader>
								<DataTableBody>
									{filteredUsers.map((user) => (
										<DataTableRow key={user.id}>
											<DataTableCell className="font-medium">
												{user.name || user.email}
											</DataTableCell>
											<DataTableCell className="text-muted-foreground">
												{user.email}
											</DataTableCell>
											<DataTableCell>
												{getUserTypeBadge(
													user.user_type,
												)}
											</DataTableCell>
											<DataTableCell>
												<Badge
													variant={
														user.is_active
															? "default"
															: "secondary"
													}
												>
													{user.is_active
														? "Active"
														: "Inactive"}
												</Badge>
											</DataTableCell>
											<DataTableCell className="text-sm text-muted-foreground">
												{user.created_at
													? new Date(
															user.created_at,
														).toLocaleDateString()
													: "N/A"}
											</DataTableCell>
											<DataTableCell className="text-sm text-muted-foreground">
												{user.last_login
													? new Date(
															user.last_login,
														).toLocaleDateString()
													: "Never"}
											</DataTableCell>
											<DataTableCell className="text-right">
												<div className="flex items-center justify-end gap-2">
													<Button
														variant="ghost"
														size="icon"
														onClick={() =>
															handleEditUser(user)
														}
														title="Edit user"
													>
														<Edit className="h-4 w-4" />
													</Button>
													<Button
														variant="ghost"
														size="icon"
														onClick={() =>
															handleDeleteUser(
																user,
															)
														}
														title="Delete user"
														disabled={
															!!(
																currentUser &&
																user.id ===
																	currentUser.id
															)
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
						<div className="flex flex-col items-center justify-center py-12 text-center">
							<UserCog className="h-12 w-12 text-muted-foreground" />
							<h3 className="mt-4 text-lg font-semibold">
								{searchTerm
									? "No users match your search"
									: "No users found"}
							</h3>
							<p className="mt-2 text-sm text-muted-foreground">
								{searchTerm
									? "Try adjusting your search term or clear the filter"
									: "No users in the system"}
							</p>
						</div>
					)}
				</CardContent>
			</Card>

			<CreateUserDialog
				open={isCreateOpen}
				onOpenChange={setIsCreateOpen}
			/>

			<EditUserDialog
				user={selectedUser}
				open={isEditOpen}
				onOpenChange={handleEditClose}
			/>

			<AlertDialog open={isDeleteOpen} onOpenChange={setIsDeleteOpen}>
				<AlertDialogContent>
					<AlertDialogHeader>
						<AlertDialogTitle>Delete User</AlertDialogTitle>
						<AlertDialogDescription>
							Are you sure you want to delete{" "}
							{selectedUser?.name || selectedUser?.email}? This
							action cannot be undone.
						</AlertDialogDescription>
					</AlertDialogHeader>
					<AlertDialogFooter>
						<AlertDialogCancel>Cancel</AlertDialogCancel>
						<AlertDialogAction
							onClick={handleConfirmDelete}
							className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
						>
							Delete
						</AlertDialogAction>
					</AlertDialogFooter>
				</AlertDialogContent>
			</AlertDialog>
		</div>
	);
}

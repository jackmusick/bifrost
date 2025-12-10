import { useState } from "react";
import { Users, FileCode, X, UserPlus, FilePlus } from "lucide-react";
import {
	Dialog,
	DialogContent,
	DialogDescription,
	DialogHeader,
	DialogTitle,
} from "@/components/ui/dialog";
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
	Card,
	CardContent,
	CardDescription,
	CardHeader,
	CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
	useRoleUsers,
	useRoleForms,
	useRemoveUserFromRole,
} from "@/hooks/useRoles";
import { AssignUsersDialog } from "./AssignUsersDialog";
import { AssignFormsDialog } from "./AssignFormsDialog";
import type { components } from "@/lib/v1";
type Role = components["schemas"]["RolePublic"];
type RoleUsersResponse = components["schemas"]["RoleUsersResponse"];
type RoleFormsResponse = components["schemas"]["RoleFormsResponse"];

interface RoleDetailsDialogProps {
	role?: Role | undefined;
	open: boolean;
	onClose: () => void;
}

export function RoleDetailsDialog({
	role,
	open,
	onClose,
}: RoleDetailsDialogProps) {
	const [isAssignUsersOpen, setIsAssignUsersOpen] = useState(false);
	const [isAssignFormsOpen, setIsAssignFormsOpen] = useState(false);
	const [isRemoveUserDialogOpen, setIsRemoveUserDialogOpen] = useState(false);
	const [isRemoveFormDialogOpen, setIsRemoveFormDialogOpen] = useState(false);
	const [userToRemove, setUserToRemove] = useState<string | undefined>();
	const [formToRemove, setFormToRemove] = useState<string | undefined>();

	const { data: users, isLoading: usersLoading } = useRoleUsers(role?.id);
	const { data: forms, isLoading: formsLoading } = useRoleForms(role?.id);
	const removeUser = useRemoveUserFromRole();
	// const removeForm = useRemoveFormFromRole(); // Not implemented - endpoint not available

	if (!role) return null;

	const handleRemoveUser = (userId: string) => {
		setUserToRemove(userId);
		setIsRemoveUserDialogOpen(true);
	};

	const handleConfirmRemoveUser = () => {
		if (!userToRemove) return;
		removeUser.mutate({
			params: { path: { role_id: role.id, user_id: userToRemove } },
		});
		setIsRemoveUserDialogOpen(false);
		setUserToRemove(undefined);
	};

	const handleRemoveForm = (formId: string) => {
		setFormToRemove(formId);
		setIsRemoveFormDialogOpen(true);
	};

	const handleConfirmRemoveForm = () => {
		if (!formToRemove) return;
		setIsRemoveFormDialogOpen(false);
		setFormToRemove(undefined);
	};

	return (
		<Dialog open={open} onOpenChange={onClose}>
			<DialogContent className="sm:max-w-[700px]">
				<DialogHeader>
					<DialogTitle>{role.name}</DialogTitle>
					<DialogDescription>
						{role.description ||
							"Manage users and forms for this role"}
					</DialogDescription>
				</DialogHeader>

				<Tabs defaultValue="users" className="mt-4">
					<TabsList className="grid w-full grid-cols-2">
						<TabsTrigger value="users">
							<Users className="mr-2 h-4 w-4" />
							Users
						</TabsTrigger>
						<TabsTrigger value="forms">
							<FileCode className="mr-2 h-4 w-4" />
							Forms
						</TabsTrigger>
					</TabsList>

					<TabsContent value="users" className="mt-4">
						<Card>
							<CardHeader>
								<div className="flex items-center justify-between">
									<div>
										<CardTitle>Assigned Users</CardTitle>
										<CardDescription>
											Organization users who have this
											role
										</CardDescription>
									</div>
									<Button
										variant="outline"
										size="sm"
										onClick={() =>
											setIsAssignUsersOpen(true)
										}
									>
										<UserPlus className="mr-2 h-4 w-4" />
										Assign Users
									</Button>
								</div>
							</CardHeader>
							<CardContent>
								{usersLoading ? (
									<div className="space-y-2">
										{[...Array(3)].map((_, i) => (
											<Skeleton
												key={i}
												className="h-10 w-full"
											/>
										))}
									</div>
								) : users &&
								  (users as RoleUsersResponse).userIds &&
								  (users as RoleUsersResponse).userIds.length >
										0 ? (
									<div className="space-y-2">
										{(
											users as RoleUsersResponse
										).userIds.map((userId: string) => (
											<div
												key={userId}
												className="flex items-center justify-between rounded-lg border p-3"
											>
												<div>
													<p className="font-medium">
														{userId}
													</p>
													<p className="text-sm text-muted-foreground">
														User ID: {userId}
													</p>
												</div>
												<Button
													variant="ghost"
													size="icon"
													onClick={() =>
														handleRemoveUser(userId)
													}
												>
													<X className="h-4 w-4" />
												</Button>
											</div>
										))}
									</div>
								) : (
									<div className="flex flex-col items-center justify-center py-8 text-center">
										<Users className="h-12 w-12 text-muted-foreground" />
										<p className="mt-2 text-sm text-muted-foreground">
											No users assigned to this role
										</p>
									</div>
								)}
							</CardContent>
						</Card>
					</TabsContent>

					<TabsContent value="forms" className="mt-4">
						<Card>
							<CardHeader>
								<div className="flex items-center justify-between">
									<div>
										<CardTitle>Assigned Forms</CardTitle>
										<CardDescription>
											Forms that users with this role can
											access
										</CardDescription>
									</div>
									<Button
										variant="outline"
										size="sm"
										onClick={() =>
											setIsAssignFormsOpen(true)
										}
									>
										<FilePlus className="mr-2 h-4 w-4" />
										Assign Forms
									</Button>
								</div>
							</CardHeader>
							<CardContent>
								{formsLoading ? (
									<div className="space-y-2">
										{[...Array(3)].map((_, i) => (
											<Skeleton
												key={i}
												className="h-10 w-full"
											/>
										))}
									</div>
								) : forms &&
								  (forms as RoleFormsResponse).formIds &&
								  (forms as RoleFormsResponse).formIds.length >
										0 ? (
									<div className="space-y-2">
										{(
											forms as RoleFormsResponse
										).formIds.map((formId: string) => (
											<div
												key={formId}
												className="flex items-center justify-between rounded-lg border p-3"
											>
												<div>
													<p className="font-medium">
														{formId}
													</p>
													<p className="text-sm text-muted-foreground">
														Form ID: {formId}
													</p>
												</div>
												<Button
													variant="ghost"
													size="icon"
													onClick={() =>
														handleRemoveForm(formId)
													}
												>
													<X className="h-4 w-4" />
												</Button>
											</div>
										))}
									</div>
								) : (
									<div className="flex flex-col items-center justify-center py-8 text-center">
										<FileCode className="h-12 w-12 text-muted-foreground" />
										<p className="mt-2 text-sm text-muted-foreground">
											No forms assigned to this role
										</p>
									</div>
								)}
							</CardContent>
						</Card>
					</TabsContent>
				</Tabs>
			</DialogContent>

			<AssignUsersDialog
				role={role}
				open={isAssignUsersOpen}
				onClose={() => setIsAssignUsersOpen(false)}
			/>

			<AssignFormsDialog
				role={role}
				open={isAssignFormsOpen}
				onClose={() => setIsAssignFormsOpen(false)}
			/>

			{/* Remove User Confirmation Dialog */}
			<AlertDialog
				open={isRemoveUserDialogOpen}
				onOpenChange={setIsRemoveUserDialogOpen}
			>
				<AlertDialogContent>
					<AlertDialogHeader>
						<AlertDialogTitle>
							Remove User from Role
						</AlertDialogTitle>
						<AlertDialogDescription>
							Are you sure you want to remove this user from the
							role? They will lose access to all forms assigned to
							this role.
						</AlertDialogDescription>
					</AlertDialogHeader>
					<AlertDialogFooter>
						<AlertDialogCancel>Cancel</AlertDialogCancel>
						<AlertDialogAction
							onClick={handleConfirmRemoveUser}
							className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
						>
							{removeUser.isPending
								? "Removing..."
								: "Remove User"}
						</AlertDialogAction>
					</AlertDialogFooter>
				</AlertDialogContent>
			</AlertDialog>

			{/* Remove Form Confirmation Dialog */}
			<AlertDialog
				open={isRemoveFormDialogOpen}
				onOpenChange={setIsRemoveFormDialogOpen}
			>
				<AlertDialogContent>
					<AlertDialogHeader>
						<AlertDialogTitle>
							Remove Form from Role
						</AlertDialogTitle>
						<AlertDialogDescription>
							Are you sure you want to remove this form from the
							role? Users with this role will lose access to this
							form.
						</AlertDialogDescription>
					</AlertDialogHeader>
					<AlertDialogFooter>
						<AlertDialogCancel>Cancel</AlertDialogCancel>
						<AlertDialogAction
							onClick={handleConfirmRemoveForm}
							className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
						>
							Remove Form
						</AlertDialogAction>
					</AlertDialogFooter>
				</AlertDialogContent>
			</AlertDialog>
		</Dialog>
	);
}

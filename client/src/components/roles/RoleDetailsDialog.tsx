import { useState, useMemo } from "react";
import { Users, FileCode, X, UserPlus, FilePlus, Search } from "lucide-react";
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
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
	useRoleUsers,
	useRoleForms,
	useRemoveUserFromRole,
} from "@/hooks/useRoles";
import { useUsers } from "@/hooks/useUsers";
import { AssignUsersDialog } from "./AssignUsersDialog";
import { AssignFormsDialog } from "./AssignFormsDialog";
import type { components } from "@/lib/v1";
type Role = components["schemas"]["RolePublic"];
type RoleUsersResponse = components["schemas"]["RoleUsersResponse"];
type RoleFormsResponse = components["schemas"]["RoleFormsResponse"];
type User = components["schemas"]["UserPublic"];

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
	const [userSearchTerm, setUserSearchTerm] = useState("");

	const { data: users, isLoading: usersLoading } = useRoleUsers(role?.id);
	const { data: forms, isLoading: formsLoading } = useRoleForms(role?.id);
	const { data: allUsers } = useUsers();
	const removeUser = useRemoveUserFromRole();

	// Build user lookup map
	const userMap = useMemo(() => {
		const map = new Map<string, User>();
		if (allUsers) {
			for (const u of allUsers as User[]) {
				map.set(u.id, u);
			}
		}
		return map;
	}, [allUsers]);

	// Filter users by search term
	const userIds = useMemo(() => (users as RoleUsersResponse)?.user_ids ?? [], [users]);
	const filteredUserIds = useMemo(() => {
		if (!userSearchTerm) return userIds;
		const term = userSearchTerm.toLowerCase();
		return userIds.filter((userId) => {
			const u = userMap.get(userId);
			if (!u) return userId.toLowerCase().includes(term);
			return (
				(u.name && u.name.toLowerCase().includes(term)) ||
				u.email.toLowerCase().includes(term)
			);
		});
	}, [userIds, userSearchTerm, userMap]);

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
			<DialogContent className="sm:max-w-[700px] max-h-[85vh] flex flex-col">
				<DialogHeader>
					<DialogTitle>{role.name}</DialogTitle>
					<DialogDescription>
						{role.description ||
							"Manage users and forms for this role"}
					</DialogDescription>
				</DialogHeader>

				<Tabs defaultValue="users" className="mt-4 flex-1 min-h-0 flex flex-col">
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

					<TabsContent value="users" className="mt-4 flex-1 min-h-0 flex flex-col">
						<Card className="flex-1 min-h-0 flex flex-col">
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
								{userIds.length > 0 && (
									<div className="relative mt-2">
										<Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
										<Input
											placeholder="Search users..."
											value={userSearchTerm}
											onChange={(e) => setUserSearchTerm(e.target.value)}
											className="pl-9 h-9"
										/>
									</div>
								)}
							</CardHeader>
							<CardContent className="flex-1 min-h-0">
								{usersLoading ? (
									<div className="space-y-2">
										{[...Array(3)].map((_, i) => (
											<Skeleton
												key={i}
												className="h-10 w-full"
											/>
										))}
									</div>
								) : userIds.length > 0 ? (
									<div className="max-h-[300px] overflow-y-auto space-y-2 pr-1">
										{filteredUserIds.length > 0 ? (
											filteredUserIds.map((userId: string) => {
												const u = userMap.get(userId);
												return (
													<div
														key={userId}
														className="flex items-center justify-between rounded-lg border p-3"
													>
														<div>
															<p className="font-medium">
																{u?.name || u?.email || userId}
															</p>
															<p className="text-sm text-muted-foreground">
																{u ? u.email : `User ID: ${userId}`}
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
												);
											})
										) : (
											<p className="text-sm text-muted-foreground text-center py-4">
												No users match your search
											</p>
										)}
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
								  (forms as RoleFormsResponse).form_ids &&
								  (forms as RoleFormsResponse).form_ids.length >
										0 ? (
									<div className="space-y-2">
										{(
											forms as RoleFormsResponse
										).form_ids.map((formId: string) => (
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

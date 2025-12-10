import { useState } from "react";
import { Building2, Plus, Pencil, Trash2, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
	Card,
	CardContent,
	CardDescription,
	CardHeader,
	CardTitle,
} from "@/components/ui/card";
import {
	Table,
	TableBody,
	TableCell,
	TableHead,
	TableHeader,
	TableRow,
} from "@/components/ui/table";
import {
	Dialog,
	DialogContent,
	DialogDescription,
	DialogFooter,
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
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { SearchBox } from "@/components/search/SearchBox";
import { useSearch } from "@/hooks/useSearch";
import {
	useOrganizations,
	useCreateOrganization,
	useUpdateOrganization,
	useDeleteOrganization,
} from "@/hooks/useOrganizations";
import type { components } from "@/lib/v1";
type Organization = components["schemas"]["OrganizationPublic"];

interface OrganizationFormData {
	name: string;
	domain: string;
}

export function Organizations() {
	const [isCreateDialogOpen, setIsCreateDialogOpen] = useState(false);
	const [isEditDialogOpen, setIsEditDialogOpen] = useState(false);
	const [isDeleteDialogOpen, setIsDeleteDialogOpen] = useState(false);
	const [selectedOrg, setSelectedOrg] = useState<Organization | undefined>();
	const [formData, setFormData] = useState<OrganizationFormData>({
		name: "",
		domain: "",
	});
	const [searchTerm, setSearchTerm] = useState("");

	const { data, isLoading, refetch } = useOrganizations();
	const organizations: Organization[] = Array.isArray(data) ? data : [];

	const createMutation = useCreateOrganization();
	const updateMutation = useUpdateOrganization();
	const deleteMutation = useDeleteOrganization();

	// Apply search filter
	const filteredOrgs = useSearch(organizations, searchTerm, [
		"name",
		"domain",
	]);

	const handleCreate = () => {
		setFormData({ name: "", domain: "" });
		setIsCreateDialogOpen(true);
	};

	const handleEdit = (org: Organization) => {
		setSelectedOrg(org);
		setFormData({
			name: org.name,
			domain: org.domain || "",
		});
		setIsEditDialogOpen(true);
	};

	const handleDelete = (org: Organization) => {
		setSelectedOrg(org);
		setIsDeleteDialogOpen(true);
	};

	const handleSubmitCreate = async (e: React.FormEvent) => {
		e.preventDefault();
		await createMutation.mutateAsync({
			body: {
				name: formData.name,
				domain: formData.domain || null,
				is_active: true,
			},
		});
		setIsCreateDialogOpen(false);
		setFormData({ name: "", domain: "" });
	};

	const handleSubmitEdit = async (e: React.FormEvent) => {
		e.preventDefault();
		if (!selectedOrg) return;

		await updateMutation.mutateAsync({
			params: { path: { org_id: selectedOrg.id } },
			body: {
				name: formData.name || null,
				domain: formData.domain || null,
				is_active: null,
			},
		});
		setIsEditDialogOpen(false);
		setSelectedOrg(undefined);
		setFormData({ name: "", domain: "" });
	};

	const handleConfirmDelete = async () => {
		if (!selectedOrg) return;

		await deleteMutation.mutateAsync({
			params: { path: { org_id: selectedOrg.id } },
		});
		setIsDeleteDialogOpen(false);
		setSelectedOrg(undefined);
	};

	const handleDialogClose = (open: boolean) => {
		if (!open) {
			setIsCreateDialogOpen(false);
			setIsEditDialogOpen(false);
			setFormData({ name: "", domain: "" });
			setSelectedOrg(undefined);
		}
	};

	return (
		<div className="space-y-6">
			<div className="flex items-center justify-between">
				<div>
					<h1 className="text-4xl font-extrabold tracking-tight">
						Organizations
					</h1>
					<p className="mt-2 text-muted-foreground">
						Manage customer organizations and their configurations
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
						onClick={handleCreate}
						title="Create Organization"
					>
						<Plus className="h-4 w-4" />
					</Button>
				</div>
			</div>

			{/* Search Box */}
			<SearchBox
				value={searchTerm}
				onChange={setSearchTerm}
				placeholder="Search organizations by name or type..."
				className="max-w-md"
			/>

			<Card>
				<CardHeader>
					<CardTitle>All Organizations</CardTitle>
					<CardDescription>
						View and manage all customer organizations
					</CardDescription>
				</CardHeader>
				<CardContent>
					{isLoading ? (
						<div className="space-y-2">
							{[...Array(5)].map((_, i) => (
								<Skeleton key={i} className="h-12 w-full" />
							))}
						</div>
					) : filteredOrgs && filteredOrgs.length > 0 ? (
						<div className="max-h-[calc(100vh-28rem)] overflow-auto rounded-md border">
							<Table>
								<TableHeader className="sticky top-0 bg-background z-10">
									<TableRow>
										<TableHead>Name</TableHead>
										<TableHead>Domain</TableHead>
										<TableHead>Organization ID</TableHead>
										<TableHead>Status</TableHead>
										<TableHead>Created</TableHead>
										<TableHead className="text-right"></TableHead>
									</TableRow>
								</TableHeader>
								<TableBody>
									{filteredOrgs.map((org) => (
										<TableRow
											key={org.id}
											className="hover:bg-muted/50"
										>
											<TableCell className="font-medium">
												{org.name}
											</TableCell>
											<TableCell className="text-sm text-muted-foreground">
												{org.domain || "-"}
											</TableCell>
											<TableCell className="font-mono text-xs text-muted-foreground">
												{org.id}
											</TableCell>
											<TableCell>
												<Badge
													variant={
														org.is_active
															? "default"
															: "secondary"
													}
												>
													{org.is_active
														? "Active"
														: "Inactive"}
												</Badge>
											</TableCell>
											<TableCell className="text-sm">
												{org.created_at
													? new Date(
															org.created_at,
														).toLocaleDateString()
													: "N/A"}
											</TableCell>
											<TableCell className="text-right">
												<div className="flex items-center justify-end gap-2">
													<Button
														variant="ghost"
														size="icon"
														onClick={() =>
															handleEdit(org)
														}
														title="Edit organization"
													>
														<Pencil className="h-4 w-4" />
													</Button>
													<Button
														variant="ghost"
														size="icon"
														onClick={() =>
															handleDelete(org)
														}
														title="Delete organization"
													>
														<Trash2 className="h-4 w-4" />
													</Button>
												</div>
											</TableCell>
										</TableRow>
									))}
								</TableBody>
							</Table>
						</div>
					) : (
						<div className="flex flex-col items-center justify-center py-12 text-center">
							<Building2 className="h-12 w-12 text-muted-foreground" />
							<h3 className="mt-4 text-lg font-semibold">
								{searchTerm
									? "No organizations match your search"
									: "No organizations found"}
							</h3>
							<p className="mt-2 text-sm text-muted-foreground">
								{searchTerm
									? "Try adjusting your search term or clear the filter"
									: "Create your first organization to get started"}
							</p>
							<Button
								variant="outline"
								size="icon"
								onClick={handleCreate}
								title="Create Organization"
								className="mt-4"
							>
								<Plus className="h-4 w-4" />
							</Button>
						</div>
					)}
				</CardContent>
			</Card>

			{/* Create Dialog */}
			<Dialog open={isCreateDialogOpen} onOpenChange={handleDialogClose}>
				<DialogContent>
					<form onSubmit={handleSubmitCreate}>
						<DialogHeader>
							<DialogTitle>Create Organization</DialogTitle>
							<DialogDescription>
								Add a new customer organization to the platform
							</DialogDescription>
						</DialogHeader>
						<div className="space-y-4 py-4">
							<div className="space-y-2">
								<Label htmlFor="name">
									Organization Name *
								</Label>
								<Input
									id="name"
									value={formData.name}
									onChange={(e) =>
										setFormData({
											...formData,
											name: e.target.value,
										})
									}
									placeholder="Acme Corporation"
									required
								/>
							</div>
							<div className="space-y-2">
								<Label htmlFor="domain">Email Domain</Label>
								<Input
									id="domain"
									value={formData.domain}
									onChange={(e) =>
										setFormData({
											...formData,
											domain: e.target.value,
										})
									}
									placeholder="acme.com"
								/>
								<p className="text-xs text-muted-foreground">
									Users with this email domain will be
									auto-provisioned to this organization
								</p>
							</div>
						</div>
						<DialogFooter>
							<Button
								type="button"
								variant="outline"
								onClick={() => handleDialogClose(false)}
							>
								Cancel
							</Button>
							<Button
								type="submit"
								disabled={createMutation.isPending}
							>
								{createMutation.isPending
									? "Creating..."
									: "Create"}
							</Button>
						</DialogFooter>
					</form>
				</DialogContent>
			</Dialog>

			{/* Edit Dialog */}
			<Dialog open={isEditDialogOpen} onOpenChange={handleDialogClose}>
				<DialogContent>
					<form onSubmit={handleSubmitEdit}>
						<DialogHeader>
							<DialogTitle>Edit Organization</DialogTitle>
							<DialogDescription>
								Update organization details
							</DialogDescription>
						</DialogHeader>
						<div className="space-y-4 py-4">
							<div className="space-y-2">
								<Label htmlFor="edit-name">
									Organization Name *
								</Label>
								<Input
									id="edit-name"
									value={formData.name}
									onChange={(e) =>
										setFormData({
											...formData,
											name: e.target.value,
										})
									}
									placeholder="Acme Corporation"
									required
								/>
							</div>
							<div className="space-y-2">
								<Label htmlFor="edit-domain">
									Email Domain
								</Label>
								<Input
									id="edit-domain"
									value={formData.domain}
									onChange={(e) =>
										setFormData({
											...formData,
											domain: e.target.value,
										})
									}
									placeholder="acme.com"
								/>
								<p className="text-xs text-muted-foreground">
									Users with this email domain will be
									auto-provisioned to this organization
								</p>
							</div>
						</div>
						<DialogFooter>
							<Button
								type="button"
								variant="outline"
								onClick={() => handleDialogClose(false)}
							>
								Cancel
							</Button>
							<Button
								type="submit"
								disabled={updateMutation.isPending}
							>
								{updateMutation.isPending
									? "Updating..."
									: "Update"}
							</Button>
						</DialogFooter>
					</form>
				</DialogContent>
			</Dialog>

			{/* Delete Confirmation Dialog */}
			<AlertDialog
				open={isDeleteDialogOpen}
				onOpenChange={setIsDeleteDialogOpen}
			>
				<AlertDialogContent>
					<AlertDialogHeader>
						<AlertDialogTitle>Are you sure?</AlertDialogTitle>
						<AlertDialogDescription>
							This will permanently delete the organization "
							{selectedOrg?.name}". This action cannot be undone.
						</AlertDialogDescription>
					</AlertDialogHeader>
					<AlertDialogFooter>
						<AlertDialogCancel>Cancel</AlertDialogCancel>
						<AlertDialogAction
							onClick={handleConfirmDelete}
							className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
						>
							{deleteMutation.isPending
								? "Deleting..."
								: "Delete"}
						</AlertDialogAction>
					</AlertDialogFooter>
				</AlertDialogContent>
			</AlertDialog>
		</div>
	);
}

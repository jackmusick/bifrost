import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import {
	Plus,
	RefreshCw,
	AlertTriangle,
	Trash2,
	Link2,
	Pencil,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
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
import {
	DataTable,
	DataTableBody,
	DataTableCell,
	DataTableHead,
	DataTableHeader,
	DataTableRow,
} from "@/components/ui/data-table";
import { SearchBox } from "@/components/search/SearchBox";
import { useSearch } from "@/hooks/useSearch";
import { CreateIntegrationDialog } from "@/components/integrations/CreateIntegrationDialog";
import {
	useIntegrations,
	useDeleteIntegration,
	type Integration,
} from "@/services/integrations";
import { toast } from "sonner";

export function Integrations() {
	const navigate = useNavigate();
	const queryClient = useQueryClient();
	const [isCreateDialogOpen, setIsCreateDialogOpen] = useState(false);
	const [editIntegrationId, setEditIntegrationId] = useState<
		string | undefined
	>();
	const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
	const [integrationToDelete, setIntegrationToDelete] =
		useState<Integration | null>(null);
	const [searchTerm, setSearchTerm] = useState("");

	const { data, isLoading, refetch } = useIntegrations();
	const deleteMutation = useDeleteIntegration();

	const integrations = data?.items || [];

	// Apply search filter
	const filteredIntegrations = useSearch(integrations, searchTerm, [
		"name",
		"list_entities_data_provider_id",
	]);

	const handleCreate = () => {
		setEditIntegrationId(undefined);
		setIsCreateDialogOpen(true);
	};

	const handleEdit = (integrationId: string) => {
		setEditIntegrationId(integrationId);
		setIsCreateDialogOpen(true);
	};

	const handleOpenIntegration = (integrationId: string) => {
		navigate(`/integrations/${integrationId}`);
	};

	const handleDelete = (integration: Integration) => {
		setIntegrationToDelete(integration);
		setDeleteDialogOpen(true);
	};

	const handleConfirmDelete = async () => {
		if (!integrationToDelete) return;

		try {
			await deleteMutation.mutateAsync({
				params: { path: { integration_id: integrationToDelete.id } },
			});
			toast.success("Integration deleted successfully");
			queryClient.invalidateQueries({ queryKey: ["integrations"] });
		} catch (error) {
			console.error("Failed to delete integration:", error);
			toast.error("Failed to delete integration");
		} finally {
			setDeleteDialogOpen(false);
			setIntegrationToDelete(null);
		}
	};

	return (
		<div className="h-[calc(100vh-8rem)] flex flex-col space-y-6">
			{/* Header */}
			<div className="flex items-center justify-between">
				<div>
					<h1 className="text-4xl font-extrabold tracking-tight">
						Integrations
					</h1>
					<p className="mt-2 text-muted-foreground">
						Configure integrations and map organizations to external
						entities
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
						onClick={handleCreate}
						title="New Integration"
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
					placeholder="Search integrations by name, OAuth provider, or data provider..."
					className="max-w-md"
				/>
			</div>

			{/* Content */}
			{isLoading ? (
				<div className="space-y-2">
					{[...Array(3)].map((_, i) => (
						<Skeleton key={i} className="h-12 w-full" />
					))}
				</div>
			) : filteredIntegrations.length > 0 ? (
				<div className="flex-1 min-h-0">
					<DataTable className="max-h-full">
						<DataTableHeader>
							<DataTableRow>
								<DataTableHead>Name</DataTableHead>
								<DataTableHead>OAuth Status</DataTableHead>
								<DataTableHead>Data Provider</DataTableHead>
								<DataTableHead>Config Fields</DataTableHead>
								<DataTableHead className="text-right" />
							</DataTableRow>
						</DataTableHeader>
						<DataTableBody>
							{filteredIntegrations.map((integration) => (
								<DataTableRow
									key={integration.id}
									clickable
									onClick={() =>
										handleOpenIntegration(integration.id)
									}
								>
									<DataTableCell className="font-medium">
										{integration.name}
									</DataTableCell>
									<DataTableCell>
										{integration.has_oauth_config ? (
											<Badge
												variant="default"
												className="text-xs bg-blue-600 hover:bg-blue-700"
											>
												Configured
											</Badge>
										) : (
											<span className="text-muted-foreground text-sm">
												Not configured
											</span>
										)}
									</DataTableCell>
									<DataTableCell>
										{integration.list_entities_data_provider_id ? (
											<Badge variant="outline">
												{
													integration.list_entities_data_provider_id
												}
											</Badge>
										) : (
											<span className="text-muted-foreground text-sm">
												None
											</span>
										)}
									</DataTableCell>
									<DataTableCell>
										{integration.config_schema &&
										integration.config_schema.length > 0 ? (
											<div className="flex gap-1">
												{integration.config_schema
													.slice(0, 2)
													.map((field) => (
														<Badge
															key={field.key}
															variant="secondary"
															className="text-xs"
														>
															{field.key}
														</Badge>
													))}
												{integration.config_schema
													.length > 2 && (
													<Badge
														variant="secondary"
														className="text-xs"
													>
														+
														{integration
															.config_schema
															.length - 2}
													</Badge>
												)}
											</div>
										) : (
											<span className="text-muted-foreground text-sm">
												None
											</span>
										)}
									</DataTableCell>
									<DataTableCell
										className="text-right"
										onClick={(e) => e.stopPropagation()}
									>
										<div className="flex gap-1 justify-end">
											<Button
												variant="ghost"
												size="icon-sm"
												onClick={() =>
													handleEdit(integration.id)
												}
												title="Edit"
											>
												<Pencil className="h-4 w-4" />
											</Button>
											<Button
												variant="ghost"
												size="icon-sm"
												onClick={() =>
													handleDelete(integration)
												}
												disabled={
													deleteMutation.isPending
												}
												title="Delete"
												className="text-red-600 hover:text-red-700"
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
				<Card>
					<CardContent className="flex flex-col items-center justify-center py-12 text-center">
						<Link2 className="h-12 w-12 text-muted-foreground" />
						<h3 className="mt-4 text-lg font-semibold">
							{searchTerm
								? "No integrations match your search"
								: "No integrations"}
						</h3>
						<p className="mt-2 text-sm text-muted-foreground max-w-md">
							{searchTerm
								? "Try adjusting your search term or clear the filter"
								: "Get started by creating your first integration. Map organizations to external entities with OAuth and configuration schemas."}
						</p>
						<Button
							variant="outline"
							size="icon"
							onClick={handleCreate}
							className="mt-4"
							title="Create Integration"
						>
							<Plus className="h-4 w-4" />
						</Button>
					</CardContent>
				</Card>
			)}

			{/* Create/Edit Dialog */}
			<CreateIntegrationDialog
				open={isCreateDialogOpen}
				onOpenChange={setIsCreateDialogOpen}
				editIntegrationId={editIntegrationId}
			/>

			{/* Delete Confirmation Dialog */}
			<AlertDialog
				open={deleteDialogOpen}
				onOpenChange={setDeleteDialogOpen}
			>
				<AlertDialogContent>
					<AlertDialogHeader>
						<AlertDialogTitle className="flex items-center gap-2">
							<AlertTriangle className="h-5 w-5 text-destructive" />
							Delete Integration
						</AlertDialogTitle>
						<AlertDialogDescription className="space-y-3">
							<p>
								Are you sure you want to delete the integration{" "}
								<strong className="text-foreground">
									{integrationToDelete?.name}
								</strong>
								?
							</p>
							<p className="text-sm text-destructive">
								This will also delete all organization mappings
								for this integration. This action cannot be
								undone.
							</p>
						</AlertDialogDescription>
					</AlertDialogHeader>
					<AlertDialogFooter>
						<AlertDialogCancel>Cancel</AlertDialogCancel>
						<AlertDialogAction
							onClick={handleConfirmDelete}
							className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
						>
							Delete Integration
						</AlertDialogAction>
					</AlertDialogFooter>
				</AlertDialogContent>
			</AlertDialog>
		</div>
	);
}

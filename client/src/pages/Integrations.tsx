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
import {
	Card,
	CardContent,
	CardDescription,
	CardHeader,
	CardTitle,
} from "@/components/ui/card";
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

	const getStats = () => {
		return {
			total: integrations.length,
			withOAuth: integrations.filter((i) => i.has_oauth_config).length,
			withDataProvider: integrations.filter(
				(i) => i.list_entities_data_provider_id,
			).length,
		};
	};

	const stats = getStats();

	return (
		<div className="space-y-6">
			<div>
				<div className="flex items-center justify-between">
					<div>
						<h1 className="text-4xl font-extrabold tracking-tight">
							Integrations
						</h1>
						<p className="mt-2 text-muted-foreground">
							Configure integrations and map organizations to
							external entities
						</p>
						<p className="mt-1 text-sm text-muted-foreground">
							Set up OAuth providers, data providers, and
							configuration schemas for multi-tenant integrations
						</p>
					</div>
					<div className="flex items-center gap-2">
						<Button
							variant="ghost"
							size="icon"
							onClick={() => refetch()}
							title="Refresh list"
						>
							<RefreshCw className="h-4 w-4" />
						</Button>
						<Button onClick={handleCreate}>
							<Plus className="mr-2 h-4 w-4" />
							New Integration
						</Button>
					</div>
				</div>
			</div>

			{/* Search Box */}
			<SearchBox
				value={searchTerm}
				onChange={setSearchTerm}
				placeholder="Search integrations by name, OAuth provider, or data provider..."
				className="max-w-md"
			/>

			{/* Stats Cards */}
			<div className="grid grid-cols-1 md:grid-cols-3 gap-4">
				<Card>
					<CardHeader className="pb-2">
						<CardDescription>Total Integrations</CardDescription>
						<CardTitle className="text-3xl">
							{stats.total}
						</CardTitle>
					</CardHeader>
				</Card>
				<Card>
					<CardHeader className="pb-2">
						<CardDescription>With OAuth</CardDescription>
						<CardTitle
							className={`text-3xl ${
								stats.withOAuth > 0 ? "text-blue-600" : ""
							}`}
						>
							{stats.withOAuth}
						</CardTitle>
					</CardHeader>
				</Card>
				<Card>
					<CardHeader className="pb-2">
						<CardDescription>With Data Provider</CardDescription>
						<CardTitle
							className={`text-3xl ${
								stats.withDataProvider > 0
									? "text-green-600"
									: ""
							}`}
						>
							{stats.withDataProvider}
						</CardTitle>
					</CardHeader>
				</Card>
			</div>

			{/* Integrations Table */}
			<Card>
				<CardHeader>
					<div className="flex items-center justify-between">
						<div>
							<CardTitle>Your Integrations</CardTitle>
							<CardDescription>
								{filteredIntegrations.length > 0
									? `Showing ${filteredIntegrations.length} integration${
											filteredIntegrations.length !== 1
												? "s"
												: ""
										}`
									: searchTerm
										? "No integrations match your search"
										: "No integrations configured yet"}
							</CardDescription>
						</div>
					</div>
				</CardHeader>
				<CardContent>
					{isLoading ? (
						<div className="space-y-2">
							{[...Array(3)].map((_, i) => (
								<Skeleton key={i} className="h-12 w-full" />
							))}
						</div>
					) : filteredIntegrations.length > 0 ? (
						<DataTable>
							<DataTableHeader>
								<DataTableRow>
									<DataTableHead>Name</DataTableHead>
									<DataTableHead>OAuth Status</DataTableHead>
									<DataTableHead>Data Provider</DataTableHead>
									<DataTableHead>Config Fields</DataTableHead>
									<DataTableHead className="text-right">
										Actions
									</DataTableHead>
								</DataTableRow>
							</DataTableHeader>
							<DataTableBody>
								{filteredIntegrations.map((integration) => (
									<DataTableRow
										key={integration.id}
										clickable
										onClick={() =>
											handleOpenIntegration(
												integration.id,
											)
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
											integration.config_schema.length >
												0 ? (
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
													size="sm"
													variant="ghost"
													onClick={() =>
														handleEdit(
															integration.id,
														)
													}
													title="Edit"
												>
													<Pencil className="h-4 w-4" />
												</Button>
												<Button
													size="sm"
													variant="ghost"
													onClick={() =>
														handleDelete(
															integration,
														)
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
					) : (
						<div className="flex flex-col items-center justify-center py-12 text-center">
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
								onClick={handleCreate}
								className="mt-4"
							>
								<Plus className="mr-2 h-4 w-4" />
								Create Integration
							</Button>
						</div>
					)}
				</CardContent>
			</Card>

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

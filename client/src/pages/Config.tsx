import { useState } from "react";
import {
	Pencil,
	Plus,
	Trash2,
	Key,
	RefreshCw,
	Globe,
	Building2,
	AlertTriangle,
	Info,
	Loader2,
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
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
	DataTable,
	DataTableBody,
	DataTableCell,
	DataTableHead,
	DataTableHeader,
	DataTableRow,
} from "@/components/ui/data-table";
import { Badge } from "@/components/ui/badge";
import { SearchBox } from "@/components/search/SearchBox";
import { useSearch } from "@/hooks/useSearch";

import { useConfigs, useDeleteConfig } from "@/hooks/useConfig";
import { ConfigDialog } from "@/components/config/ConfigDialog";
import { useOrgScope } from "@/contexts/OrgScopeContext";
import type { components } from "@/lib/v1";
type ConfigType = components["schemas"]["ConfigResponse"];

export function Config() {
	const [selectedConfig, setSelectedConfig] = useState<
		ConfigType | undefined
	>();
	const [isDialogOpen, setIsDialogOpen] = useState(false);
	const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
	const [configToDelete, setConfigToDelete] = useState<ConfigType | null>(
		null,
	);
	const [searchTerm, setSearchTerm] = useState("");
	const { scope, isGlobalScope } = useOrgScope();

	// Fetch configs based on current scope
	const scopeParam = isGlobalScope ? "GLOBAL" : "org";
	const { data: configs, isFetching, refetch } = useConfigs(scopeParam);
	const deleteConfig = useDeleteConfig();

	// Apply search filter
	const filteredConfigs = useSearch(configs || [], searchTerm, [
		"key",
		"value",
		"type",
		"description",
	]);

	// React Query automatically refetches when scope changes (via orgId in query key)

	const handleEdit = (config: ConfigType) => {
		setSelectedConfig(config);
		setIsDialogOpen(true);
	};

	const handleAdd = () => {
		setSelectedConfig(undefined);
		setIsDialogOpen(true);
	};

	const handleDelete = (config: ConfigType) => {
		setConfigToDelete(config);
		setDeleteDialogOpen(true);
	};

	const handleConfirmDelete = () => {
		if (!configToDelete) return;

		deleteConfig.mutate(
			{ params: { path: { key: configToDelete.key } } },
			{
				onSettled: () => {
					setDeleteDialogOpen(false);
					setConfigToDelete(null);
				},
			},
		);
	};

	const handleDialogClose = () => {
		setIsDialogOpen(false);
		setSelectedConfig(undefined);
	};

	const getTypeBadge = (type: string) => {
		const variants: Record<
			string,
			"default" | "secondary" | "destructive" | "outline"
		> = {
			string: "default",
			int: "secondary",
			bool: "outline",
			json: "secondary",
			secret_ref: "destructive",
		};
		return <Badge variant={variants[type] || "default"}>{type}</Badge>;
	};

	const maskValue = (value: unknown, type: string) => {
		if (!value) return "-";
		const strValue = String(value);
		if (type === "secret_ref") {
			return "••••••••";
		}
		if (strValue.length > 50) {
			return strValue.substring(0, 50) + "...";
		}
		return strValue;
	};

	return (
		<div className="space-y-6">
			<div className="flex items-center justify-between">
				<div>
					<div className="flex items-center gap-3">
						<h1 className="text-4xl font-extrabold tracking-tight">
							Configuration
						</h1>
						<Badge
							variant={isGlobalScope ? "default" : "outline"}
							className="text-sm"
						>
							{isGlobalScope ? (
								<>
									<Globe className="mr-1 h-3 w-3" />
									Global
								</>
							) : (
								<>
									<Building2 className="mr-1 h-3 w-3" />
									{scope.orgName}
								</>
							)}
						</Badge>
					</div>
					<p className="mt-2 text-muted-foreground">
						{isGlobalScope
							? "Platform-wide configuration values"
							: `Configuration for ${scope.orgName}`}
					</p>
				</div>
				<div className="flex gap-2">
					<Button
						variant="outline"
						size="icon"
						onClick={() => refetch()}
						disabled={isFetching}
					>
						<RefreshCw
							className={`h-4 w-4 ${
								isFetching ? "animate-spin" : ""
							}`}
						/>
					</Button>
					<Button
						variant="outline"
						size="icon"
						onClick={handleAdd}
						title="Add Config"
					>
						<Plus className="h-4 w-4" />
					</Button>
				</div>
			</div>

			{isGlobalScope && (
				<Alert>
					<Info className="h-4 w-4" />
					<AlertDescription>
						Showing configuration from the Global partition only.
						Switch to an organization scope to see that
						organization's configuration.
					</AlertDescription>
				</Alert>
			)}

			{/* Search Box */}
			<SearchBox
				value={searchTerm}
				onChange={setSearchTerm}
				placeholder="Search config by key, value, type, or description..."
				className="max-w-md"
			/>

			<Card>
				<CardHeader>
					<div>
						<CardTitle>
							{isGlobalScope ? "Global" : "OrganizationPublic"}{" "}
							Configuration
						</CardTitle>
						<CardDescription>
							{isGlobalScope
								? "Platform-wide configuration values"
								: "Organization-specific configuration overrides"}
						</CardDescription>
					</div>
				</CardHeader>
				<CardContent>
					{isFetching ? (
						<div className="flex items-center justify-center py-12">
							<Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
						</div>
					) : filteredConfigs && filteredConfigs.length > 0 ? (
						<div className="max-h-[calc(100vh-28rem)] overflow-auto rounded-md border">
							<DataTable>
								<DataTableHeader className="sticky top-0 bg-background z-10">
									<DataTableRow>
										{isGlobalScope && (
											<DataTableHead>Scope</DataTableHead>
										)}
										<DataTableHead>Key</DataTableHead>
										<DataTableHead>Value</DataTableHead>
										<DataTableHead>Type</DataTableHead>
										<DataTableHead>
											Description
										</DataTableHead>
										<DataTableHead className="text-right">
											Actions
										</DataTableHead>
									</DataTableRow>
								</DataTableHeader>
								<DataTableBody>
									{filteredConfigs.map((config) => (
										<DataTableRow
											key={`${config.scope}-${config.key}`}
										>
											{isGlobalScope && (
												<DataTableCell>
													<Badge
														variant="default"
														className="text-xs"
													>
														<Globe className="mr-1 h-3 w-3" />
														Global
													</Badge>
												</DataTableCell>
											)}
											<DataTableCell className="font-mono">
												{config.key}
											</DataTableCell>
											<DataTableCell className="max-w-xs truncate">
												{maskValue(
													config.value,
													config.type,
												)}
											</DataTableCell>
											<DataTableCell>
												{getTypeBadge(config.type)}
											</DataTableCell>
											<DataTableCell className="max-w-xs truncate text-muted-foreground">
												{config.description || "-"}
											</DataTableCell>
											<DataTableCell className="text-right">
												<div className="flex justify-end gap-2">
													<Button
														variant="ghost"
														size="icon"
														onClick={() =>
															handleEdit(config)
														}
													>
														<Pencil className="h-4 w-4" />
													</Button>
													<Button
														variant="ghost"
														size="icon"
														onClick={() =>
															handleDelete(config)
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
							<Key className="h-12 w-12 text-muted-foreground" />
							<h3 className="mt-4 text-lg font-semibold">
								{searchTerm
									? "No configuration matches your search"
									: "No configuration found"}
							</h3>
							<p className="mt-2 text-sm text-muted-foreground">
								{searchTerm
									? "Try adjusting your search term or clear the filter"
									: "Get started by creating your first config entry"}
							</p>
							<Button
								variant="outline"
								size="icon"
								onClick={handleAdd}
								className="mt-4"
								title="Add Config"
							>
								<Plus className="h-4 w-4" />
							</Button>
						</div>
					)}
				</CardContent>
			</Card>

			<ConfigDialog
				config={selectedConfig}
				open={isDialogOpen}
				onClose={handleDialogClose}
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
							Delete Configuration
						</AlertDialogTitle>
						<AlertDialogDescription className="space-y-3">
							<p>
								Are you sure you want to delete the config{" "}
								<strong className="text-foreground">
									{configToDelete?.key}
								</strong>
								?
							</p>
							<div className="bg-muted p-3 rounded-md border border-border">
								<p className="text-sm font-medium text-foreground mb-2">
									Before deleting:
								</p>
								<p className="text-sm">
									We recommend searching for{" "}
									<code className="bg-background px-1.5 py-0.5 rounded text-xs">
										get_config('{configToDelete?.key}')
									</code>{" "}
									in your{" "}
									<code className="bg-background px-1.5 py-0.5 rounded text-xs">
										@workflows/workspace/
									</code>{" "}
									repo to confirm it isn't being used.
								</p>
							</div>
							<p className="text-sm text-destructive">
								Workflows using this config will fail if it's
								deleted. This action cannot be undone.
							</p>
						</AlertDialogDescription>
					</AlertDialogHeader>
					<AlertDialogFooter>
						<AlertDialogCancel>Cancel</AlertDialogCancel>
						<AlertDialogAction
							onClick={handleConfirmDelete}
							className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
						>
							I'm Sure - Delete Config
						</AlertDialogAction>
					</AlertDialogFooter>
				</AlertDialogContent>
			</AlertDialog>
		</div>
	);
}

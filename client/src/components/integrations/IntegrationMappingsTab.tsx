import {
	CheckCircle2,
	Plus,
	Link as LinkIcon,
	Settings,
	Pencil,
	Unlink,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
	Card,
	CardContent,
	CardDescription,
	CardHeader,
	CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
	DataTable,
	DataTableBody,
	DataTableCell,
	DataTableHead,
	DataTableHeader,
	DataTableRow,
} from "@/components/ui/data-table";
import { type IntegrationMapping } from "@/services/integrations";
import { AutoMatchControls } from "@/components/integrations/AutoMatchControls";
import { EntitySelector } from "@/components/integrations/EntitySelector";
import { MatchSuggestionBadge } from "@/components/integrations/MatchSuggestionBadge";
import type { MatchMode, MatchSuggestion, MatchResult } from "@/lib/matching";

interface MappingFormData {
	organization_id: string;
	entity_id: string;
	entity_name: string;
	oauth_token_id?: string;
	config: Record<string, unknown>;
}

export interface OrgWithMapping {
	id: string;
	name: string;
	mapping?: IntegrationMapping;
	formData: MappingFormData;
	isDirty: boolean;
}

interface ConfigSchemaField {
	key: string;
	type: string;
	required?: boolean;
}

interface Entity {
	value: string;
	label: string;
}

export interface IntegrationMappingsTabProps {
	orgsWithMappings: OrgWithMapping[];
	entities: Entity[];
	isLoadingEntities: boolean;
	isEntitiesError?: boolean;
	hasDataProvider: boolean;
	configSchema: ConfigSchemaField[];
	configDefaults: Record<string, unknown> | null | undefined;
	autoMatchSuggestions: Map<string, MatchSuggestion>;
	matchStats: MatchResult["stats"] | null;
	isMatching: boolean;
	isDeletePending: boolean;
	onRunAutoMatch: (mode: MatchMode) => void;
	onAcceptAllSuggestions: () => void;
	onClearSuggestions: () => void;
	onAcceptSuggestion: (orgId: string) => void;
	onRejectSuggestion: (orgId: string) => void;
	onUpdateOrgMapping: (orgId: string, updates: Partial<MappingFormData>) => void;
	onOpenConfigDialog: (orgId: string) => void;
	onDeleteMapping: (org: OrgWithMapping) => void;
	onEditIntegration: () => void;
}

export function IntegrationMappingsTab({
	orgsWithMappings,
	entities,
	isLoadingEntities,
	isEntitiesError,
	hasDataProvider,
	configSchema,
	configDefaults,
	autoMatchSuggestions,
	matchStats,
	isMatching,
	isDeletePending,
	onRunAutoMatch,
	onAcceptAllSuggestions,
	onClearSuggestions,
	onAcceptSuggestion,
	onRejectSuggestion,
	onUpdateOrgMapping,
	onOpenConfigDialog,
	onDeleteMapping,
	onEditIntegration,
}: IntegrationMappingsTabProps) {
	const hasNonDefaultConfig = (org: OrgWithMapping): boolean => {
		if (!org.mapping?.config || !configSchema) return false;

		const defaults = configDefaults ?? {};

		return configSchema.some((field) => {
			const currentValue = org.mapping?.config?.[field.key];
			const defaultValue = defaults[field.key];
			return currentValue !== defaultValue;
		});
	};

	return (
		<Card>
			<CardHeader className="flex flex-row items-start justify-between space-y-0">
				<div>
					<CardTitle>Organization Mappings</CardTitle>
					<CardDescription>
						Configure how each organization maps to
						external entities
					</CardDescription>
				</div>
				{/* Auto-Match Controls in header */}
				{hasDataProvider &&
					orgsWithMappings.length > 0 && (
						<AutoMatchControls
							onRunAutoMatch={onRunAutoMatch}
							onAcceptAll={onAcceptAllSuggestions}
							onClear={onClearSuggestions}
							matchStats={matchStats}
							hasSuggestions={
								autoMatchSuggestions.size > 0
							}
							isMatching={isMatching}
							disabled={isLoadingEntities}
						/>
					)}
			</CardHeader>
			<CardContent>
				{!hasDataProvider ? (
					<div className="flex flex-col items-center justify-center py-12 text-center">
						<Settings className="h-12 w-12 text-muted-foreground" />
						<h3 className="mt-4 text-lg font-semibold">
							No Data Provider Configured
						</h3>
						<p className="mt-2 text-sm text-muted-foreground max-w-md">
							Configure a data provider to populate
							the entity dropdown. Edit the
							integration to select one.
						</p>
						<Button
							variant="outline"
							className="mt-4"
							onClick={onEditIntegration}
						>
							<Pencil className="h-4 w-4 mr-2" />
							Edit Integration
						</Button>
					</div>
				) : orgsWithMappings.length === 0 ? (
					<div className="flex flex-col items-center justify-center py-12 text-center">
						<LinkIcon className="h-12 w-12 text-muted-foreground" />
						<h3 className="mt-4 text-lg font-semibold">
							No organizations available
						</h3>
						<p className="mt-2 text-sm text-muted-foreground">
							Create organizations first to set up
							mappings
						</p>
					</div>
				) : (
					<div className="rounded-md border overflow-x-auto">
						<DataTable>
							<DataTableHeader>
								<DataTableRow>
									<DataTableHead className="w-48">
										Organization
									</DataTableHead>
									<DataTableHead className="w-64">
										External Entity
									</DataTableHead>
									<DataTableHead className="w-24">
										Status
									</DataTableHead>
									<DataTableHead className="w-32 text-right">
										Actions
									</DataTableHead>
								</DataTableRow>
							</DataTableHeader>
							<DataTableBody>
								{orgsWithMappings.map((org) => {
									// Filter out entities already mapped to other orgs
									const usedEntityIds =
										orgsWithMappings
											.filter(
												(o) =>
													o.id !==
														org.id &&
													o.formData
														.entity_id,
											)
											.map(
												(o) =>
													o.formData
														.entity_id,
											);
									const availableEntities =
										entities.filter(
											(e) =>
												e.value ===
													org.formData
														.entity_id ||
												!usedEntityIds.includes(
													e.value,
												),
										);

									return (
										<DataTableRow key={org.id}>
											<DataTableCell className="font-medium">
												{org.name}
											</DataTableCell>
											<DataTableCell>
												{autoMatchSuggestions.has(
													org.id,
												) ? (
													<MatchSuggestionBadge
														suggestion={
															autoMatchSuggestions.get(
																org.id,
															)!
														}
														onAccept={() =>
															onAcceptSuggestion(
																org.id,
															)
														}
														onReject={() =>
															onRejectSuggestion(
																org.id,
															)
														}
													/>
												) : (
													<EntitySelector
														entities={
															availableEntities
														}
														value={
															org
																.formData
																.entity_id
														}
														onChange={(
															value,
															label,
														) =>
															onUpdateOrgMapping(
																org.id,
																{
																	entity_id:
																		value,
																	entity_name:
																		label,
																},
															)
														}
														isLoading={
															isLoadingEntities
														}
														isError={isEntitiesError}
														placeholder="Select entity..."
													/>
												)}
											</DataTableCell>
											<DataTableCell>
												{org.mapping ? (
													<Badge
														variant="default"
														className="bg-green-600"
													>
														<CheckCircle2 className="h-3 w-3 mr-1" />
														Mapped
													</Badge>
												) : org.formData
														.entity_id ? (
													<Badge variant="secondary">
														<Plus className="h-3 w-3 mr-1" />
														New
													</Badge>
												) : (
													<Badge variant="outline">
														Not Mapped
													</Badge>
												)}
												{org.isDirty && (
													<Badge
														variant="secondary"
														className="ml-1"
													>
														*
													</Badge>
												)}
											</DataTableCell>
											<DataTableCell className="text-right">
												<div className="flex gap-1 justify-end">
													<Button
														size="sm"
														variant="ghost"
														onClick={() =>
															onOpenConfigDialog(
																org.id,
															)
														}
														title="Configure"
														className="relative"
													>
														<Settings className="h-4 w-4" />
														{hasNonDefaultConfig(
															org,
														) && (
															<span className="absolute -top-0.5 -right-0.5 h-2 w-2 rounded-full bg-blue-600" />
														)}
													</Button>
													<Button
														size="sm"
														variant="ghost"
														onClick={() =>
															onDeleteMapping(
																org,
															)
														}
														disabled={
															!org.mapping ||
															isDeletePending
														}
														title={
															org.mapping
																? "Unlink mapping"
																: "No mapping to unlink"
														}
														className="text-red-600 hover:text-red-700 disabled:text-muted-foreground"
													>
														<Unlink className="h-4 w-4" />
													</Button>
												</div>
											</DataTableCell>
										</DataTableRow>
									);
								})}
							</DataTableBody>
						</DataTable>
					</div>
				)}
			</CardContent>
		</Card>
	);
}

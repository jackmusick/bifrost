/**
 * Knowledge Management Page
 *
 * Flat document list across all namespaces with org/namespace filters.
 * Supports multi-select for bulk scope changes and pagination.
 */

import { useState, useEffect, useCallback } from "react";
import {
	RefreshCw,
	BookOpen,
	FileText,
	Plus,
	Trash2,
	Globe,
	Building2,
	ArrowRightLeft,
	Download,
	Upload,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Checkbox } from "@/components/ui/checkbox";
import {
	DataTable,
	DataTableBody,
	DataTableCell,
	DataTableFooter,
	DataTableHead,
	DataTableHeader,
	DataTableRow,
} from "@/components/ui/data-table";
import {
	Pagination,
	PaginationContent,
	PaginationItem,
	PaginationLink,
	PaginationNext,
	PaginationPrevious,
} from "@/components/ui/pagination";
import {
	Select,
	SelectContent,
	SelectItem,
	SelectTrigger,
	SelectValue,
} from "@/components/ui/select";
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
import {
	Dialog,
	DialogContent,
	DialogDescription,
	DialogFooter,
	DialogHeader,
	DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { SearchBox } from "@/components/search/SearchBox";
import { OrganizationSelect } from "@/components/forms/OrganizationSelect";
import { useAuth } from "@/contexts/AuthContext";
import { useOrganizations } from "@/hooks/useOrganizations";
import { toast } from "sonner";
import { authFetch } from "@/lib/api-client";
import { KnowledgeDocumentDrawer } from "@/components/knowledge/KnowledgeDocumentDrawer";
import { exportEntities } from "@/services/exportImport";
import { ImportDialog } from "@/components/ImportDialog";

const PAGE_SIZE = 50;

interface DocumentSummary {
	id: string;
	namespace: string;
	key: string | null;
	content_preview: string;
	metadata: Record<string, unknown>;
	organization_id: string | null;
	created_at: string | null;
}

interface KnowledgeNamespace {
	namespace: string;
	document_count: number;
}

export function Knowledge() {
	const { isPlatformAdmin } = useAuth();
	const [documents, setDocuments] = useState<DocumentSummary[]>([]);
	const [namespaces, setNamespaces] = useState<KnowledgeNamespace[]>([]);
	const [isLoading, setIsLoading] = useState(true);
	const [searchTerm, setSearchTerm] = useState("");
	const [filterOrgId, setFilterOrgId] = useState<string | null | undefined>(
		undefined,
	);
	const [filterNamespace, setFilterNamespace] = useState<string | undefined>(
		undefined,
	);
	const [page, setPage] = useState(0);
	const [hasMore, setHasMore] = useState(false);
	const [deleteDoc, setDeleteDoc] = useState<DocumentSummary | null>(null);
	const [viewDocId, setViewDocId] = useState<string | null>(null);
	const [viewDocNamespace, setViewDocNamespace] = useState<string>("");
	const [isCreating, setIsCreating] = useState(false);
	const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
	const [bulkScopeOpen, setBulkScopeOpen] = useState(false);
	const [bulkScopeOrgId, setBulkScopeOrgId] = useState<
		string | null | undefined
	>(null);
	const [isBulkUpdating, setIsBulkUpdating] = useState(false);
	const [bulkConflictMessage, setBulkConflictMessage] = useState<
		string | null
	>(null);
	const [isImportOpen, setIsImportOpen] = useState(false);
	const [isExporting, setIsExporting] = useState(false);

	const { data: organizations } = useOrganizations({
		enabled: isPlatformAdmin,
	});

	const getOrgName = (orgId: string | null | undefined): string => {
		if (!orgId) return "Global";
		const org = organizations?.find((o) => o.id === orgId);
		return org?.name || orgId;
	};

	const fetchNamespaces = useCallback(async () => {
		try {
			const response = await authFetch("/api/knowledge-sources");
			if (response.ok) {
				const data = await response.json();
				setNamespaces(data);
			}
		} catch {
			// Non-critical — namespace filter just won't populate
		}
	}, []);

	const fetchDocuments = useCallback(async () => {
		setIsLoading(true);
		try {
			const params = new URLSearchParams();
			if (searchTerm) params.set("search", searchTerm);
			if (filterNamespace) params.set("namespace", filterNamespace);
			if (filterOrgId === null) {
				params.set("scope", "global");
			} else if (filterOrgId !== undefined) {
				params.set("scope", filterOrgId);
			}
			params.set("limit", String(PAGE_SIZE));
			params.set("offset", String(page * PAGE_SIZE));
			const qs = params.toString();
			const response = await authFetch(
				`/api/knowledge-sources/documents${qs ? `?${qs}` : ""}`,
			);
			if (response.ok) {
				const data: DocumentSummary[] = await response.json();
				setDocuments(data);
				setHasMore(data.length === PAGE_SIZE);
			}
		} catch {
			toast.error("Failed to load documents");
		} finally {
			setIsLoading(false);
		}
	}, [searchTerm, filterNamespace, filterOrgId, page]);

	// Reset page when filters change. Use the adjusting-state-on-prop-change
	// idiom to avoid a setState-in-effect cycle.
	const filtersKey = `${searchTerm}|${filterNamespace ?? ""}|${filterOrgId ?? ""}`;
	const [prevFiltersKey, setPrevFiltersKey] = useState(filtersKey);
	if (prevFiltersKey !== filtersKey) {
		setPrevFiltersKey(filtersKey);
		setPage(0);
	}

	// Network fetches: setState happens after `await`, so wrapping in a void
	// IIFE keeps the synchronous part of the effect free of setState calls.
	useEffect(() => {
		void (async () => {
			await fetchNamespaces();
		})();
	}, [fetchNamespaces]);

	useEffect(() => {
		void (async () => {
			await fetchDocuments();
		})();
	}, [fetchDocuments]);

	const handleDelete = async () => {
		if (!deleteDoc) return;
		try {
			const response = await authFetch(
				`/api/knowledge-sources/${encodeURIComponent(deleteDoc.namespace)}/documents/${deleteDoc.id}`,
				{ method: "DELETE" },
			);
			if (response.ok) {
				toast.success("Document deleted");
				fetchDocuments();
			}
		} catch {
			toast.error("Failed to delete document");
		}
		setDeleteDoc(null);
	};

	const openDocument = (doc: DocumentSummary) => {
		setViewDocNamespace(doc.namespace);
		setViewDocId(doc.id);
	};

	const toggleSelect = (id: string) => {
		setSelectedIds((prev) => {
			const next = new Set(prev);
			if (next.has(id)) {
				next.delete(id);
			} else {
				next.add(id);
			}
			return next;
		});
	};

	const toggleSelectAll = () => {
		if (selectedIds.size === documents.length) {
			setSelectedIds(new Set());
		} else {
			setSelectedIds(new Set(documents.map((d) => d.id)));
		}
	};

	const handleBulkScopeUpdate = async (forceReplace = false) => {
		if (selectedIds.size === 0) return;
		setIsBulkUpdating(true);
		try {
			const scope =
				bulkScopeOrgId === null ? "global" : (bulkScopeOrgId ?? "");
			const response = await authFetch(
				"/api/knowledge-sources/documents/scope",
				{
					method: "PATCH",
					headers: { "Content-Type": "application/json" },
					body: JSON.stringify({
						document_ids: Array.from(selectedIds),
						scope,
						replace: forceReplace,
					}),
				},
			);
			if (response.ok) {
				const result = await response.json();
				toast.success(`Updated scope for ${result.updated} documents`);
				setSelectedIds(new Set());
				setBulkScopeOpen(false);
				fetchDocuments();
			} else if (response.status === 409) {
				const err = await response.json().catch(() => ({}));
				const detail = err.detail;
				const msg =
					typeof detail === "object"
						? detail?.message
						: detail || "Resource already exists";
				setBulkScopeOpen(false);
				setBulkConflictMessage(msg);
			} else {
				const err = await response.json().catch(() => ({}));
				const detail = err.detail;
				const msg =
					typeof detail === "object"
						? detail?.message
						: detail || "Failed to update scope";
				toast.error(msg);
			}
		} catch {
			toast.error("Failed to update scope");
		} finally {
			setIsBulkUpdating(false);
		}
	};

	const handleExport = async () => {
		const ids = selectedIds.size > 0 ? Array.from(selectedIds) : [];
		setIsExporting(true);
		try {
			await exportEntities("knowledge", ids);
			toast.success("Export downloaded");
		} catch {
			toast.error("Export failed");
		} finally {
			setIsExporting(false);
		}
	};

	return (
		<div className="h-full flex flex-col space-y-6 max-w-7xl mx-auto">
			{/* Header */}
			<div className="flex items-center justify-between">
				<div>
					<h1 className="text-4xl font-extrabold tracking-tight">
						Knowledge
					</h1>
					<p className="mt-2 text-muted-foreground">
						Manage knowledge documents for AI agents
					</p>
				</div>
				<div className="flex gap-2">
					<Button
						variant="outline"
						size="icon"
						onClick={fetchDocuments}
						title="Refresh"
					>
						<RefreshCw className="h-4 w-4" />
					</Button>
					<Button
						variant="outline"
						onClick={() => setIsCreating(true)}
					>
						<Plus className="h-4 w-4 mr-1" />
						Add Document
					</Button>
				</div>
			</div>

			{/* Filters + Bulk Actions */}
			<div className="flex items-center gap-4">
				<SearchBox
					value={searchTerm}
					onChange={setSearchTerm}
					placeholder="Search documents..."
					className="flex-1"
				/>
				<Select
					value={filterNamespace ?? "__ALL__"}
					onValueChange={(v) =>
						setFilterNamespace(v === "__ALL__" ? undefined : v)
					}
				>
					<SelectTrigger className="w-48">
						<SelectValue placeholder="All namespaces" />
					</SelectTrigger>
					<SelectContent>
						<SelectItem value="__ALL__">All namespaces</SelectItem>
						{namespaces.map((ns) => (
							<SelectItem key={ns.namespace} value={ns.namespace}>
								{ns.namespace}
							</SelectItem>
						))}
					</SelectContent>
				</Select>
				{isPlatformAdmin && (
					<div className="w-64">
						<OrganizationSelect
							value={filterOrgId}
							onChange={setFilterOrgId}
							showAll={true}
							showGlobal={true}
							placeholder="All organizations"
						/>
					</div>
				)}
				{isPlatformAdmin && (
					<div className="flex items-center gap-2 ml-auto">
						{selectedIds.size > 0 && (
							<>
								<span className="text-sm text-muted-foreground">
									{selectedIds.size} selected
								</span>
								<Button
									variant="outline"
									size="sm"
									onClick={() => {
										setBulkScopeOrgId(null);
										setBulkScopeOpen(true);
									}}
								>
									<ArrowRightLeft className="h-4 w-4 mr-1" />
									Change Scope
								</Button>
							</>
						)}
						<Button
							variant="outline"
							size="sm"
							onClick={handleExport}
							disabled={isExporting}
						>
							<Download className="h-4 w-4 mr-1" />
							{selectedIds.size > 0
								? `Export (${selectedIds.size})`
								: "Export All"}
						</Button>
						<Button
							variant="outline"
							size="sm"
							onClick={() => setIsImportOpen(true)}
						>
							<Upload className="h-4 w-4 mr-1" />
							Import
						</Button>
					</div>
				)}
			</div>

			{/* Content */}
			{isLoading ? (
				<div className="space-y-2">
					{[...Array(5)].map((_, i) => (
						<Skeleton key={i} className="h-12 w-full" />
					))}
				</div>
			) : documents.length > 0 ? (
				<div className="flex-1 min-h-0 flex flex-col">
					<div className="flex-1 min-h-0">
						<DataTable className="max-h-full">
							<DataTableHeader>
								<DataTableRow>
									{isPlatformAdmin && (
										<DataTableHead className="w-10">
											<Checkbox
												checked={
													documents.length > 0 &&
													selectedIds.size ===
														documents.length
												}
												onCheckedChange={
													toggleSelectAll
												}
											/>
										</DataTableHead>
									)}
									<DataTableHead className="w-0 whitespace-nowrap">Scope</DataTableHead>
									<DataTableHead className="w-0 whitespace-nowrap">Namespace</DataTableHead>
									<DataTableHead>Key</DataTableHead>
									<DataTableHead className="w-0 whitespace-nowrap">Created</DataTableHead>
									<DataTableHead className="w-0 whitespace-nowrap text-right" />
								</DataTableRow>
							</DataTableHeader>
							<DataTableBody>
								{documents.map((doc) => (
									<DataTableRow
										key={doc.id}
										className="cursor-pointer"
										onClick={() => openDocument(doc)}
									>
										{isPlatformAdmin && (
											<DataTableCell>
												<Checkbox
													checked={selectedIds.has(
														doc.id,
													)}
													onCheckedChange={() =>
														toggleSelect(doc.id)
													}
													onClick={(e) =>
														e.stopPropagation()
													}
												/>
											</DataTableCell>
										)}
										<DataTableCell className="w-0 whitespace-nowrap">
											{doc.organization_id ? (
												<Badge
													variant="outline"
													className="text-xs"
												>
													<Building2 className="mr-1 h-3 w-3" />
													{getOrgName(
														doc.organization_id,
													)}
												</Badge>
											) : (
												<Badge
													variant="default"
													className="text-xs"
												>
													<Globe className="mr-1 h-3 w-3" />
													Global
												</Badge>
											)}
										</DataTableCell>
										<DataTableCell className="w-0 whitespace-nowrap">
											<div className="flex items-center gap-2">
												<BookOpen className="h-4 w-4 text-muted-foreground shrink-0" />
												{doc.namespace}
											</div>
										</DataTableCell>
										<DataTableCell className="font-mono text-xs">
											{doc.key || "-"}
										</DataTableCell>
										<DataTableCell className="w-0 whitespace-nowrap text-xs text-muted-foreground">
											{doc.created_at
												? new Date(
														doc.created_at,
													).toLocaleDateString()
												: "-"}
										</DataTableCell>
										<DataTableCell className="w-0 whitespace-nowrap text-right">
											<Button
												variant="ghost"
												size="icon-sm"
												onClick={(e) => {
													e.stopPropagation();
													setDeleteDoc(doc);
												}}
											>
												<Trash2 className="h-4 w-4" />
											</Button>
										</DataTableCell>
									</DataTableRow>
								))}
							</DataTableBody>
							{(page > 0 || hasMore) && (
								<DataTableFooter>
									<DataTableRow>
										<DataTableCell
											colSpan={isPlatformAdmin ? 6 : 5}
											className="p-0"
										>
											<div className="px-6 py-4 flex items-center justify-center">
												<Pagination>
													<PaginationContent>
														<PaginationItem>
															<PaginationPrevious
																onClick={(e) => {
																	e.preventDefault();
																	setPage((p) => p - 1);
																}}
																className={
																	page === 0
																		? "pointer-events-none opacity-50"
																		: "cursor-pointer"
																}
																aria-disabled={page === 0}
															/>
														</PaginationItem>
														<PaginationItem>
															<PaginationLink isActive>
																{page + 1}
															</PaginationLink>
														</PaginationItem>
														<PaginationItem>
															<PaginationNext
																onClick={(e) => {
																	e.preventDefault();
																	setPage((p) => p + 1);
																}}
																className={
																	!hasMore
																		? "pointer-events-none opacity-50"
																		: "cursor-pointer"
																}
																aria-disabled={!hasMore}
															/>
														</PaginationItem>
													</PaginationContent>
												</Pagination>
											</div>
										</DataTableCell>
									</DataTableRow>
								</DataTableFooter>
							)}
						</DataTable>
					</div>
				</div>
			) : (
				<Card>
					<CardContent className="flex flex-col items-center justify-center py-12 text-center">
						<FileText className="h-12 w-12 text-muted-foreground" />
						<h3 className="mt-4 text-lg font-semibold">
							{page > 0
								? "No more documents"
								: "No documents found"}
						</h3>
						<p className="mt-2 text-sm text-muted-foreground">
							{page > 0
								? "You've reached the end of the results."
								: "Add documents to knowledge namespaces for AI agent RAG"}
						</p>
						{page > 0 ? (
							<Button
								variant="outline"
								onClick={() => setPage(0)}
								className="mt-4"
							>
								Back to first page
							</Button>
						) : (
							<Button
								variant="outline"
								onClick={() => setIsCreating(true)}
								className="mt-4"
							>
								<Plus className="h-4 w-4 mr-2" />
								Add Document
							</Button>
						)}
					</CardContent>
				</Card>
			)}

			{/* Delete Confirmation */}
			<AlertDialog
				open={!!deleteDoc}
				onOpenChange={() => setDeleteDoc(null)}
			>
				<AlertDialogContent>
					<AlertDialogHeader>
						<AlertDialogTitle>Delete Document?</AlertDialogTitle>
						<AlertDialogDescription>
							This will permanently delete this document and its
							embeddings.
						</AlertDialogDescription>
					</AlertDialogHeader>
					<AlertDialogFooter>
						<AlertDialogCancel>Cancel</AlertDialogCancel>
						<AlertDialogAction
							onClick={handleDelete}
							className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
						>
							Delete
						</AlertDialogAction>
					</AlertDialogFooter>
				</AlertDialogContent>
			</AlertDialog>

			{/* Bulk Scope Change Dialog */}
			<Dialog open={bulkScopeOpen} onOpenChange={setBulkScopeOpen}>
				<DialogContent className="sm:max-w-md">
					<DialogHeader>
						<DialogTitle>Change Scope</DialogTitle>
						<DialogDescription>
							Update the organization scope for{" "}
							{selectedIds.size} selected document
							{selectedIds.size !== 1 ? "s" : ""}.
						</DialogDescription>
					</DialogHeader>
					<div className="space-y-2 py-4">
						<Label>Target Organization</Label>
						<OrganizationSelect
							value={bulkScopeOrgId}
							onChange={setBulkScopeOrgId}
							showGlobal={true}
						/>
					</div>
					<DialogFooter>
						<Button
							variant="outline"
							onClick={() => setBulkScopeOpen(false)}
						>
							Cancel
						</Button>
						<Button
							onClick={() => handleBulkScopeUpdate(false)}
							disabled={isBulkUpdating}
						>
							{isBulkUpdating ? "Updating..." : "Update Scope"}
						</Button>
					</DialogFooter>
				</DialogContent>
			</Dialog>

			{/* Bulk Replace Confirmation */}
			<AlertDialog
				open={!!bulkConflictMessage}
				onOpenChange={() => setBulkConflictMessage(null)}
			>
				<AlertDialogContent>
					<AlertDialogHeader>
						<AlertDialogTitle>
							Replace Existing Documents?
						</AlertDialogTitle>
						<AlertDialogDescription>
							{bulkConflictMessage} Do you want to replace them?
						</AlertDialogDescription>
					</AlertDialogHeader>
					<AlertDialogFooter>
						<AlertDialogCancel>Cancel</AlertDialogCancel>
						<AlertDialogAction
							onClick={() => {
								setBulkConflictMessage(null);
								handleBulkScopeUpdate(true);
							}}
						>
							Replace
						</AlertDialogAction>
					</AlertDialogFooter>
				</AlertDialogContent>
			</AlertDialog>

			{/* Import Dialog */}
			<ImportDialog
				open={isImportOpen}
				onOpenChange={setIsImportOpen}
				entityType="knowledge"
				onImportComplete={() => fetchDocuments()}
			/>

			{/* Document Drawer */}
			<KnowledgeDocumentDrawer
				namespace={viewDocNamespace}
				documentId={viewDocId}
				isCreating={isCreating}
				onClose={() => {
					setViewDocId(null);
					setViewDocNamespace("");
					setIsCreating(false);
					fetchDocuments();
					fetchNamespaces();
				}}
			/>
		</div>
	);
}

export default Knowledge;

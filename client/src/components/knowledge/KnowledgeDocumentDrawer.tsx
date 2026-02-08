/**
 * Knowledge Document Drawer
 *
 * Sheet component for editing and creating documents.
 * Uses the TiptapEditor for rich markdown editing.
 * Documents always open in editable mode.
 */

import { useState, useEffect, useCallback } from "react";
import { Save, X, ChevronDown, ChevronRight } from "lucide-react";
import {
	Sheet,
	SheetContent,
	SheetHeader,
	SheetTitle,
} from "@/components/ui/sheet";
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
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { TiptapEditor } from "@/components/ui/tiptap-editor";
import { OrganizationSelect } from "@/components/forms/OrganizationSelect";
import { VariablesTreeView } from "@/components/ui/variables-tree-view";
import {
	Collapsible,
	CollapsibleContent,
	CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { useAuth } from "@/contexts/AuthContext";
import { toast } from "sonner";
import { authFetch } from "@/lib/api-client";

interface KnowledgeDocumentDrawerProps {
	namespace: string;
	documentId: string | null;
	isCreating: boolean;
	onClose: () => void;
}

interface DocumentFull {
	id: string;
	namespace: string;
	key: string | null;
	content: string;
	metadata: Record<string, unknown>;
	organization_id: string | null;
	created_at: string | null;
	updated_at: string | null;
}

function MetadataSection({ metadata }: { metadata: Record<string, unknown> }) {
	const [open, setOpen] = useState(false);
	return (
		<Collapsible open={open} onOpenChange={setOpen}>
			<CollapsibleTrigger className="flex items-center gap-1 text-sm font-medium text-muted-foreground hover:text-foreground transition-colors">
				{open ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
				Metadata
			</CollapsibleTrigger>
			<CollapsibleContent className="mt-2">
				<VariablesTreeView data={metadata} />
			</CollapsibleContent>
		</Collapsible>
	);
}

export function KnowledgeDocumentDrawer({
	namespace,
	documentId,
	isCreating,
	onClose,
}: KnowledgeDocumentDrawerProps) {
	const { isPlatformAdmin, user } = useAuth();
	const [document, setDocument] = useState<DocumentFull | null>(null);
	const [content, setContent] = useState("");
	const [key, setKey] = useState("");
	const [createNamespace, setCreateNamespace] = useState("");
	const [scopeOrgId, setScopeOrgId] = useState<string | null | undefined>(
		null,
	);
	const [isSaving, setIsSaving] = useState(false);
	const [conflictMessage, setConflictMessage] = useState<string | null>(null);

	const isOpen = !!documentId || isCreating;

	const loadDocument = useCallback(async () => {
		if (!documentId || !namespace) return;
		try {
			const response = await authFetch(
				`/api/knowledge-sources/${encodeURIComponent(namespace)}/documents/${documentId}`,
			);
			if (response.ok) {
				const data: DocumentFull = await response.json();
				setDocument(data);
				setContent(data.content);
				setKey(data.key || "");
				setScopeOrgId(data.organization_id ?? null);
			}
		} catch {
			toast.error("Failed to load document");
		}
	}, [documentId, namespace]);

	useEffect(() => {
		if (documentId) {
			loadDocument();
		} else if (isCreating) {
			setDocument(null);
			setContent("");
			setKey("");
			setCreateNamespace("");
			setScopeOrgId(
				isPlatformAdmin ? null : (user?.organizationId ?? null),
			);
		}
	}, [
		documentId,
		isCreating,
		loadDocument,
		isPlatformAdmin,
		user?.organizationId,
	]);

	const handleSave = async (forceReplace = false) => {
		if (!content.trim()) {
			toast.error("Content is required");
			return;
		}

		setIsSaving(true);
		try {
			if (isCreating) {
				const ns = createNamespace.trim();
				if (!ns) {
					toast.error("Namespace is required");
					setIsSaving(false);
					return;
				}
				const params = new URLSearchParams();
				if (scopeOrgId === null) {
					params.set("scope", "global");
				} else if (scopeOrgId) {
					params.set("scope", scopeOrgId);
				}
				const qs = params.toString();
				const response = await authFetch(
					`/api/knowledge-sources/${encodeURIComponent(ns)}/documents${qs ? `?${qs}` : ""}`,
					{
						method: "POST",
						headers: { "Content-Type": "application/json" },
						body: JSON.stringify({
							content: content.trim(),
							key: key.trim() || null,
							metadata: {},
						}),
					},
				);
				if (response.ok) {
					toast.success("Document created");
					onClose();
				} else if (response.status === 409) {
					const err = await response.json().catch(() => ({}));
					const detail = err.detail;
					const msg =
						typeof detail === "object"
							? detail?.message
							: detail || "Resource already exists";
					toast.error(msg);
				} else {
					const err = await response.json().catch(() => ({}));
					toast.error(err.detail || "Failed to create document");
				}
			} else if (documentId && namespace) {
				const params = new URLSearchParams();
				if (scopeOrgId === null) {
					params.set("scope", "global");
				} else if (scopeOrgId) {
					params.set("scope", scopeOrgId);
				}
				if (forceReplace) {
					params.set("replace", "true");
				}
				const qs = params.toString();
				const response = await authFetch(
					`/api/knowledge-sources/${encodeURIComponent(namespace)}/documents/${documentId}${qs ? `?${qs}` : ""}`,
					{
						method: "PUT",
						headers: { "Content-Type": "application/json" },
						body: JSON.stringify({
							content: content.trim(),
							metadata: document?.metadata || {},
						}),
					},
				);
				if (response.ok) {
					toast.success("Document updated");
					onClose();
				} else if (response.status === 409) {
					const err = await response.json().catch(() => ({}));
					const detail = err.detail;
					const msg =
						typeof detail === "object"
							? detail?.message
							: detail || "Resource already exists";
					setConflictMessage(msg);
				} else {
					const err = await response.json().catch(() => ({}));
					toast.error(err.detail || "Failed to update document");
				}
			}
		} catch {
			toast.error("Failed to save document");
		} finally {
			setIsSaving(false);
		}
	};

	return (
		<>
			<Sheet open={isOpen} onOpenChange={() => onClose()}>
				<SheetContent className="sm:max-w-[800px] flex flex-col">
					<SheetHeader>
						<SheetTitle>
							{isCreating
								? "New Document"
								: (document?.key || "Document")}
						</SheetTitle>
					</SheetHeader>

					<div className="flex-1 flex flex-col gap-4 overflow-hidden mt-4 px-6">
						{/* Scope selector - shown at top for platform admins */}
						{isPlatformAdmin && (
							<div className="space-y-2">
								<Label>Organization</Label>
								<OrganizationSelect
									value={scopeOrgId}
									onChange={setScopeOrgId}
									showGlobal={true}
								/>
							</div>
						)}

						{/* Create-mode fields */}
						{isCreating && (
							<>
								<div className="space-y-2">
									<Label htmlFor="doc-namespace">
										Namespace
									</Label>
									<Input
										id="doc-namespace"
										value={createNamespace}
										onChange={(e) =>
											setCreateNamespace(e.target.value)
										}
										placeholder="e.g. company-docs"
									/>
								</div>
								<div className="space-y-2">
									<Label htmlFor="doc-key">
										Key (optional)
									</Label>
									<Input
										id="doc-key"
										value={key}
										onChange={(e) => setKey(e.target.value)}
										placeholder="unique-document-key"
									/>
								</div>
							</>
						)}

						{/* Editor */}
						<div className="flex-1 min-h-0 border rounded-md overflow-hidden">
							<TiptapEditor
								content={content}
								onChange={setContent}
								className="h-full border-0 rounded-none grid grid-rows-[auto_1fr] [&>div:last-child]:min-h-0 [&>div:last-child]:overflow-y-auto [&_.tiptap-editor]:!max-h-none"
							/>
						</div>

						{/* Metadata (view mode only) */}
						{!isCreating && document && Object.keys(document.metadata).length > 0 && (
							<MetadataSection metadata={document.metadata} />
						)}

						{/* Actions - always show Save and Cancel */}
						<div className="flex justify-end gap-2 py-2 pb-6">
							<Button
								variant="outline"
								onClick={() => {
									if (!isCreating && document) {
										setContent(document.content || "");
										setScopeOrgId(
											document.organization_id ?? null,
										);
									}
									onClose();
								}}
							>
								<X className="h-4 w-4 mr-1" />
								Cancel
							</Button>
							<Button
								onClick={() => handleSave(false)}
								disabled={isSaving}
							>
								<Save className="h-4 w-4 mr-1" />
								{isSaving ? "Saving..." : "Save"}
							</Button>
						</div>
					</div>
				</SheetContent>
			</Sheet>

			{/* Replace confirmation dialog */}
			<AlertDialog
				open={!!conflictMessage}
				onOpenChange={() => setConflictMessage(null)}
			>
				<AlertDialogContent>
					<AlertDialogHeader>
						<AlertDialogTitle>
							Replace Existing Document?
						</AlertDialogTitle>
						<AlertDialogDescription>
							{conflictMessage} Do you want to replace it?
						</AlertDialogDescription>
					</AlertDialogHeader>
					<AlertDialogFooter>
						<AlertDialogCancel>Cancel</AlertDialogCancel>
						<AlertDialogAction
							onClick={() => {
								setConflictMessage(null);
								handleSave(true);
							}}
						>
							Replace
						</AlertDialogAction>
					</AlertDialogFooter>
				</AlertDialogContent>
			</AlertDialog>
		</>
	);
}

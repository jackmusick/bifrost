/**
 * AppReplacePathDialog
 *
 * Repoints an application's `repo_path` to a new source directory. Two-phase UI:
 *   pick     — folder picker + path text input + force toggle
 *   validated — inline validation results panel after the replace succeeds
 *
 * Mirrors the CLI `bifrost apps replace --repo-path` flag surface, including
 * `--force` which bypasses uniqueness / nesting / source-exists checks.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
	AlertTriangle,
	ArrowRightLeft,
	CheckCircle2,
	ChevronDown,
	ChevronRight,
	Folder,
	FolderOpen,
	Loader2,
	XCircle,
} from "lucide-react";
import {
	Dialog,
	DialogContent,
	DialogDescription,
	DialogFooter,
	DialogHeader,
	DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import {
	Collapsible,
	CollapsibleContent,
	CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { workspaceOperations } from "@/components/file-tree/adapters/workspaceOperations";
import type { FileNode } from "@/components/file-tree";
import {
	useApplications,
	useReplaceApplication,
	useValidateApplication,
	type ApplicationPublic,
} from "@/hooks/useApplications";
import type { components } from "@/lib/v1";

type ValidationResponse = components["schemas"]["AppValidationResponse"];
type ValidationIssue = components["schemas"]["AppValidationIssue"];

interface AppReplacePathDialogProps {
	app: ApplicationPublic;
	open: boolean;
	onClose: () => void;
	onSuccess?: () => void;
}

type Phase = "pick" | "replacing" | "validated";

/** Single folder row in the picker tree. */
interface FolderRowProps {
	node: FileNode;
	level: number;
	selected: boolean;
	expanded: boolean;
	loading: boolean;
	onToggle: (path: string) => void;
	onSelect: (path: string) => void;
}

function FolderRow({
	node,
	level,
	selected,
	expanded,
	loading,
	onToggle,
	onSelect,
}: FolderRowProps) {
	return (
		<button
			type="button"
			onClick={() => onSelect(node.path)}
			onDoubleClick={() => onToggle(node.path)}
			className={cn(
				"flex items-center w-full py-1 px-2 text-sm transition-colors text-left rounded",
				selected ? "bg-primary/10 text-primary" : "hover:bg-muted/50",
			)}
			style={{ paddingLeft: `${level * 12 + 4}px` }}
		>
			<span
				className="inline-flex h-5 w-5 items-center justify-center mr-1"
				role="button"
				tabIndex={-1}
				onClick={(e) => {
					e.stopPropagation();
					onToggle(node.path);
				}}
			>
				{loading ? (
					<Loader2 className="h-3 w-3 animate-spin text-muted-foreground" />
				) : expanded ? (
					<ChevronDown className="h-3 w-3 text-muted-foreground" />
				) : (
					<ChevronRight className="h-3 w-3 text-muted-foreground" />
				)}
			</span>
			{expanded ? (
				<FolderOpen className="h-4 w-4 mr-1.5 text-muted-foreground" />
			) : (
				<Folder className="h-4 w-4 mr-1.5 text-muted-foreground" />
			)}
			<span className="truncate font-mono text-xs">{node.name}</span>
		</button>
	);
}

/**
 * Lightweight folder picker backed by `workspaceOperations.list`.
 *
 * Lazily loads directory contents on expand. File nodes are hidden — only
 * folders are rendered and selectable.
 */
function FolderPicker({
	selectedPath,
	onSelectPath,
}: {
	selectedPath: string;
	onSelectPath: (path: string) => void;
}) {
	const [childrenByPath, setChildrenByPath] = useState<
		Record<string, FileNode[]>
	>({});
	const [expanded, setExpanded] = useState<Set<string>>(new Set());
	const [loadingPaths, setLoadingPaths] = useState<Set<string>>(new Set());

	const loadPath = useCallback(async (path: string) => {
		setLoadingPaths((prev) => new Set(prev).add(path));
		try {
			const nodes = await workspaceOperations.list(path);
			setChildrenByPath((prev) => ({ ...prev, [path]: nodes }));
		} finally {
			setLoadingPaths((prev) => {
				const next = new Set(prev);
				next.delete(path);
				return next;
			});
		}
	}, []);

	// Load root on mount
	useEffect(() => {
		loadPath("");
	}, [loadPath]);

	const toggle = useCallback(
		(path: string) => {
			const isExpanded = expanded.has(path);
			if (isExpanded) {
				setExpanded((prev) => {
					const next = new Set(prev);
					next.delete(path);
					return next;
				});
				return;
			}
			setExpanded((prev) => new Set(prev).add(path));
			if (!childrenByPath[path]) {
				loadPath(path);
			}
		},
		[expanded, childrenByPath, loadPath],
	);

	// Auto-expand ancestors of the selectedPath when it changes (so the text
	// field → tree sync works). Only expand, never collapse.
	useEffect(() => {
		if (!selectedPath) return;
		const parts = selectedPath.split("/");
		const ancestors: string[] = [];
		for (let i = 1; i < parts.length; i++) {
			ancestors.push(parts.slice(0, i).join("/"));
		}
		setExpanded((prev) => {
			let changed = false;
			const next = new Set(prev);
			for (const a of ancestors) {
				if (!next.has(a)) {
					next.add(a);
					changed = true;
				}
			}
			return changed ? next : prev;
		});
		for (const a of ancestors) {
			if (!childrenByPath[a] && !loadingPaths.has(a)) {
				loadPath(a);
			}
		}
	}, [selectedPath, childrenByPath, loadingPaths, loadPath]);

	const renderLevel = (parentPath: string, level: number): React.ReactNode => {
		const nodes = childrenByPath[parentPath];
		if (!nodes) return null;
		const folders = nodes.filter((n) => n.type === "folder");
		return folders.map((node) => (
			<div key={node.path}>
				<FolderRow
					node={node}
					level={level}
					selected={selectedPath === node.path}
					expanded={expanded.has(node.path)}
					loading={loadingPaths.has(node.path)}
					onToggle={toggle}
					onSelect={onSelectPath}
				/>
				{expanded.has(node.path) && renderLevel(node.path, level + 1)}
			</div>
		));
	};

	const rootLoading = loadingPaths.has("") && !childrenByPath[""];

	return (
		<div className="border rounded-md max-h-64 overflow-auto p-1 bg-muted/20">
			{rootLoading ? (
				<div className="flex items-center justify-center py-4 text-sm text-muted-foreground">
					<Loader2 className="h-4 w-4 animate-spin mr-2" />
					Loading workspace…
				</div>
			) : (
				renderLevel("", 0)
			)}
		</div>
	);
}

interface ValidationSection {
	title: string;
	issues: ValidationIssue[];
	variant: "error" | "warning";
}

function ValidationResultsPanel({
	result,
}: {
	result: ValidationResponse | null;
}) {
	if (!result) return null;

	if (result.valid && result.warnings.length === 0) {
		return (
			<div className="flex items-center gap-2 p-3 rounded-md bg-green-50 dark:bg-green-950 text-green-700 dark:text-green-300 text-sm">
				<CheckCircle2 className="h-4 w-4 shrink-0" />
				<span>No issues found. Your app source looks good.</span>
			</div>
		);
	}

	const sections: ValidationSection[] = [];
	if (result.errors.length > 0) {
		sections.push({
			title: `Errors (${result.errors.length})`,
			issues: result.errors,
			variant: "error",
		});
	}
	if (result.warnings.length > 0) {
		sections.push({
			title: `Warnings (${result.warnings.length})`,
			issues: result.warnings,
			variant: "warning",
		});
	}

	return (
		<div className="space-y-3">
			{sections.map((section) => (
				<div key={section.title} className="border rounded-md">
					<div
						className={cn(
							"px-3 py-2 text-sm font-medium border-b flex items-center gap-2",
							section.variant === "error"
								? "bg-destructive/10 text-destructive"
								: "bg-yellow-50 dark:bg-yellow-950 text-yellow-700 dark:text-yellow-300",
						)}
					>
						{section.variant === "error" ? (
							<XCircle className="h-4 w-4" />
						) : (
							<AlertTriangle className="h-4 w-4" />
						)}
						{section.title}
					</div>
					<ul className="divide-y text-sm">
						{section.issues.map((issue, idx) => (
							<li key={idx} className="px-3 py-2">
								<div className="flex items-start gap-2">
									<Badge variant="outline" className="text-xs shrink-0">
										{issue.severity}
									</Badge>
									<div className="min-w-0 flex-1">
										<div className="font-mono text-xs text-muted-foreground truncate">
											{issue.file}
											{issue.line != null && `:${issue.line}`}
										</div>
										<div className="text-sm">{issue.message}</div>
									</div>
								</div>
							</li>
						))}
					</ul>
				</div>
			))}
		</div>
	);
}

function AppReplacePathDialogBody({
	app,
	onClose,
	onSuccess,
}: {
	app: ApplicationPublic;
	onClose: () => void;
	onSuccess?: () => void;
}) {
	const navigate = useNavigate();
	const replaceApp = useReplaceApplication();
	const validateApp = useValidateApplication();
	const { data: appList } = useApplications();

	const [phase, setPhase] = useState<Phase>("pick");
	const [targetPath, setTargetPathState] = useState("");
	const [force, setForce] = useState(false);
	const [advancedOpen, setAdvancedOpen] = useState(false);
	const [targetHasFiles, setTargetHasFiles] = useState<boolean | null>(null);
	const [targetChecking, setTargetChecking] = useState(false);
	const [validationResult, setValidationResult] =
		useState<ValidationResponse | null>(null);

	// Probing state for the source-exists check. We run it from the setter
	// rather than an effect so we can satisfy react-hooks/set-state-in-effect.
	const probeTokenRef = useRef(0);

	const setTargetPath = useCallback((next: string) => {
		setTargetPathState(next);
		const token = ++probeTokenRef.current;
		if (!next) {
			setTargetHasFiles(null);
			setTargetChecking(false);
			return;
		}
		setTargetChecking(true);
		workspaceOperations
			.list(next)
			.then((nodes) => {
				if (probeTokenRef.current !== token) return;
				setTargetHasFiles(nodes.some((n) => n.type === "file"));
			})
			.catch(() => {
				if (probeTokenRef.current !== token) return;
				setTargetHasFiles(false);
			})
			.finally(() => {
				if (probeTokenRef.current !== token) return;
				setTargetChecking(false);
			});
	}, []);

	// Client-side pre-flight warnings so the user sees feedback before submitting.
	const warnings = useMemo(() => {
		const out: { kind: "uniqueness" | "nesting" | "empty"; message: string }[] =
			[];
		if (!targetPath) return out;
		const normalized = targetPath.replace(/\/$/, "");
		if (normalized === app.repo_path) {
			return out;
		}
		const others = (appList?.applications ?? []).filter((a) => a.id !== app.id);
		const exactMatch = others.find((a) => a.repo_path === normalized);
		if (exactMatch) {
			out.push({
				kind: "uniqueness",
				message: `Path is already claimed by "${exactMatch.name}".`,
			});
		}
		for (const other of others) {
			if (!other.repo_path) continue;
			if (normalized.startsWith(`${other.repo_path}/`)) {
				out.push({
					kind: "nesting",
					message: `Path is nested under "${other.name}" (${other.repo_path}).`,
				});
				break;
			}
			if (other.repo_path.startsWith(`${normalized}/`)) {
				out.push({
					kind: "nesting",
					message: `Path would contain "${other.name}" (${other.repo_path}) nested inside it.`,
				});
				break;
			}
		}
		if (targetHasFiles === false && !targetChecking) {
			out.push({
				kind: "empty",
				message:
					"No source files found at this path. Enable Force if you plan to push files next.",
			});
		}
		return out;
	}, [targetPath, app, appList, targetHasFiles, targetChecking]);

	const hasBlockingWarning = warnings.length > 0;
	const canReplace =
		!!targetPath &&
		targetPath !== app.repo_path &&
		(!hasBlockingWarning || force);

	const handleReplace = async () => {
		setPhase("replacing");
		try {
			await replaceApp.mutateAsync({
				params: { path: { app_id: app.id } },
				body: { repo_path: targetPath, force },
			});
			onSuccess?.();
			// Run validation and move into the validated phase
			try {
				const result = await validateApp.mutateAsync({
					params: { path: { app_id: app.id } },
				});
				setValidationResult(result);
			} catch {
				setValidationResult(null);
			}
			setPhase("validated");
		} catch {
			setPhase("pick");
		}
	};

	const handleClose = onClose;

	return (
		<DialogContent className="max-w-xl">
			<DialogHeader>
				<DialogTitle className="flex items-center gap-2">
					<ArrowRightLeft className="h-5 w-5" />
					Replace app path
				</DialogTitle>
				<DialogDescription>
					Repoint <span className="font-medium">{app.name}</span> to a
					different source directory. Current path:{" "}
					<code className="bg-muted px-1 py-0.5 rounded text-xs">
						{app.repo_path}
					</code>
				</DialogDescription>
			</DialogHeader>

			{phase === "validated" ? (
					<div className="space-y-4">
						<div className="flex items-center gap-2 p-3 rounded-md bg-muted text-sm">
							<CheckCircle2 className="h-4 w-4 text-green-600" />
							Path replaced. Now pointing to{" "}
							<code className="bg-background px-1 py-0.5 rounded text-xs">
								{targetPath}
							</code>
						</div>
						<ValidationResultsPanel result={validationResult} />
						<DialogFooter>
							<Button variant="outline" onClick={handleClose}>
								Close
							</Button>
							<Button
								onClick={() => {
									navigate(`/apps/${app.slug}/edit`);
									handleClose();
								}}
							>
								Open app
							</Button>
						</DialogFooter>
					</div>
				) : (
					<div className="space-y-4">
						<div className="space-y-2">
							<label
								htmlFor="target-path"
								className="text-sm font-medium"
							>
								New path
							</label>
							<Input
								id="target-path"
								value={targetPath}
								onChange={(e) => setTargetPath(e.target.value)}
								placeholder="apps/my-app-v2"
								className="font-mono text-sm"
								disabled={phase === "replacing"}
							/>
							<FolderPicker
								selectedPath={targetPath}
								onSelectPath={setTargetPath}
							/>
						</div>

						{warnings.length > 0 && (
							<div className="space-y-2">
								{warnings.map((w) => (
									<div
										key={w.kind}
										className={cn(
											"flex items-start gap-2 p-3 rounded-md text-sm",
											w.kind === "empty"
												? "bg-yellow-50 dark:bg-yellow-950 text-yellow-700 dark:text-yellow-300"
												: "bg-destructive/10 text-destructive",
										)}
									>
										<AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
										<span>{w.message}</span>
									</div>
								))}
							</div>
						)}

						<Collapsible
							open={advancedOpen}
							onOpenChange={setAdvancedOpen}
						>
							<CollapsibleTrigger asChild>
								<button
									type="button"
									className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
								>
									{advancedOpen ? (
										<ChevronDown className="h-3 w-3" />
									) : (
										<ChevronRight className="h-3 w-3" />
									)}
									Advanced
								</button>
							</CollapsibleTrigger>
							<CollapsibleContent className="pt-3">
								<label className="flex items-start gap-2 text-sm">
									<Checkbox
										checked={force}
										onCheckedChange={(v) => setForce(v === true)}
										disabled={phase === "replacing"}
										className="mt-0.5"
									/>
									<span>
										<span className="font-medium">
											Force (skip validation)
										</span>
										<span className="block text-xs text-muted-foreground">
											Bypass uniqueness, nesting, and source-exists
											checks. Matches the CLI's{" "}
											<code className="bg-muted px-1 rounded">
												--force
											</code>{" "}
											flag — use when repointing before files are
											pushed.
										</span>
									</span>
								</label>
							</CollapsibleContent>
						</Collapsible>

						<DialogFooter>
							<Button
								variant="outline"
								onClick={handleClose}
								disabled={phase === "replacing"}
							>
								Cancel
							</Button>
							<Button
								onClick={handleReplace}
								disabled={!canReplace || phase === "replacing"}
							>
								{phase === "replacing" ? (
									<>
										<Loader2 className="mr-2 h-4 w-4 animate-spin" />
										Replacing…
									</>
								) : (
									<>
										<ArrowRightLeft className="mr-2 h-4 w-4" />
										Replace
									</>
								)}
							</Button>
						</DialogFooter>
					</div>
				)}
		</DialogContent>
	);
}

/**
 * Thin outer component. Mounts the body only when `open` is true so state
 * resets every time the dialog is opened — avoids having to do setState
 * inside a useEffect.
 */
export function AppReplacePathDialog({
	app,
	open,
	onClose,
	onSuccess,
}: AppReplacePathDialogProps) {
	return (
		<Dialog open={open} onOpenChange={(isOpen) => !isOpen && onClose()}>
			{open && (
				<AppReplacePathDialogBody
					app={app}
					onClose={onClose}
					onSuccess={onSuccess}
				/>
			)}
		</Dialog>
	);
}

export default AppReplacePathDialog;

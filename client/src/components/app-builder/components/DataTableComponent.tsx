/**
 * DataTable Component for App Builder
 *
 * Displays tabular data from a data source with support for
 * pagination, search, sorting, row actions, and row selection.
 */

import { useState, useMemo, useCallback, useEffect } from "react";
import { cn } from "@/lib/utils";
import {
	Table,
	TableBody,
	TableCell,
	TableHead,
	TableHeader,
	TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { Skeleton } from "@/components/ui/skeleton";
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
	ChevronLeft,
	ChevronRight,
	ChevronsLeft,
	ChevronsRight,
	Search,
	ArrowUpDown,
	ArrowUp,
	ArrowDown,
	RefreshCw,
} from "lucide-react";
import {
	Tooltip,
	TooltipContent,
	TooltipProvider,
	TooltipTrigger,
} from "@/components/ui/tooltip";
import { getIcon } from "@/lib/icons";
import type {
	DataTableComponentProps,
	TableColumn,
	TableAction,
} from "@/lib/app-builder-types";
import type { RegisteredComponentProps } from "../ComponentRegistry";
import {
	evaluateExpression,
	evaluateVisibility,
} from "@/lib/expression-parser";
import { useAppBuilderStore, useTableCache } from "@/stores/app-builder.store";

interface SortState {
	column: string | null;
	direction: "asc" | "desc";
}

function getNestedValue(obj: Record<string, unknown>, path: string): unknown {
	return path.split(".").reduce((current, key) => {
		if (current && typeof current === "object") {
			return (current as Record<string, unknown>)[key];
		}
		return undefined;
	}, obj as unknown);
}

function formatCellValue(value: unknown, column: TableColumn): React.ReactNode {
	if (value === null || value === undefined) {
		return "-";
	}

	switch (column.type) {
		case "number":
			return typeof value === "number"
				? value.toLocaleString()
				: String(value);

		case "date":
			if (value instanceof Date) {
				return value.toLocaleDateString();
			}
			if (typeof value === "string" || typeof value === "number") {
				return new Date(value).toLocaleDateString();
			}
			return String(value);

		case "badge": {
			const stringValue = String(value);
			const variant = column.badgeColors?.[stringValue] as
				| "default"
				| "secondary"
				| "destructive"
				| "outline"
				| undefined;
			return <Badge variant={variant || "default"}>{stringValue}</Badge>;
		}

		case "text":
		default:
			return String(value);
	}
}

export function DataTableComponent({
	component,
	context,
}: RegisteredComponentProps) {
	const { props } = component as DataTableComponentProps;

	// Table cache from store
	const cachedEntry = useTableCache(props.cacheKey);
	const setTableCache = useAppBuilderStore((state) => state.setTableCache);
	const clearTableCache = useAppBuilderStore(
		(state) => state.clearTableCache,
	);
	const [isRefreshing, setIsRefreshing] = useState(false);

	// Get data from context - memoize to prevent dependency changes
	// Support dot-notation paths like "tickets.tickets" for nested data access
	const rawData = useMemo(() => {
		if (props.dataSource.startsWith("{{")) {
			return evaluateExpression(props.dataSource, context);
		}
		// Use getNestedValue for dot-notation paths (e.g., "tickets.tickets")
		if (context.data && props.dataSource.includes(".")) {
			return getNestedValue(
				context.data as Record<string, unknown>,
				props.dataSource,
			);
		}
		// Simple key lookup for single-level paths
		return context.data?.[props.dataSource];
	}, [props.dataSource, context]);

	// Use cached data if available and no fresh data yet
	const effectiveData = useMemo(() => {
		// If we have fresh data from context, use it
		if (Array.isArray(rawData) && rawData.length > 0) {
			return rawData;
		}
		// If we have cached data and context data is empty/undefined, use cache
		if (
			cachedEntry?.data &&
			(!rawData || (Array.isArray(rawData) && rawData.length === 0))
		) {
			return cachedEntry.data;
		}
		// Otherwise use raw data (may be empty)
		return Array.isArray(rawData) ? rawData : [];
	}, [rawData, cachedEntry]);

	const data = effectiveData;

	// Update cache when fresh data arrives
	useEffect(() => {
		if (props.cacheKey && Array.isArray(rawData) && rawData.length > 0) {
			setTableCache(props.cacheKey, rawData, props.dataSource);
		}
	}, [props.cacheKey, rawData, props.dataSource, setTableCache]);

	// Show skeleton if data is undefined AND we're loading
	const isLoading =
		(rawData === undefined && context.isDataLoading) || isRefreshing;

	// Refresh handler
	const handleRefresh = useCallback(() => {
		if (props.cacheKey) {
			clearTableCache(props.cacheKey);
		}
		setIsRefreshing(true);
		// Trigger data source refresh
		context.refreshTable?.(props.dataSource);
		// Reset refreshing state after a delay (data will re-fetch)
		setTimeout(() => setIsRefreshing(false), 500);
	}, [props.cacheKey, props.dataSource, context, clearTableCache]);

	// State
	const [searchQuery, setSearchQuery] = useState("");
	const [currentPage, setCurrentPage] = useState(1);
	const [selectedRows, setSelectedRows] = useState<Set<number>>(new Set());
	const [sortState, setSortState] = useState<SortState>({
		column: null,
		direction: "asc",
	});

	// Confirmation dialog state
	const [confirmDialog, setConfirmDialog] = useState<{
		isOpen: boolean;
		action: TableAction | null;
		row: Record<string, unknown>;
		title: string;
		message: string;
		confirmLabel: string;
		cancelLabel: string;
	}>({
		isOpen: false,
		action: null,
		row: {},
		title: "",
		message: "",
		confirmLabel: "Confirm",
		cancelLabel: "Cancel",
	});

	const pageSize = props.pageSize ?? 10;

	// Filter data by search
	const filteredData = useMemo(() => {
		if (!props.searchable || !searchQuery.trim()) {
			return data;
		}

		const query = searchQuery.toLowerCase();
		return data.filter((row: Record<string, unknown>) =>
			props.columns.some((col) => {
				const value = getNestedValue(row, col.key);
				return String(value ?? "")
					.toLowerCase()
					.includes(query);
			}),
		);
	}, [data, searchQuery, props.searchable, props.columns]);

	// Sort data
	const sortedData = useMemo(() => {
		if (!sortState.column) {
			return filteredData;
		}

		const column = props.columns.find((c) => c.key === sortState.column);
		if (!column?.sortable) {
			return filteredData;
		}

		return [...filteredData].sort(
			(a: Record<string, unknown>, b: Record<string, unknown>) => {
				const aVal = getNestedValue(a, sortState.column!);
				const bVal = getNestedValue(b, sortState.column!);

				let comparison = 0;
				if (aVal === null || aVal === undefined) comparison = 1;
				else if (bVal === null || bVal === undefined) comparison = -1;
				else if (typeof aVal === "number" && typeof bVal === "number") {
					comparison = aVal - bVal;
				} else {
					comparison = String(aVal).localeCompare(String(bVal));
				}

				return sortState.direction === "asc" ? comparison : -comparison;
			},
		);
	}, [filteredData, sortState, props.columns]);

	// Paginate data
	const paginatedData = useMemo(() => {
		if (!props.paginated) {
			return sortedData;
		}

		const start = (currentPage - 1) * pageSize;
		return sortedData.slice(start, start + pageSize);
	}, [sortedData, currentPage, pageSize, props.paginated]);

	const totalPages = Math.ceil(sortedData.length / pageSize);

	// Handlers
	const handleSort = (columnKey: string) => {
		const column = props.columns.find((c) => c.key === columnKey);
		if (!column?.sortable) return;

		setSortState((prev) => ({
			column: columnKey,
			direction:
				prev.column === columnKey && prev.direction === "asc"
					? "desc"
					: "asc",
		}));
	};

	const handleRowClick = (row: Record<string, unknown>, index: number) => {
		if (!props.onRowClick) return;

		if (
			props.onRowClick.type === "navigate" &&
			props.onRowClick.navigateTo
		) {
			const path = String(
				evaluateExpression(props.onRowClick.navigateTo, {
					...context,
					row,
				}) ?? "",
			);
			context.navigate?.(path);
		} else if (props.onRowClick.type === "select" && props.selectable) {
			setSelectedRows((prev) => {
				const next = new Set(prev);
				if (next.has(index)) {
					next.delete(index);
				} else {
					next.add(index);
				}
				return next;
			});
		} else if (
			props.onRowClick.type === "set-variable" &&
			props.onRowClick.variableName
		) {
			// TODO: Integrate with AppContext for variable state management
			// This requires adding setVariable to ExpressionContext
		}
	};

	const handleSelectAll = (checked: boolean) => {
		if (checked) {
			setSelectedRows(new Set(paginatedData.map((_, i) => i)));
		} else {
			setSelectedRows(new Set());
		}
	};

	const handleRowSelect = (index: number, checked: boolean) => {
		setSelectedRows((prev) => {
			const next = new Set(prev);
			if (checked) {
				next.add(index);
			} else {
				next.delete(index);
			}
			return next;
		});
	};

	// Execute the actual action (after confirmation if needed)
	const executeAction = useCallback(
		(action: TableAction, row: Record<string, unknown>) => {
			// Create a scoped context with row data available for expression evaluation
			const rowContext: typeof context = {
				...context,
				row,
			};

			if (
				action.onClick.type === "navigate" &&
				action.onClick.navigateTo
			) {
				const path = String(
					evaluateExpression(action.onClick.navigateTo, rowContext) ??
						"",
				);
				context.navigate?.(path);
			} else if (
				action.onClick.type === "workflow" &&
				action.onClick.workflowId
			) {
				// Evaluate actionParams expressions with row context
				const actionParams = action.onClick.actionParams ?? {};
				const evaluatedParams: Record<string, unknown> = { row };

				// Evaluate each param value if it contains expressions
				for (const [key, value] of Object.entries(actionParams)) {
					if (typeof value === "string" && value.includes("{{")) {
						evaluatedParams[key] = evaluateExpression(
							value,
							rowContext,
						);
					} else {
						evaluatedParams[key] = value;
					}
				}

				context.triggerWorkflow?.(
					action.onClick.workflowId,
					evaluatedParams,
				);
			} else if (
				action.onClick.type === "set-variable" &&
				action.onClick.variableName
			) {
				// Evaluate variable value with row context
				const value = action.onClick.variableValue
					? evaluateExpression(
							action.onClick.variableValue,
							rowContext,
						)
					: row;
				context.setVariable?.(action.onClick.variableName, value);
			}
		},
		[context],
	);

	const handleAction = useCallback(
		(action: TableAction, row: Record<string, unknown>) => {
			// Check if action requires confirmation
			if (action.confirm) {
				// Create row context for evaluating expressions in confirmation text
				const rowContext: typeof context = {
					...context,
					row,
				};

				// Evaluate any expressions in title/message
				const title = action.confirm.title.includes("{{")
					? String(
							evaluateExpression(
								action.confirm.title,
								rowContext,
							) ?? action.confirm.title,
						)
					: action.confirm.title;
				const message = action.confirm.message.includes("{{")
					? String(
							evaluateExpression(
								action.confirm.message,
								rowContext,
							) ?? action.confirm.message,
						)
					: action.confirm.message;

				setConfirmDialog({
					isOpen: true,
					action,
					row,
					title,
					message,
					confirmLabel: action.confirm.confirmLabel || "Confirm",
					cancelLabel: action.confirm.cancelLabel || "Cancel",
				});
			} else {
				// No confirmation needed, execute immediately
				executeAction(action, row);
			}
		},
		[context, executeAction],
	);

	// Handle confirmation dialog confirm
	const handleConfirm = useCallback(() => {
		if (confirmDialog.action) {
			executeAction(confirmDialog.action, confirmDialog.row);
		}
		setConfirmDialog((prev) => ({ ...prev, isOpen: false }));
	}, [confirmDialog.action, confirmDialog.row, executeAction]);

	// Handle confirmation dialog cancel
	const handleCancel = useCallback(() => {
		setConfirmDialog((prev) => ({ ...prev, isOpen: false }));
	}, []);

	const getSortIcon = (columnKey: string) => {
		if (sortState.column !== columnKey) {
			return <ArrowUpDown className="ml-2 h-4 w-4 opacity-50" />;
		}
		return sortState.direction === "asc" ? (
			<ArrowUp className="ml-2 h-4 w-4" />
		) : (
			<ArrowDown className="ml-2 h-4 w-4" />
		);
	};

	// Don't show empty message when loading - skeleton will be shown instead
	if (data.length === 0 && !props.emptyMessage && !isLoading) {
		return (
			<div
				className={cn(
					"text-center py-8 text-muted-foreground",
					props.className,
				)}
			>
				No data available
			</div>
		);
	}

	return (
		<TooltipProvider>
			<div className={cn("space-y-4", props.className)}>
				{/* Header with search, refresh, and actions */}
				{(props.searchable ||
					props.headerActions?.length ||
					props.cacheKey) && (
					<div className="flex items-center justify-between gap-4">
						{props.searchable && (
							<div className="relative flex-1 max-w-sm">
								<Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
								<Input
									placeholder="Search..."
									value={searchQuery}
									onChange={(e) => {
										setSearchQuery(e.target.value);
										setCurrentPage(1);
									}}
									className="pl-10"
								/>
							</div>
						)}
						<div className="flex items-center gap-2">
							{/* Refresh Button */}
							{props.cacheKey && (
								<Tooltip>
									<TooltipTrigger asChild>
										<Button
											variant="outline"
											size="icon"
											onClick={handleRefresh}
											disabled={isLoading}
											className="h-8 w-8"
										>
											<RefreshCw
												className={cn(
													"h-4 w-4",
													isLoading && "animate-spin",
												)}
											/>
										</Button>
									</TooltipTrigger>
									<TooltipContent>
										<p>Refresh data</p>
									</TooltipContent>
								</Tooltip>
							)}
							{/* Header Actions */}
							{props.headerActions?.map((action, idx) => {
								const IconComponent = action.icon
									? getIcon(action.icon)
									: null;
								const isIconOnly =
									IconComponent && !action.label.trim();

								const buttonElement = (
									<Button
										key={idx}
										variant={action.variant || "default"}
										size={isIconOnly ? "icon" : "sm"}
										onClick={() => handleAction(action, {})}
										className={
											isIconOnly ? "h-8 w-8" : undefined
										}
									>
										{IconComponent && (
											<IconComponent
												className={cn(
													"h-4 w-4",
													!isIconOnly && "mr-1.5",
												)}
											/>
										)}
										{!isIconOnly && action.label}
									</Button>
								);

								if (isIconOnly) {
									return (
										<Tooltip key={idx}>
											<TooltipTrigger asChild>
												{buttonElement}
											</TooltipTrigger>
											<TooltipContent>
												<p>{action.label}</p>
											</TooltipContent>
										</Tooltip>
									);
								}

								return buttonElement;
							})}
						</div>
					</div>
				)}

				{/* Table */}
				<div className="rounded-md border">
					<Table>
						<TableHeader>
							<TableRow>
								{props.selectable && (
									<TableHead className="w-12">
										<Checkbox
											checked={
												paginatedData.length > 0 &&
												selectedRows.size ===
													paginatedData.length
											}
											onCheckedChange={handleSelectAll}
										/>
									</TableHead>
								)}
								{props.columns.map((column) => (
									<TableHead
										key={column.key}
										className={cn(
											column.sortable &&
												"cursor-pointer select-none",
										)}
										style={{
											width:
												column.width !== "auto"
													? column.width
													: undefined,
										}}
										onClick={() =>
											column.sortable &&
											handleSort(column.key)
										}
									>
										<div className="flex items-center">
											{column.header}
											{column.sortable &&
												getSortIcon(column.key)}
										</div>
									</TableHead>
								))}
								{props.rowActions?.length && (
									<TableHead className="w-24 text-right">
										Actions
									</TableHead>
								)}
							</TableRow>
						</TableHeader>
						<TableBody>
							{isLoading ? (
								// Show skeleton rows when loading
								Array.from({ length: 5 }).map((_, rowIndex) => (
									<TableRow key={`skeleton-${rowIndex}`}>
										{props.selectable && (
											<TableCell>
												<Skeleton className="h-4 w-4" />
											</TableCell>
										)}
										{props.columns.map((column) => (
											<TableCell key={column.key}>
												<Skeleton className="h-4 w-full" />
											</TableCell>
										))}
										{props.rowActions?.length && (
											<TableCell className="text-right">
												<Skeleton className="h-8 w-16 ml-auto" />
											</TableCell>
										)}
									</TableRow>
								))
							) : paginatedData.length === 0 ? (
								<TableRow>
									<TableCell
										colSpan={
											props.columns.length +
											(props.selectable ? 1 : 0) +
											(props.rowActions?.length ? 1 : 0)
										}
										className="text-center py-8 text-muted-foreground"
									>
										{props.emptyMessage ||
											"No results found"}
									</TableCell>
								</TableRow>
							) : (
								paginatedData.map(
									(
										row: Record<string, unknown>,
										rowIndex,
									) => (
										<TableRow
											key={
												(row.id as string) ??
												(row._id as string) ??
												`row-${rowIndex}`
											}
											className={cn(
												props.onRowClick &&
													"cursor-pointer",
												selectedRows.has(rowIndex) &&
													"bg-muted/50",
											)}
											onClick={() =>
												handleRowClick(row, rowIndex)
											}
										>
											{props.selectable && (
												<TableCell
													onClick={(e) =>
														e.stopPropagation()
													}
												>
													<Checkbox
														checked={selectedRows.has(
															rowIndex,
														)}
														onCheckedChange={(
															checked,
														) =>
															handleRowSelect(
																rowIndex,
																!!checked,
															)
														}
													/>
												</TableCell>
											)}
											{props.columns.map((column) => (
												<TableCell key={column.key}>
													{formatCellValue(
														getNestedValue(
															row,
															column.key,
														),
														column,
													)}
												</TableCell>
											))}
											{props.rowActions?.length && (
												<TableCell
													className="text-right"
													onClick={(e) =>
														e.stopPropagation()
													}
												>
													<div className="flex items-center justify-end gap-1">
														{props.rowActions.map(
															(action, idx) => {
																// Create row-scoped context for expression evaluation
																const actionRowContext =
																	{
																		...context,
																		row,
																	};
																// Check visibility expression
																if (
																	action.visible &&
																	!evaluateVisibility(
																		action.visible,
																		actionRowContext,
																	)
																) {
																	return null;
																}
																// Check disabled expression
																const isDisabled =
																	action.disabled
																		? Boolean(
																				evaluateExpression(
																					action.disabled,
																					actionRowContext,
																				),
																			)
																		: false;
																// Evaluate label with row context
																const label =
																	action.label.includes(
																		"{{",
																	)
																		? String(
																				evaluateExpression(
																					action.label,
																					actionRowContext,
																				) ??
																					action.label,
																			)
																		: action.label;

																// Get icon component if specified
																const IconComponent =
																	action.icon
																		? getIcon(
																				action.icon,
																			)
																		: null;

																// Icon-only when there's an icon but no label text
																const isIconOnly =
																	IconComponent &&
																	!label.trim();

																// For icon-only buttons, default to outline variant to match platform style
																const buttonVariant =
																	action.variant ||
																	(isIconOnly
																		? "outline"
																		: "ghost");

																const buttonElement =
																	(
																		<Button
																			key={
																				idx
																			}
																			variant={
																				buttonVariant
																			}
																			size={
																				isIconOnly
																					? "icon"
																					: "sm"
																			}
																			disabled={
																				isDisabled
																			}
																			onClick={() =>
																				handleAction(
																					action,
																					row,
																				)
																			}
																			className={
																				isIconOnly
																					? "h-8 w-8"
																					: undefined
																			}
																		>
																			{IconComponent && (
																				<IconComponent
																					className={cn(
																						"h-4 w-4",
																						!isIconOnly &&
																							"mr-1.5",
																					)}
																				/>
																			)}
																			{!isIconOnly &&
																				label}
																		</Button>
																	);

																// Wrap icon-only buttons in tooltip for accessibility
																if (
																	isIconOnly
																) {
																	return (
																		<Tooltip
																			key={
																				idx
																			}
																		>
																			<TooltipTrigger
																				asChild
																			>
																				{
																					buttonElement
																				}
																			</TooltipTrigger>
																			<TooltipContent>
																				<p>
																					{
																						action.label
																					}
																				</p>
																			</TooltipContent>
																		</Tooltip>
																	);
																}

																return buttonElement;
															},
														)}
													</div>
												</TableCell>
											)}
										</TableRow>
									),
								)
							)}
						</TableBody>
					</Table>
				</div>

				{/* Pagination */}
				{props.paginated && totalPages > 1 && (
					<div className="flex items-center justify-between">
						<p className="text-sm text-muted-foreground">
							Showing {(currentPage - 1) * pageSize + 1} to{" "}
							{Math.min(
								currentPage * pageSize,
								sortedData.length,
							)}{" "}
							of {sortedData.length} results
						</p>
						<div className="flex items-center gap-1">
							<Button
								variant="outline"
								size="sm"
								onClick={() => setCurrentPage(1)}
								disabled={currentPage === 1}
							>
								<ChevronsLeft className="h-4 w-4" />
							</Button>
							<Button
								variant="outline"
								size="sm"
								onClick={() =>
									setCurrentPage((p) => Math.max(1, p - 1))
								}
								disabled={currentPage === 1}
							>
								<ChevronLeft className="h-4 w-4" />
							</Button>
							<span className="px-3 text-sm">
								Page {currentPage} of {totalPages}
							</span>
							<Button
								variant="outline"
								size="sm"
								onClick={() =>
									setCurrentPage((p) =>
										Math.min(totalPages, p + 1),
									)
								}
								disabled={currentPage === totalPages}
							>
								<ChevronRight className="h-4 w-4" />
							</Button>
							<Button
								variant="outline"
								size="sm"
								onClick={() => setCurrentPage(totalPages)}
								disabled={currentPage === totalPages}
							>
								<ChevronsRight className="h-4 w-4" />
							</Button>
						</div>
					</div>
				)}

				{/* Confirmation Dialog */}
				<AlertDialog
					open={confirmDialog.isOpen}
					onOpenChange={(open) => !open && handleCancel()}
				>
					<AlertDialogContent>
						<AlertDialogHeader>
							<AlertDialogTitle>
								{confirmDialog.title}
							</AlertDialogTitle>
							<AlertDialogDescription>
								{confirmDialog.message}
							</AlertDialogDescription>
						</AlertDialogHeader>
						<AlertDialogFooter>
							<AlertDialogCancel onClick={handleCancel}>
								{confirmDialog.cancelLabel}
							</AlertDialogCancel>
							<AlertDialogAction onClick={handleConfirm}>
								{confirmDialog.confirmLabel}
							</AlertDialogAction>
						</AlertDialogFooter>
					</AlertDialogContent>
				</AlertDialog>
			</div>
		</TooltipProvider>
	);
}

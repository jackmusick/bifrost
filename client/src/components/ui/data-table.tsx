import * as React from "react";

import { cn } from "@/lib/utils";

/**
 * DataTable - A standardized table component with sticky headers and consistent styling.
 *
 * Features:
 * - Sticky header with backdrop blur
 * - Consistent hover states
 * - Click-to-navigate row support
 * - Overflow handling
 *
 * Usage:
 * ```tsx
 * <DataTable>
 *   <DataTableHeader>
 *     <DataTableRow>
 *       <DataTableHead>Column</DataTableHead>
 *     </DataTableRow>
 *   </DataTableHeader>
 *   <DataTableBody>
 *     <DataTableRow onClick={() => navigate('/path')} clickable>
 *       <DataTableCell>Value</DataTableCell>
 *     </DataTableRow>
 *   </DataTableBody>
 * </DataTable>
 * ```
 */

interface DataTableProps extends React.HTMLAttributes<HTMLDivElement> {
	/** Optional fixed height for the table container */
	fixedHeight?: boolean;
}

const DataTable = React.forwardRef<HTMLDivElement, DataTableProps>(
	({ className, fixedHeight, children, ...props }, ref) => (
		<div
			ref={ref}
			className={cn(
				"border rounded-lg overflow-hidden bg-card",
				// Make DataTable flex-aware: fill available space and enable shrinking for scroll
				"flex flex-col flex-1 min-h-0",
				fixedHeight && "h-full",
				className,
			)}
			{...props}
		>
			<div
				className={cn(
					"overflow-auto flex-1 min-h-0",
					fixedHeight && "h-full",
				)}
			>
				<table className="relative w-full caption-bottom text-sm">
					{children}
				</table>
			</div>
		</div>
	),
);
DataTable.displayName = "DataTable";

const DataTableHeader = React.forwardRef<
	HTMLTableSectionElement,
	React.HTMLAttributes<HTMLTableSectionElement>
>(({ className, ...props }, ref) => (
	<thead
		ref={ref}
		className={cn(
			"sticky top-0 bg-background/80 backdrop-blur-sm z-10 [&_tr]:border-b",
			className,
		)}
		{...props}
	/>
));
DataTableHeader.displayName = "DataTableHeader";

const DataTableBody = React.forwardRef<
	HTMLTableSectionElement,
	React.HTMLAttributes<HTMLTableSectionElement>
>(({ className, ...props }, ref) => (
	<tbody
		ref={ref}
		className={cn("[&_tr:last-child]:border-0", className)}
		{...props}
	/>
));
DataTableBody.displayName = "DataTableBody";

const DataTableFooter = React.forwardRef<
	HTMLTableSectionElement,
	React.HTMLAttributes<HTMLTableSectionElement>
>(({ className, ...props }, ref) => (
	<tfoot
		ref={ref}
		className={cn(
			"sticky bottom-0 border-t bg-background/80 backdrop-blur-sm z-10 font-medium [&>tr]:last:border-b-0",
			className,
		)}
		{...props}
	/>
));
DataTableFooter.displayName = "DataTableFooter";

interface DataTableRowProps extends React.HTMLAttributes<HTMLTableRowElement> {
	/** Makes the row appear clickable with cursor and hover state */
	clickable?: boolean;
}

const DataTableRow = React.forwardRef<HTMLTableRowElement, DataTableRowProps>(
	({ className, clickable, ...props }, ref) => (
		<tr
			ref={ref}
			className={cn(
				"border-b transition-colors hover:bg-muted/50 data-[state=selected]:bg-muted",
				clickable && "cursor-pointer",
				className,
			)}
			{...props}
		/>
	),
);
DataTableRow.displayName = "DataTableRow";

const DataTableHead = React.forwardRef<
	HTMLTableCellElement,
	React.ThHTMLAttributes<HTMLTableCellElement>
>(({ className, ...props }, ref) => (
	<th
		ref={ref}
		className={cn(
			"h-12 px-4 text-left align-middle font-medium text-muted-foreground [&:has([role=checkbox])]:pr-0",
			className,
		)}
		{...props}
	/>
));
DataTableHead.displayName = "DataTableHead";

const DataTableCell = React.forwardRef<
	HTMLTableCellElement,
	React.TdHTMLAttributes<HTMLTableCellElement>
>(({ className, ...props }, ref) => (
	<td
		ref={ref}
		className={cn(
			"p-4 align-middle [&:has([role=checkbox])]:pr-0",
			className,
		)}
		{...props}
	/>
));
DataTableCell.displayName = "DataTableCell";

const DataTableCaption = React.forwardRef<
	HTMLTableCaptionElement,
	React.HTMLAttributes<HTMLTableCaptionElement>
>(({ className, ...props }, ref) => (
	<caption
		ref={ref}
		className={cn("mt-4 text-sm text-muted-foreground", className)}
		{...props}
	/>
));
DataTableCaption.displayName = "DataTableCaption";

export {
	DataTable,
	DataTableHeader,
	DataTableBody,
	DataTableFooter,
	DataTableHead,
	DataTableRow,
	DataTableCell,
	DataTableCaption,
};

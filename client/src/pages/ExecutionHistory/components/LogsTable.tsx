import {
    DataTable,
    DataTableBody,
    DataTableCell,
    DataTableFooter,
    DataTableHead,
    DataTableHeader,
    DataTableRow,
} from "@/components/ui/data-table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ChevronLeft, ChevronRight } from "lucide-react";
import type { components } from "@/lib/v1";
import { formatDate } from "@/lib/utils";

type LogListEntry = components["schemas"]["LogListEntry"];

interface LogsTableProps {
    logs: LogListEntry[];
    isLoading: boolean;
    continuationToken?: string | null;
    onNextPage: () => void;
    onPrevPage: () => void;
    canGoBack: boolean;
    onLogClick: (log: LogListEntry) => void;
}

function getLevelBadgeVariant(
    level: string,
): "default" | "secondary" | "destructive" | "outline" | "warning" {
    switch (level.toUpperCase()) {
        case "ERROR":
        case "CRITICAL":
            return "destructive";
        case "WARNING":
            return "warning";
        case "DEBUG":
            return "outline";
        default:
            return "default";
    }
}

export function LogsTable({
    logs,
    isLoading,
    continuationToken,
    onNextPage,
    onPrevPage,
    canGoBack,
    onLogClick,
}: LogsTableProps) {
    return (
        <DataTable>
            <DataTableHeader>
                <DataTableRow>
                    <DataTableHead className="w-[150px]">
                        Organization
                    </DataTableHead>
                    <DataTableHead className="w-[180px]">
                        Workflow
                    </DataTableHead>
                    <DataTableHead className="w-[100px]">Level</DataTableHead>
                    <DataTableHead>Message</DataTableHead>
                    <DataTableHead className="w-[180px]">
                        Timestamp
                    </DataTableHead>
                </DataTableRow>
            </DataTableHeader>
            <DataTableBody>
                {isLoading ? (
                    <DataTableRow>
                        <DataTableCell colSpan={5} className="text-center py-8">
                            Loading logs...
                        </DataTableCell>
                    </DataTableRow>
                ) : logs.length === 0 ? (
                    <DataTableRow>
                        <DataTableCell
                            colSpan={5}
                            className="text-center py-8 text-muted-foreground"
                        >
                            No logs found matching your filters.
                        </DataTableCell>
                    </DataTableRow>
                ) : (
                    logs.map((log) => (
                        <DataTableRow
                            key={log.id}
                            clickable
                            onClick={() => onLogClick(log)}
                            className="cursor-pointer"
                        >
                            <DataTableCell className="font-medium">
                                {log.organization_name || "\u2014"}
                            </DataTableCell>
                            <DataTableCell>{log.workflow_name}</DataTableCell>
                            <DataTableCell>
                                <Badge
                                    variant={getLevelBadgeVariant(log.level)}
                                    className="font-mono text-xs uppercase"
                                >
                                    {log.level}
                                </Badge>
                            </DataTableCell>
                            <DataTableCell className="max-w-md truncate">
                                {log.message}
                            </DataTableCell>
                            <DataTableCell className="text-muted-foreground text-sm">
                                {formatDate(log.timestamp)}
                            </DataTableCell>
                        </DataTableRow>
                    ))
                )}
            </DataTableBody>
            <DataTableFooter>
                <DataTableRow>
                    <DataTableCell colSpan={5}>
                        <div className="flex items-center justify-between">
                            <span className="text-sm text-muted-foreground">
                                {logs.length} logs shown
                            </span>
                            <div className="flex gap-2">
                                <Button
                                    variant="outline"
                                    size="sm"
                                    onClick={onPrevPage}
                                    disabled={!canGoBack}
                                >
                                    <ChevronLeft className="h-4 w-4 mr-1" />
                                    Previous
                                </Button>
                                <Button
                                    variant="outline"
                                    size="sm"
                                    onClick={onNextPage}
                                    disabled={!continuationToken}
                                >
                                    Next
                                    <ChevronRight className="h-4 w-4 ml-1" />
                                </Button>
                            </div>
                        </div>
                    </DataTableCell>
                </DataTableRow>
            </DataTableFooter>
        </DataTable>
    );
}

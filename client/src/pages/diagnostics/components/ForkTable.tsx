// client/src/pages/diagnostics/components/ForkTable.tsx
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Button } from "@/components/ui/button";
import {
    AlertDialog,
    AlertDialogAction,
    AlertDialogCancel,
    AlertDialogContent,
    AlertDialogDescription,
    AlertDialogFooter,
    AlertDialogHeader,
    AlertDialogTitle,
    AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { RotateCw } from "lucide-react";
import { toast } from "sonner";
import type { ProcessInfo } from "@/services/workers";
import { useRecycleAllProcesses } from "@/services/workers";
import type { ExecutionRowData } from "./ExecutionRow";

function formatUptime(seconds: number): string {
    if (seconds < 60) return `${Math.floor(seconds)}s`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
    if (seconds < 86400) {
        const h = Math.floor(seconds / 3600);
        const m = Math.floor((seconds % 3600) / 60);
        return m > 0 ? `${h}h ${m}m` : `${h}h`;
    }
    const d = Math.floor(seconds / 86400);
    const h = Math.floor((seconds % 86400) / 3600);
    return h > 0 ? `${d}d ${h}h` : `${d}d`;
}

const stateVariant: Record<string, "secondary" | "default" | "destructive"> = {
    idle: "secondary",
    busy: "default",
    killed: "destructive",
};

interface ForkTableProps {
    workerId: string;
    processes: ProcessInfo[];
    /** Map of process_id -> execution info for busy processes */
    executions?: Map<string, ExecutionRowData>;
    /** Max memory for this container in bytes (for progress bar scale) */
    containerMemoryMax?: number;
}

export function ForkTable({
    workerId,
    processes,
    executions,
    containerMemoryMax,
}: ForkTableProps) {
    const recycleAll = useRecycleAllProcesses();

    const handleRecycleAll = () => {
        recycleAll.mutate(
            { workerId, reason: "manual_recycle" },
            {
                onSuccess: () => toast.success("Recycle request sent"),
                onError: (err) => toast.error(`Recycle failed: ${err.message}`),
            }
        );
    };

    // Max memory for progress bars — use container cgroup or fallback to max process memory
    const maxMem =
        containerMemoryMax && containerMemoryMax > 0
            ? containerMemoryMax / (1024 * 1024) // Convert bytes to MB
            : Math.max(...processes.map((p) => p.memory_mb), 1);

    return (
        <div>
            <Table>
                <TableHeader>
                    <TableRow className="text-xs">
                        <TableHead className="w-[80px]">PID</TableHead>
                        <TableHead className="w-[70px]">State</TableHead>
                        <TableHead className="w-[140px]">Memory</TableHead>
                        <TableHead className="w-[70px]">Jobs</TableHead>
                        <TableHead>Execution</TableHead>
                        <TableHead className="w-[80px]">Uptime</TableHead>
                    </TableRow>
                </TableHeader>
                <TableBody>
                    {processes.map((proc) => {
                        const execution = executions?.get(proc.process_id);
                        const memPct = maxMem > 0 ? (proc.memory_mb / maxMem) * 100 : 0;

                        return (
                            <TableRow
                                key={proc.process_id}
                                className={
                                    proc.state === "busy"
                                        ? "bg-yellow-500/5"
                                        : undefined
                                }
                            >
                                <TableCell className="font-mono text-xs">
                                    {proc.pid}
                                </TableCell>
                                <TableCell>
                                    <Badge
                                        variant={stateVariant[proc.state] ?? "secondary"}
                                        className="text-[10px] px-1.5 py-0"
                                    >
                                        {proc.state}
                                    </Badge>
                                </TableCell>
                                <TableCell>
                                    <div className="flex items-center gap-2">
                                        <Progress
                                            value={memPct}
                                            className="h-1 w-10"
                                        />
                                        <span className="text-xs text-muted-foreground">
                                            {proc.memory_mb.toFixed(0)} MB
                                        </span>
                                    </div>
                                </TableCell>
                                <TableCell className="text-xs">
                                    {proc.executions_completed}
                                </TableCell>
                                <TableCell className="text-xs">
                                    {execution ? (
                                        <span>
                                            <span className="text-foreground">
                                                {execution.workflow_name}
                                            </span>
                                            <span className="text-muted-foreground ml-2">
                                                {formatUptime(execution.elapsed_seconds)}
                                            </span>
                                        </span>
                                    ) : (
                                        <span className="text-muted-foreground">&mdash;</span>
                                    )}
                                </TableCell>
                                <TableCell className="text-xs text-muted-foreground">
                                    {formatUptime(proc.uptime_seconds)}
                                </TableCell>
                            </TableRow>
                        );
                    })}
                </TableBody>
            </Table>
            <div className="flex justify-end mt-2 px-2">
                <AlertDialog>
                    <AlertDialogTrigger asChild>
                        <Button
                            variant="ghost"
                            size="sm"
                            className="h-7 text-xs text-destructive hover:text-destructive"
                        >
                            <RotateCw className="h-3 w-3 mr-1" />
                            Recycle All
                        </Button>
                    </AlertDialogTrigger>
                    <AlertDialogContent>
                        <AlertDialogHeader>
                            <AlertDialogTitle>Recycle all processes?</AlertDialogTitle>
                            <AlertDialogDescription>
                                This will gracefully restart all {processes.length}{" "}
                                fork(s) in {workerId}. Running executions will
                                complete before their process is recycled.
                            </AlertDialogDescription>
                        </AlertDialogHeader>
                        <AlertDialogFooter>
                            <AlertDialogCancel>Cancel</AlertDialogCancel>
                            <AlertDialogAction onClick={handleRecycleAll}>
                                Recycle All
                            </AlertDialogAction>
                        </AlertDialogFooter>
                    </AlertDialogContent>
                </AlertDialog>
            </div>
        </div>
    );
}

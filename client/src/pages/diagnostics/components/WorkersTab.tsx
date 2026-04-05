import { useState, useMemo } from "react";
import { RefreshCw, Loader2, WifiOff, Server } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { usePools, useQueueStatus } from "@/services/workers";
import { getErrorMessage } from "@/lib/api-error";
import { QueueBadge } from "./QueueBadge";
import { MemoryChart } from "./MemoryChart";
import { ContainerTable } from "./ContainerTable";
import { useWorkerWebSocket } from "../hooks/useWorkerWebSocket";

export function WorkersTab() {
    const {
        data: poolsData,
        isLoading: poolsLoading,
        error: poolsError,
        refetch: refetchPools,
    } = usePools();

    const {
        data: queueData,
        isLoading: queueLoading,
        refetch: refetchQueue,
    } = useQueueStatus({ limit: 50 });

    const { pools: wsPools, isConnected } = useWorkerWebSocket();

    const [isRefreshing, setIsRefreshing] = useState(false);

    const handleRefresh = async () => {
        setIsRefreshing(true);
        try {
            await Promise.all([refetchPools(), refetchQueue()]);
        } finally {
            setIsRefreshing(false);
        }
    };

    const restPools = poolsData?.pools || [];
    const pools = wsPools.length > 0 ? wsPools : restPools;
    const queueItems = queueData?.items || [];

    // Stable sorted worker IDs for consistent color assignment
    const workerIds = useMemo(
        () => [...new Set(pools.map((p) => p.worker_id))].sort(),
        [pools]
    );

    // Compute summary stats
    const stats = useMemo(() => {
        let totalForks = 0;
        let totalBusy = 0;
        for (const pool of pools) {
            if ("processes" in pool && Array.isArray(pool.processes)) {
                totalForks += pool.processes.length;
                totalBusy += pool.processes.filter(
                    (p: any) => p.state === "busy"
                ).length;
            } else {
                totalForks += (pool as any).pool_size ?? 0;
                totalBusy += (pool as any).busy_count ?? 0;
            }
        }
        return { containers: pools.length, forks: totalForks, busy: totalBusy };
    }, [pools]);

    return (
        <div className="max-w-[900px] mx-auto space-y-6">
            {/* Connection Status Banner */}
            {!isConnected && (
                <Alert className="border-amber-500/50 text-amber-700 dark:text-amber-400 [&>svg]:text-amber-600">
                    <WifiOff className="h-4 w-4" />
                    <AlertDescription>
                        Connecting to real-time worker updates... Data may not be
                        current.
                    </AlertDescription>
                </Alert>
            )}

            {/* Error State */}
            {poolsError && (
                <Alert variant="destructive">
                    <AlertDescription>
                        Failed to load pools:{" "}
                        {getErrorMessage(poolsError, "Unknown error")}
                    </AlertDescription>
                </Alert>
            )}

            {/* Header */}
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                    <h2 className="text-lg font-semibold">Process Pools</h2>
                    {isConnected && (
                        <span className="flex items-center gap-1 text-xs text-green-600">
                            <span className="w-2 h-2 bg-green-500 rounded-full animate-pulse" />
                            Live
                        </span>
                    )}
                    <QueueBadge items={queueItems} isLoading={queueLoading} />
                </div>
                <div className="flex items-center gap-3">
                    <span className="text-sm text-muted-foreground">
                        {stats.containers} container{stats.containers !== 1 ? "s" : ""}{" "}
                        &middot; {stats.forks} fork{stats.forks !== 1 ? "s" : ""}
                    </span>
                    <Button
                        variant="outline"
                        size="sm"
                        onClick={handleRefresh}
                        disabled={isRefreshing || poolsLoading}
                    >
                        <RefreshCw
                            className={`h-4 w-4 mr-2 ${isRefreshing ? "animate-spin" : ""}`}
                        />
                        Refresh
                    </Button>
                </div>
            </div>

            {/* Memory Chart */}
            <MemoryChart />

            {/* Container Table */}
            {poolsLoading && pools.length === 0 ? (
                <div className="flex items-center justify-center py-12">
                    <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                </div>
            ) : pools.length === 0 ? (
                <Card>
                    <CardContent className="flex flex-col items-center justify-center py-12 text-center">
                        <Server className="h-12 w-12 text-muted-foreground mb-4" />
                        <h3 className="text-lg font-semibold">
                            No containers connected
                        </h3>
                        <p className="mt-2 text-sm text-muted-foreground max-w-md">
                            Worker containers register themselves on startup.
                            If you expect containers to be running, check the
                            worker logs for connection issues.
                        </p>
                    </CardContent>
                </Card>
            ) : (
                <ContainerTable pools={pools} workerIds={workerIds} />
            )}
        </div>
    );
}

/**
 * CLI Sessions List Page
 *
 * Shows all CLI sessions for the current user.
 * Individual session details are now handled by the Workbench page.
 */

import { useState, useEffect, useCallback } from "react";
import { Link } from "react-router-dom";
import {
	Terminal,
	RefreshCw,
	Loader2,
	AlertCircle,
	ExternalLink,
	Trash2,
	Clock,
	Wifi,
	WifiOff,
} from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { webSocketService } from "@/services/websocket";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";
import { getCLISessions, deleteCLISession, type CLISessionResponse } from "@/services/cli";
import {
	Table,
	TableBody,
	TableCell,
	TableHead,
	TableHeader,
	TableRow,
} from "@/components/ui/table";
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

/**
 * Sessions list view
 */
function SessionsList() {
	const [sessions, setSessions] = useState<CLISessionResponse[]>([]);
	const [isLoading, setIsLoading] = useState(true);
	const [error, setError] = useState<string | null>(null);
	const [deletingId, setDeletingId] = useState<string | null>(null);
	const { user } = useAuth();

	const fetchSessions = useCallback(async () => {
		try {
			setIsLoading(true);
			const response = await getCLISessions();
			setSessions(response.sessions);
			setError(null);
		} catch (err) {
			setError(err instanceof Error ? err.message : "Failed to load sessions");
		} finally {
			setIsLoading(false);
		}
	}, []);

	useEffect(() => {
		fetchSessions();
	}, [fetchSessions]);

	// Subscribe to websocket for session updates
	useEffect(() => {
		if (!user?.id) return;

		const channel = `cli-sessions:${user.id}`;
		webSocketService.connect([channel]);

		// Listen for session updates and refresh list
		const handleMessage = (event: MessageEvent) => {
			try {
				const data = JSON.parse(event.data);
				if (data.type === "cli_session_update") {
					fetchSessions();
				}
			} catch {
				// ignore
			}
		};

		// Add listener directly to websocket
		const ws = (webSocketService as unknown as { ws: WebSocket | null }).ws;
		ws?.addEventListener("message", handleMessage);

		return () => {
			ws?.removeEventListener("message", handleMessage);
			webSocketService.unsubscribe(channel);
		};
	}, [user?.id, fetchSessions]);

	const handleDelete = async (sessionId: string) => {
		setDeletingId(sessionId);
		try {
			await deleteCLISession(sessionId);
			toast.success("Session deleted");
			setSessions((prev) => prev.filter((s) => s.id !== sessionId));
		} catch (err) {
			toast.error(err instanceof Error ? err.message : "Failed to delete session");
		} finally {
			setDeletingId(null);
		}
	};

	if (isLoading) {
		return (
			<Card>
				<CardContent className="pt-6 space-y-4">
					<Skeleton className="h-10 w-full" />
					<Skeleton className="h-10 w-full" />
					<Skeleton className="h-10 w-full" />
				</CardContent>
			</Card>
		);
	}

	if (error) {
		return (
			<Alert variant="destructive">
				<AlertCircle className="h-4 w-4" />
				<AlertTitle>Error</AlertTitle>
				<AlertDescription>{error}</AlertDescription>
			</Alert>
		);
	}

	if (sessions.length === 0) {
		return (
			<Card>
				<CardContent className="pt-6">
					<div className="flex flex-col items-center justify-center py-12 text-center">
						<Terminal className="h-16 w-16 text-muted-foreground mb-4" />
						<h3 className="text-lg font-semibold mb-2">No CLI Sessions</h3>
						<p className="text-muted-foreground mb-4 max-w-md">
							Run <code className="bg-muted px-2 py-1 rounded text-sm">bifrost run &lt;file&gt;</code> in
							your terminal to start a workflow execution session.
						</p>
						<pre className="bg-muted p-4 rounded-lg text-sm text-left overflow-x-auto max-w-full">
							<code>
								{`# Example usage
bifrost run my_workflows.py

# With specific workflow
bifrost run my_workflows.py --workflow onboard_user`}
							</code>
						</pre>
					</div>
				</CardContent>
			</Card>
		);
	}

	return (
		<Card>
			<CardHeader className="flex flex-row items-center justify-between">
				<div>
					<CardTitle>CLI Sessions</CardTitle>
					<CardDescription>Active and recent debugging sessions</CardDescription>
				</div>
				<Button variant="outline" size="sm" onClick={fetchSessions}>
					<RefreshCw className="mr-2 h-4 w-4" />
					Refresh
				</Button>
			</CardHeader>
			<CardContent>
				<Table>
					<TableHeader>
						<TableRow>
							<TableHead>File</TableHead>
							<TableHead>Workflows</TableHead>
							<TableHead>Executions</TableHead>
							<TableHead>Status</TableHead>
							<TableHead>Created</TableHead>
							<TableHead className="w-[100px]">Actions</TableHead>
						</TableRow>
					</TableHeader>
					<TableBody>
						{sessions.map((session) => (
							<TableRow key={session.id}>
								<TableCell>
									<Link
										to={`/cli/${session.id}`}
										className="font-mono text-sm hover:underline text-primary"
									>
										{session.file_path.split("/").pop()}
									</Link>
									<p className="text-xs text-muted-foreground truncate max-w-[200px]">
										{session.file_path}
									</p>
								</TableCell>
								<TableCell>
									<div className="flex flex-wrap gap-1">
										{session.workflows.slice(0, 3).map((w) => (
											<Badge key={w.name} variant="secondary" className="text-xs">
												{w.name}
											</Badge>
										))}
										{session.workflows.length > 3 && (
											<Badge variant="outline" className="text-xs">
												+{session.workflows.length - 3}
											</Badge>
										)}
									</div>
								</TableCell>
								<TableCell>
									<Badge variant="outline">{session.executions.length}</Badge>
								</TableCell>
								<TableCell>
									{session.is_connected ? (
										<Badge variant="default" className="bg-green-500">
											<Wifi className="mr-1 h-3 w-3" />
											Connected
										</Badge>
									) : (
										<Badge variant="secondary">
											<WifiOff className="mr-1 h-3 w-3" />
											Disconnected
										</Badge>
									)}
								</TableCell>
								<TableCell className="text-sm text-muted-foreground">
									<div className="flex items-center gap-1">
										<Clock className="h-3 w-3" />
										{new Date(session.created_at).toLocaleString()}
									</div>
								</TableCell>
								<TableCell>
									<div className="flex items-center gap-2">
										<Button variant="ghost" size="sm" asChild>
											<Link to={`/cli/${session.id}`}>
												<ExternalLink className="h-4 w-4" />
											</Link>
										</Button>
										<AlertDialog>
											<AlertDialogTrigger asChild>
												<Button
													variant="ghost"
													size="sm"
													disabled={deletingId === session.id}
												>
													{deletingId === session.id ? (
														<Loader2 className="h-4 w-4 animate-spin" />
													) : (
														<Trash2 className="h-4 w-4 text-destructive" />
													)}
												</Button>
											</AlertDialogTrigger>
											<AlertDialogContent>
												<AlertDialogHeader>
													<AlertDialogTitle>Delete Session?</AlertDialogTitle>
													<AlertDialogDescription>
														This will permanently delete this CLI session and its history.
														This action cannot be undone.
													</AlertDialogDescription>
												</AlertDialogHeader>
												<AlertDialogFooter>
													<AlertDialogCancel>Cancel</AlertDialogCancel>
													<AlertDialogAction onClick={() => handleDelete(session.id)}>
														Delete
													</AlertDialogAction>
												</AlertDialogFooter>
											</AlertDialogContent>
										</AlertDialog>
									</div>
								</TableCell>
							</TableRow>
						))}
					</TableBody>
				</Table>
			</CardContent>
		</Card>
	);
}

/**
 * CLI page - shows sessions list
 */
export function CLI() {
	return (
		<div className="space-y-6">
			<div>
				<h1 className="scroll-m-20 text-4xl font-extrabold tracking-tight lg:text-5xl">Local Sessions</h1>
				<p className="leading-7 mt-2 text-muted-foreground">
					CLI debugging sessions with web-based parameter input
				</p>
			</div>

			<SessionsList />
		</div>
	);
}

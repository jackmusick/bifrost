/**
 * UserMCPConnections — "My Connections" tab in user settings (mockup §7).
 *
 * Lists all MCP connections the org admin has set up that the user can
 * opt into for personalized access. Connecting opens an OAuth popup at
 * GET /api/me/mcp-connections/{id}/connect; the popup callback posts
 * back via window.opener.postMessage({type: "mcp_oauth_success", ...})
 * and we invalidate the connection list query.
 *
 * Backend gaps (flagged for follow-up — see report):
 *   - No GET /api/me/mcp-credentials endpoint exists yet, so we can't
 *     show per-user connect status (since/expires) authoritatively. We
 *     currently display "Connect" on every row and let the popup flow
 *     drive state. After connect, the toast confirms; the list refreshes
 *     on focus.
 *   - No DELETE /api/me/mcp-connections/{id} endpoint exists for the
 *     "forget my personal credential" flow. The Disconnect button is
 *     rendered disabled with a tooltip explaining "coming soon".
 */

import { useEffect, useMemo } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Loader2, Plug, RefreshCw } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
	DataTable,
	DataTableBody,
	DataTableCell,
	DataTableHead,
	DataTableHeader,
	DataTableRow,
} from "@/components/ui/data-table";
import { Skeleton } from "@/components/ui/skeleton";
import {
	Tooltip,
	TooltipContent,
	TooltipProvider,
	TooltipTrigger,
} from "@/components/ui/tooltip";
import { $api, apiClient } from "@/lib/api-client";

interface ConnectionRow {
	connection_id: string;
	server_id: string;
	server_name: string;
	available_in_chat: boolean;
	available_to_autonomous: boolean;
	has_service_token: boolean;
}

export function UserMCPConnections() {
	const queryClient = useQueryClient();

	// All connections visible to the user (org-scoped on the server side).
	const {
		data: connections = [],
		isLoading: connsLoading,
		refetch,
	} = $api.useQuery("get", "/api/mcp-connections", {
		params: { query: {} },
	});

	// Server templates (so we can label rows with the service name).
	const { data: servers = [], isLoading: serversLoading } = $api.useQuery(
		"get",
		"/api/mcp-servers",
		{ params: { query: { active_only: false } } },
	);

	const isLoading = connsLoading || serversLoading;

	const rows: ConnectionRow[] = useMemo(() => {
		const serverById = new Map<string, string>();
		for (const s of servers) serverById.set(s.id, s.name);
		return connections.map((c) => ({
			connection_id: c.id,
			server_id: c.server_id,
			server_name: serverById.get(c.server_id) ?? "Unknown service",
			available_in_chat: c.available_in_chat,
			available_to_autonomous: c.available_to_autonomous,
			has_service_token: c.service_oauth_token_id != null,
		}));
	}, [connections, servers]);

	// Listen for the popup's success message and invalidate the list. The
	// callback page (api/src/routers/mcp_oauth_callback.py) posts a
	// {type: 'mcp_oauth_success', connection_id} message back to the opener.
	useEffect(() => {
		function handleMessage(ev: MessageEvent) {
			if (ev.origin !== window.location.origin) return;
			const data = ev.data as { type?: string; connection_id?: string } | null;
			if (!data || typeof data !== "object") return;
			if (data.type === "mcp_oauth_success") {
				toast.success("Connected — your personal access is now linked");
				queryClient.invalidateQueries({
					queryKey: ["get", "/api/mcp-connections"],
				});
			} else if (data.type === "mcp_oauth_error") {
				toast.error(
					`Connection failed: ${(data as { error?: string }).error ?? "unknown"}`,
				);
			}
		}
		window.addEventListener("message", handleMessage);
		return () => window.removeEventListener("message", handleMessage);
	}, [queryClient]);

	async function handleConnect(connectionId: string, serverName: string) {
		try {
			const { data, error } = await apiClient.GET(
				"/api/me/mcp-connections/{connection_id}/connect",
				{ params: { path: { connection_id: connectionId } } },
			);
			if (error || !data?.authorization_url) {
				toast.error(`Failed to start ${serverName} OAuth flow`);
				return;
			}
			const popup = window.open(
				data.authorization_url,
				"mcp_user_oauth",
				"width=600,height=720",
			);
			if (!popup) {
				toast.error(
					"Popup blocked — please allow popups for this site and try again",
				);
				return;
			}
			toast.message(`Continue ${serverName} sign-in in the popup window`);
		} catch (err) {
			toast.error(
				err instanceof Error
					? err.message
					: "Failed to start OAuth flow",
			);
		}
	}

	function fallbackLabel(row: ConnectionRow) {
		if (row.available_in_chat && row.has_service_token) {
			return (
				<>
					<span className="text-foreground">Shared service account</span>
					<div className="text-xs text-muted-foreground">
						(if you disconnect)
					</div>
				</>
			);
		}
		return (
			<>
				<Badge variant="default" className="bg-rose-600 hover:bg-rose-700">
					No fallback
				</Badge>
				<div className="text-xs text-muted-foreground">
					Tools disabled until you connect
				</div>
			</>
		);
	}

	return (
		<TooltipProvider>
			<Card>
				<CardContent className="py-6 space-y-4">
					<div className="flex items-center justify-between">
						<div>
							<h2 className="text-lg font-semibold">My Connections</h2>
							<p className="mt-1 text-sm text-muted-foreground max-w-2xl">
								Connect your account to external tools so agents can act
								with your identity (and your permissions). Without a
								personal connection, the agent uses the shared org service
								account if your admin has enabled it.
							</p>
						</div>
						<Button
							variant="outline"
							size="sm"
							onClick={() => refetch()}
							title="Refresh"
						>
							<RefreshCw className="h-4 w-4 mr-1" />
							Refresh
						</Button>
					</div>

					{isLoading ? (
						<div className="space-y-2">
							{[...Array(3)].map((_, i) => (
								<Skeleton key={i} className="h-12 w-full" />
							))}
						</div>
					) : rows.length === 0 ? (
						<div className="border rounded-md py-12 text-center">
							<Plug className="h-10 w-10 mx-auto text-muted-foreground" />
							<h3 className="mt-3 font-semibold">No connections available</h3>
							<p className="mt-1 text-sm text-muted-foreground max-w-md mx-auto">
								No MCP services have been set up for your organization yet.
								Ask an admin to add a connection.
							</p>
						</div>
					) : (
						<DataTable>
							<DataTableHeader>
								<DataTableRow>
									<DataTableHead>Service</DataTableHead>
									<DataTableHead>Your status</DataTableHead>
									<DataTableHead>Org default</DataTableHead>
									<DataTableHead className="text-right">
										Actions
									</DataTableHead>
								</DataTableRow>
							</DataTableHeader>
							<DataTableBody>
								{rows.map((row) => (
									<DataTableRow key={row.connection_id}>
										<DataTableCell className="font-medium">
											{row.server_name}
										</DataTableCell>
										<DataTableCell>
											{/*
											 * Backend gap: no GET endpoint for the caller's
											 * user_mcp_credentials yet, so we display a
											 * neutral status. Connect/Reconnect drives the
											 * actual link.
											 */}
											<Badge variant="secondary">Status unknown</Badge>
											<div className="text-xs text-muted-foreground mt-1">
												Click Connect to (re)link your account
											</div>
										</DataTableCell>
										<DataTableCell>{fallbackLabel(row)}</DataTableCell>
										<DataTableCell className="text-right">
											<div className="inline-flex items-center gap-2">
												<Button
													size="sm"
													onClick={() =>
														handleConnect(
															row.connection_id,
															row.server_name,
														)
													}
												>
													Connect
												</Button>
												<Tooltip>
													<TooltipTrigger asChild>
														<span tabIndex={0}>
															<Button
																variant="outline"
																size="sm"
																disabled
																className="text-rose-600"
																onClick={() => {
																	// TODO(phase4-gap): backend
																	// has no DELETE endpoint for
																	// user_mcp_credentials. Wire
																	// this up once that ships.
																	console.warn(
																		"[UserMCPConnections] disconnect not implemented — backend DELETE missing",
																	);
																}}
															>
																Disconnect
															</Button>
														</span>
													</TooltipTrigger>
													<TooltipContent>
														Disconnect endpoint coming soon
													</TooltipContent>
												</Tooltip>
											</div>
										</DataTableCell>
									</DataTableRow>
								))}
							</DataTableBody>
						</DataTable>
					)}

					{/*
					 * Faint hint that we're aware of the per-user status gap. Once
					 * GET /api/me/mcp-credentials lands we replace the column with
					 * Connected (since…) / Not connected.
					 */}
					<p className="text-xs text-muted-foreground/80">
						Status display is best-effort while the per-user credential
						listing endpoint is being added. After you connect, the org
						admin can confirm in the MCP Servers admin view.
					</p>
				</CardContent>
			</Card>
		</TooltipProvider>
	);
}

// Re-export under a default for lazy/dynamic imports if ever needed.
export default UserMCPConnections;

// Trivial loader to keep this file minimal in JSX usage.
export function UserMCPConnectionsLoader() {
	return (
		<div className="flex items-center justify-center py-12">
			<Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
		</div>
	);
}

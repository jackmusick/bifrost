import {
	Trash2,
	ExternalLink,
	Clock,
	CheckCircle2,
	XCircle,
	Loader2,
	AlertCircle,
	Copy,
	Check,
	Pencil,
	RefreshCw,
	MoreVertical,
} from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
	Card,
	CardContent,
	CardFooter,
	CardHeader,
	CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
	Tooltip,
	TooltipContent,
	TooltipProvider,
	TooltipTrigger,
} from "@/components/ui/tooltip";
import {
	DropdownMenu,
	DropdownMenuContent,
	DropdownMenuItem,
	DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { toast } from "sonner";
import type { components } from "@/lib/v1";
import { getStatusLabel, isExpired, expiresSoon } from "@/lib/client-types";

type OAuthConnectionDetail = components["schemas"]["OAuthConnectionDetail"];

interface OAuthConnectionCardProps {
	connection: OAuthConnectionDetail;
	onAuthorize: (connectionName: string) => Promise<string | void>;
	onEdit: (connectionName: string) => void;
	onRefresh: (connectionName: string) => void;
	onDelete: (connectionName: string) => void;
	onCancel?: (connectionName: string) => void;
	isAuthorizing?: boolean;
	isRefreshing?: boolean;
	isDeleting?: boolean;
	isCanceling?: boolean;
}

export function OAuthConnectionCard({
	connection,
	onAuthorize,
	onEdit,
	onRefresh,
	onDelete,
	onCancel,
	isAuthorizing = false,
	isRefreshing = false,
	isDeleting = false,
	isCanceling = false,
}: OAuthConnectionCardProps) {
	const [copiedCallback, setCopiedCallback] = useState(false);

	const callbackUrl = `${window.location.origin}/oauth/callback/${connection.connection_name}`;

	const handleCopyCallback = () => {
		navigator.clipboard.writeText(callbackUrl);
		setCopiedCallback(true);
		toast.success("Callback URL copied to clipboard");
		setTimeout(() => setCopiedCallback(false), 2000);
	};

	const handleAuthorizeClick = async () => {
		await onAuthorize(connection.connection_name);
	};

	const getStatusIcon = () => {
		switch (connection.status) {
			case "completed":
				return <CheckCircle2 className="h-4 w-4 text-green-600" />;
			case "failed":
				return <XCircle className="h-4 w-4 text-red-600" />;
			case "waiting_callback":
			case "testing":
				return (
					<Loader2 className="h-4 w-4 text-yellow-600 animate-spin" />
				);
			default:
				return <Clock className="h-4 w-4 text-gray-500" />;
		}
	};

	const canConnect = connection.oauth_flow_type !== "client_credentials";
	const needsReconnection =
		connection.status === "not_connected" || connection.status === "failed";

	const expirationWarning =
		connection.expires_at && expiresSoon(connection.expires_at);
	const isTokenExpired =
		connection.expires_at && isExpired(connection.expires_at);

	const formatDateTime = (dateStr?: string) => {
		if (!dateStr) return "Never";

		// Parse the date - backend sends UTC timestamps without 'Z' suffix
		// Add 'Z' to explicitly mark it as UTC, then JavaScript will convert to local time
		const utcDateStr = dateStr.endsWith("Z") ? dateStr : `${dateStr}Z`;
		const date = new Date(utcDateStr);
		const now = new Date();
		const diffMs = date.getTime() - now.getTime();
		const diffMins = Math.floor(Math.abs(diffMs) / 60000);
		const diffHours = Math.floor(Math.abs(diffMs) / 3600000);
		const diffDays = Math.floor(Math.abs(diffMs) / 86400000);

		// For dates within 7 days, show relative time
		if (diffDays < 7) {
			// Past dates (negative diffMs) - show "X ago"
			if (diffMs < 0) {
				if (diffMins < 60) {
					return `${diffMins} minute${diffMins !== 1 ? "s" : ""} ago`;
				} else if (diffHours < 24) {
					return `${diffHours} hour${diffHours !== 1 ? "s" : ""} ago`;
				} else {
					return `${diffDays} day${diffDays !== 1 ? "s" : ""} ago`;
				}
			}

			// Future dates (positive diffMs) - show "in X"
			if (diffMs > 0) {
				if (diffMins < 60) {
					return `in ${diffMins} minute${diffMins !== 1 ? "s" : ""}`;
				} else if (diffHours < 24) {
					return `in ${diffHours} hour${diffHours !== 1 ? "s" : ""}`;
				} else {
					return `in ${diffDays} day${diffDays !== 1 ? "s" : ""}`;
				}
			}

			// Exactly now
			return "just now";
		}

		// Absolute dates for far past/future (converts to user's local timezone)
		return date.toLocaleString(undefined, {
			month: "short",
			day: "numeric",
			year: "numeric",
			hour: "numeric",
			minute: "2-digit",
		});
	};

	// Compact format for badges
	const formatDateTimeCompact = (dateStr?: string) => {
		if (!dateStr) return "Never";

		const utcDateStr = dateStr.endsWith("Z") ? dateStr : `${dateStr}Z`;
		const date = new Date(utcDateStr);
		const now = new Date();
		const diffMs = date.getTime() - now.getTime();
		const diffMins = Math.floor(Math.abs(diffMs) / 60000);
		const diffHours = Math.floor(Math.abs(diffMs) / 3600000);
		const diffDays = Math.floor(Math.abs(diffMs) / 86400000);

		// For dates within 7 days, show compact relative time
		if (diffDays < 7) {
			if (diffMs < 0) {
				// Past
				if (diffMins < 60) return `${diffMins}m ago`;
				if (diffHours < 24) return `${diffHours}h ago`;
				return `${diffDays}d ago`;
			}

			// Future
			if (diffMins < 60) return `${diffMins}m`;
			if (diffHours < 24) return `${diffHours}h`;
			return `${diffDays}d`;
		}

		// Absolute dates
		return date.toLocaleDateString(undefined, {
			month: "short",
			day: "numeric",
		});
	};

	return (
		<Card className="flex flex-col h-full hover:shadow-lg transition-shadow">
			<CardHeader className="pb-3 !grid-cols-1 !grid-rows-1">
				<div className="flex items-start justify-between gap-3">
					<div className="flex-1 min-w-0 space-y-1">
						<CardTitle className="text-lg truncate">
							{connection.connection_name}
						</CardTitle>
						<Badge variant="outline" className="text-xs w-fit">
							{connection.oauth_flow_type}
						</Badge>
					</div>
					<div className="flex items-center gap-2 shrink-0">
						{connection.expires_at && (
							<TooltipProvider>
								<Tooltip>
									<TooltipTrigger asChild>
										<div
											className={`flex items-center gap-1 text-xs cursor-help whitespace-nowrap ${isTokenExpired ? "text-red-600" : expirationWarning ? "text-yellow-600" : "text-muted-foreground"}`}
										>
											{isTokenExpired ? (
												<XCircle className="h-3 w-3" />
											) : (
												<CheckCircle2 className="h-3 w-3" />
											)}
											<span>
												{formatDateTimeCompact(
													connection.expires_at,
												)}
											</span>
										</div>
									</TooltipTrigger>
									<TooltipContent>
										<p>
											{isTokenExpired
												? "Expired"
												: "Expires"}{" "}
											{formatDateTime(
												connection.expires_at,
											)}
										</p>
									</TooltipContent>
								</Tooltip>
							</TooltipProvider>
						)}
						<TooltipProvider>
							<Tooltip>
								<TooltipTrigger asChild>
									<div className="cursor-help">
										{getStatusIcon()}
									</div>
								</TooltipTrigger>
								<TooltipContent>
									<p>{getStatusLabel(connection.status)}</p>
								</TooltipContent>
							</Tooltip>
						</TooltipProvider>
					</div>
				</div>
			</CardHeader>

			<CardContent className="flex-1 space-y-3">
				{/* Callback URL for not connected state */}
				{needsReconnection && canConnect && (
					<div className="space-y-2">
						<p className="text-xs font-medium text-muted-foreground">
							Callback URL:
						</p>
						<div className="flex items-center gap-2">
							<code className="flex-1 px-2 py-1 bg-muted rounded text-xs break-all">
								{callbackUrl}
							</code>
							<Button
								type="button"
								variant="outline"
								size="sm"
								onClick={handleCopyCallback}
							>
								{copiedCallback ? (
									<Check className="h-3 w-3" />
								) : (
									<Copy className="h-3 w-3" />
								)}
							</Button>
						</div>
						<p className="text-xs text-muted-foreground">
							Add this URL to your OAuth app's allowed redirect
							URIs
						</p>
					</div>
				)}

				{/* Status Message - only show for non-completed statuses */}
				{connection.status_message &&
					connection.status !== "completed" && (
						<div className="text-sm text-muted-foreground bg-muted p-2 rounded-md">
							{connection.status_message}
						</div>
					)}

				{/* Expiration Warning */}
				{connection.status === "completed" && isTokenExpired && (
					<div className="flex items-start gap-2 text-sm text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-900/50 p-2 rounded-md">
						<AlertCircle className="h-4 w-4 mt-0.5" />
						<span>
							Token expired. Reconnect to continue using this
							connection.
						</span>
					</div>
				)}

				{connection.status === "completed" &&
					!isTokenExpired &&
					expirationWarning && (
						<div className="flex items-start gap-2 text-sm text-yellow-600 dark:text-yellow-400 bg-yellow-50 dark:bg-yellow-950/30 border border-yellow-200 dark:border-yellow-900/50 p-2 rounded-md">
							<AlertCircle className="h-4 w-4 mt-0.5" />
							<span>Token expires soon</span>
						</div>
					)}
			</CardContent>

			<CardFooter className="flex flex-col gap-2">
				<div className="flex gap-2 w-full">
					{needsReconnection && canConnect && (
						<Button
							onClick={handleAuthorizeClick}
							disabled={isAuthorizing}
							className="flex-1"
						>
							{isAuthorizing ? (
								<>
									<Loader2 className="mr-2 h-4 w-4 animate-spin" />
									Connecting...
								</>
							) : (
								<>
									<ExternalLink className="mr-2 h-4 w-4" />
									{connection.status === "failed"
										? "Reconnect"
										: "Connect"}
								</>
							)}
						</Button>
					)}

					{connection.status === "completed" && canConnect && (
						<Button
							onClick={handleAuthorizeClick}
							disabled={isAuthorizing}
							variant="outline"
							className="flex-1"
						>
							{isAuthorizing ? (
								<>
									<Loader2 className="mr-2 h-4 w-4 animate-spin" />
									Reconnecting...
								</>
							) : (
								<>
									<ExternalLink className="mr-2 h-4 w-4" />
									Reconnect
								</>
							)}
						</Button>
					)}

					{/* For client_credentials, show Refresh Token button where Reconnect would be */}
					{connection.status === "completed" &&
						!canConnect &&
						connection.expires_at && (
							<Button
								onClick={() =>
									onRefresh(connection.connection_name)
								}
								disabled={isRefreshing}
								variant="outline"
								className="flex-1"
							>
								{isRefreshing ? (
									<>
										<Loader2 className="mr-2 h-4 w-4 animate-spin" />
										Refreshing...
									</>
								) : (
									<>
										<RefreshCw className="mr-2 h-4 w-4" />
										Refresh Token
									</>
								)}
							</Button>
						)}

					{connection.status === "waiting_callback" && (
						<>
							<Button
								variant="outline"
								className="flex-1"
								disabled
							>
								<Loader2 className="mr-2 h-4 w-4 animate-spin" />
								Connecting...
							</Button>
							{onCancel && (
								<Button
									variant="ghost"
									size="sm"
									onClick={() =>
										onCancel(connection.connection_name)
									}
									disabled={isCanceling}
								>
									{isCanceling ? "Canceling..." : "Cancel"}
								</Button>
							)}
						</>
					)}

					{connection.status === "testing" && (
						<Button variant="outline" className="flex-1" disabled>
							<Loader2 className="mr-2 h-4 w-4 animate-spin" />
							Testing connection...
						</Button>
					)}

					<DropdownMenu>
						<DropdownMenuTrigger asChild>
							<Button variant="outline" size="icon">
								<MoreVertical className="h-4 w-4" />
							</Button>
						</DropdownMenuTrigger>
						<DropdownMenuContent align="end">
							{/* Only show refresh in dropdown for authorization_code flow (canConnect) */}
							{connection.status === "completed" &&
								connection.expires_at &&
								canConnect && (
									<DropdownMenuItem
										onClick={() =>
											onRefresh(
												connection.connection_name,
											)
										}
										disabled={isRefreshing}
									>
										<RefreshCw
											className={`mr-2 h-4 w-4 ${isRefreshing ? "animate-spin" : ""}`}
										/>
										{isRefreshing
											? "Refreshing..."
											: "Refresh token"}
									</DropdownMenuItem>
								)}
							<DropdownMenuItem
								onClick={() =>
									onEdit(connection.connection_name)
								}
							>
								<Pencil className="mr-2 h-4 w-4" />
								Edit
							</DropdownMenuItem>
							<DropdownMenuItem
								onClick={() =>
									onDelete(connection.connection_name)
								}
								disabled={isDeleting}
								className="text-red-600 focus:text-red-600"
							>
								<Trash2 className="mr-2 h-4 w-4" />
								{isDeleting ? "Deleting..." : "Delete"}
							</DropdownMenuItem>
						</DropdownMenuContent>
					</DropdownMenu>
				</div>
			</CardFooter>
		</Card>
	);
}

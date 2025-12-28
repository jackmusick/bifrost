/**
 * MCP OAuth Callback Page
 *
 * Handles the OAuth callback for MCP (Model Context Protocol) clients.
 * This page is loaded after the user authenticates via Bifrost login.
 *
 * The flow:
 * 1. MCP client (e.g., Claude Desktop) initiates OAuth at /authorize
 * 2. User is redirected to Bifrost login
 * 3. After login, browser navigates to /mcp/callback with internal_state
 * 4. This component fetches /mcp/callback via XHR (works with Vite proxy)
 * 5. Server returns redirect_url in JSON response (claude:// protocol URL)
 * 6. Component opens the URL (triggers Claude Desktop) and closes the tab
 */

import { useEffect, useState, useRef } from "react";
import { useSearchParams } from "react-router-dom";
import { Loader2, AlertCircle, CheckCircle2 } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";

export function MCPCallback() {
	const [searchParams] = useSearchParams();
	const [error, setError] = useState<string | null>(null);
	const [success, setSuccess] = useState(false);
	const hasHandledRef = useRef(false);

	useEffect(() => {
		// Prevent double execution in strict mode
		if (hasHandledRef.current) return;
		hasHandledRef.current = true;

		async function handleCallback() {
			const internalState = searchParams.get("internal_state");

			if (!internalState) {
				setError("Missing internal_state parameter");
				return;
			}

			try {
				// Fetch the callback endpoint via XHR - Vite proxy handles this
				// The server returns a JSON response with redirect_url when Accept: application/json
				const response = await fetch(
					`/mcp/callback?internal_state=${internalState}`,
					{
						headers: {
							Accept: "application/json",
						},
						credentials: "include", // Include cookies for auth
					},
				);

				if (!response.ok) {
					const data = await response.json().catch(() => ({}));
					setError(
						data.error_description ||
							data.error ||
							`Callback failed: ${response.status}`,
					);
					return;
				}

				const data = await response.json();

				if (data.redirect_url) {
					// Show success state first
					setSuccess(true);

					// Use location.replace to redirect to the protocol URL (e.g., claude://)
					// This triggers the desktop app and doesn't trigger popup blockers
					// The page will show the success message while the protocol handler takes over
					setTimeout(() => {
						window.location.replace(data.redirect_url);
					}, 100);
				} else {
					setError("No redirect URL returned from server");
				}
			} catch (err) {
				setError(
					err instanceof Error ? err.message : "MCP callback failed",
				);
			}
		}

		handleCallback();
	}, [searchParams]);

	if (error) {
		return (
			<div className="min-h-screen flex items-center justify-center bg-background p-4">
				<div className="w-full max-w-md space-y-4">
					<Alert variant="destructive">
						<AlertCircle className="h-4 w-4" />
						<AlertDescription>
							OAuth callback failed: {error}
						</AlertDescription>
					</Alert>
					<Button
						className="w-full"
						onClick={() => (window.location.href = "/")}
					>
						Return to Home
					</Button>
				</div>
			</div>
		);
	}

	if (success) {
		return (
			<div className="min-h-screen flex items-center justify-center bg-background p-4">
				<div className="w-full max-w-md space-y-4 text-center">
					<CheckCircle2 className="h-12 w-12 mx-auto text-green-500" />
					<h2 className="text-xl font-semibold">
						Authorization Complete
					</h2>
					<p className="text-muted-foreground">
						You can close this tab and return to Claude Desktop.
					</p>
				</div>
			</div>
		);
	}

	return (
		<div className="min-h-screen flex items-center justify-center bg-background">
			<div className="text-center">
				<Loader2 className="h-8 w-8 animate-spin mx-auto mb-4 text-primary" />
				<p className="text-muted-foreground">
					Completing MCP authorization...
				</p>
			</div>
		</div>
	);
}

export default MCPCallback;

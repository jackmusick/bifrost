import { useEffect, useState, useRef } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import {
	Card,
	CardContent,
	CardDescription,
	CardHeader,
	CardTitle,
} from "@/components/ui/card";
import { Loader2, CheckCircle2, XCircle, AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { handleOAuthCallback } from "@/hooks/useOAuth";

export function OAuthCallback() {
	const navigate = useNavigate();
	const { connectionName } = useParams<{ connectionName: string }>();
	const [searchParams] = useSearchParams();
	const [status, setStatus] = useState<
		"processing" | "success" | "error" | "warning"
	>("processing");
	const [message, setMessage] = useState("Processing OAuth callback...");
	const [warning, setWarning] = useState<string | null>(null);
	const hasProcessed = useRef(false);

	useEffect(() => {
		const handleCallback = async () => {
			// Prevent double-processing (React.StrictMode, refresh, etc.)
			if (hasProcessed.current) {
				return;
			}
			hasProcessed.current = true;
			if (!connectionName) {
				setStatus("error");
				setMessage("Missing connection name in URL");
				return;
			}

			// Get query parameters from OAuth provider
			const code = searchParams.get("code");
			const error = searchParams.get("error");
			const errorDescription = searchParams.get("error_description");
			const state = searchParams.get("state");

			// Check for error from OAuth provider
			if (error) {
				setStatus("error");
				setMessage(
					`OAuth authorization failed: ${errorDescription || error}`,
				);
				return;
			}

			// Check for authorization code
			if (!code) {
				setStatus("error");
				setMessage("Missing authorization code from OAuth provider");
				return;
			}

			try {
				// Send the authorization code to the API for token exchange
				const response = await handleOAuthCallback(
					connectionName,
					code,
					state,
				);
				// eslint-disable-next-line @typescript-eslint/no-explicit-any
				const responseData = response as any; // Response may include error_message or warning_message

				// Check for error_message
				if (
					responseData &&
					typeof responseData === "object" &&
					"error_message" in responseData &&
					responseData.error_message
				) {
					setStatus("error");
					setMessage(responseData.error_message as string);
					// DO NOT auto-close - user must manually close after reading error
					return;
				}

				// Check for warning_message (e.g., no refresh token)
				if (
					responseData &&
					typeof responseData === "object" &&
					"warning_message" in responseData &&
					responseData.warning_message
				) {
					setWarning(responseData.warning_message as string);
					setStatus("warning");
					setMessage("Connection established with limitations");

					// Notify parent window to refresh connections (even with warning)
					if (window.opener) {
						window.opener.postMessage(
							{
								type: "oauth_success",
								connectionName,
							},
							window.location.origin,
						);
					}

					// DO NOT auto-close - user must manually close after reading warning
					return;
				}

				// No warning or error - proceed with normal success flow
				setStatus("success");
				setMessage("OAuth connection completed successfully!");

				// Notify parent window to refresh connections
				if (window.opener) {
					window.opener.postMessage(
						{
							type: "oauth_success",
							connectionName,
						},
						window.location.origin,
					);
				}

				// Auto-close on success (no warning)
				setTimeout(() => {
					window.close();
					setTimeout(() => {
						navigate("/oauth");
					}, 100);
				}, 1500);
			} catch (err: unknown) {
				setStatus("error");
				const errorMsg =
					(err as Error).message ||
					"Failed to complete OAuth connection";

				// Provide helpful message for common errors
				if (
					errorMsg.includes("already been redeemed") ||
					errorMsg.includes("already been used")
				) {
					setMessage(
						"This authorization has already been processed. You can close this window.",
					);
					// Auto-close since this is likely a refresh/duplicate
					setTimeout(() => {
						window.close();
					}, 2000);
				} else {
					setMessage(errorMsg);
				}
			}
		};

		handleCallback();
	}, [connectionName, searchParams, navigate]);

	return (
		<div className="flex items-center justify-center min-h-screen bg-background p-4">
			<Card className="max-w-md w-full hover:!transform-none">
				<CardHeader>
					<div className="flex items-center gap-2">
						{status === "processing" && (
							<Loader2 className="h-6 w-6 animate-spin text-blue-500" />
						)}
						{status === "success" && (
							<CheckCircle2 className="h-6 w-6 text-green-500" />
						)}
						{status === "warning" && (
							<AlertTriangle className="h-6 w-6 text-yellow-600" />
						)}
						{status === "error" && (
							<XCircle className="h-6 w-6 text-red-500" />
						)}
						<CardTitle>
							{status === "processing" &&
								"Processing OAuth Callback"}
							{status === "success" && "Authorization Successful"}
							{status === "warning" && "Warning"}
							{status === "error" && "Authorization Failed"}
						</CardTitle>
					</div>
					<CardDescription>
						Connection:{" "}
						<code className="font-mono">{connectionName}</code>
					</CardDescription>
				</CardHeader>
				<CardContent>
					<p className="text-sm text-muted-foreground mb-4">
						{message}
					</p>

					{/* Warning state */}
					{status === "warning" && warning && (
						<>
							<p className="text-sm mb-4">{warning}</p>
							<div className="flex justify-center">
								<Button
									onClick={() => window.close()}
									variant="default"
									className="w-48"
								>
									Close
								</Button>
							</div>
						</>
					)}

					{/* Success state - auto-closes */}
					{status === "success" && (
						<p className="text-xs text-muted-foreground">
							This window will close automatically...
						</p>
					)}

					{/* Error state - manual close */}
					{status === "error" && (
						<div className="flex justify-center">
							<Button
								onClick={() => window.close()}
								variant="outline"
								className="w-48"
							>
								Close
							</Button>
						</div>
					)}
				</CardContent>
			</Card>
		</div>
	);
}

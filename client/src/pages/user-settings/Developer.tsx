import { useState, useEffect } from "react";
import {
	Card,
	CardContent,
	CardDescription,
	CardHeader,
	CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import {
	Select,
	SelectContent,
	SelectItem,
	SelectTrigger,
	SelectValue,
} from "@/components/ui/select";
import { toast } from "sonner";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
	Loader2,
	Code,
	Download,
	ExternalLink,
	AlertCircle,
	Star,
} from "lucide-react";
import { sdkService, type DeveloperContext } from "@/services/sdk";
import { apiClient } from "@/lib/api-client";
import type { components } from "@/lib/v1";

type Organization = components["schemas"]["OrganizationPublic"];

export function DeveloperSettings() {
	const [_context, setContext] = useState<DeveloperContext | null>(null);
	const [organizations, setOrganizations] = useState<Organization[]>([]);
	const [loading, setLoading] = useState(true);
	const [error, setError] = useState<string | null>(null);
	const [saving, setSaving] = useState(false);

	// Form state
	const [selectedOrg, setSelectedOrg] = useState<string>("__none__");
	const [trackExecutions, setTrackExecutions] = useState(true);

	// Load data
	useEffect(() => {
		async function loadData() {
			try {
				const [contextData, orgsResult] = await Promise.all([
					sdkService.getContext(),
					apiClient.GET("/api/organizations"),
				]);
				const orgsData = orgsResult.data ?? [];

				setContext(contextData);
				setOrganizations(orgsData);

				// Set form defaults
				setSelectedOrg(contextData.organization?.id || "__none__");
				setTrackExecutions(contextData.track_executions);
			} catch (err) {
				console.error("Failed to load developer settings:", err);
				setError(
					"Failed to load developer settings. Please try again.",
				);
				toast.error("Failed to load developer settings");
			} finally {
				setLoading(false);
			}
		}

		loadData();
	}, []);

	// Save context settings
	const handleSaveContext = async () => {
		setSaving(true);
		try {
			const updated = await sdkService.updateContext({
				default_org_id: selectedOrg === "__none__" ? null : selectedOrg,
				track_executions: trackExecutions,
			});
			setContext(updated);
			toast.success("Developer settings saved");
		} catch (error) {
			console.error("Failed to save settings:", error);
			toast.error("Failed to save settings");
		} finally {
			setSaving(false);
		}
	};

	// Retry function for error state
	const handleRetry = () => {
		setError(null);
		setLoading(true);
		window.location.reload();
	};

	if (loading) {
		return (
			<div className="flex items-center justify-center py-12">
				<Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
			</div>
		);
	}

	if (error) {
		return (
			<Card>
				<CardContent className="p-6">
					<Alert variant="destructive">
						<AlertCircle className="h-4 w-4" />
						<AlertDescription>{error}</AlertDescription>
					</Alert>
					<Button onClick={handleRetry} className="mt-4">
						Retry
					</Button>
				</CardContent>
			</Card>
		);
	}

	return (
		<div className="space-y-6">
			{/* SDK Setup Instructions */}
			<Card>
				<CardHeader>
					<div className="flex items-center gap-2">
						<Code className="h-5 w-5" />
						<CardTitle>
							Local Development with Bifrost SDK
						</CardTitle>
					</div>
					<CardDescription>
						Develop and test workflows locally using VS Code or your
						preferred IDE
					</CardDescription>
				</CardHeader>
				<CardContent className="space-y-4">
					<div className="rounded-lg border bg-muted/50 p-4 space-y-3">
						<p className="font-medium">Quick Start</p>
						<div className="space-y-2 text-sm">
							<div className="flex items-start gap-2">
								<span className="bg-primary text-primary-foreground rounded-full w-5 h-5 flex items-center justify-center text-xs flex-shrink-0 mt-0.5">
									1
								</span>
								<div>
									<p>Install the SDK:</p>
									<code className="block mt-1 p-2 bg-background rounded text-xs">
										pip install {window.location.origin}
										/api/cli/download
									</code>
								</div>
							</div>
							<div className="flex items-start gap-2">
								<span className="bg-primary text-primary-foreground rounded-full w-5 h-5 flex items-center justify-center text-xs flex-shrink-0 mt-0.5">
									2
								</span>
								<div>
									<p>Login to authenticate:</p>
									<code className="block mt-1 p-2 bg-background rounded text-xs">
										bifrost login
									</code>
								</div>
							</div>
							<div className="flex items-start gap-2">
								<span className="bg-primary text-primary-foreground rounded-full w-5 h-5 flex items-center justify-center text-xs flex-shrink-0 mt-0.5">
									3
								</span>
								<div>
									<p>Run your workflow:</p>
									<code className="block mt-1 p-2 bg-background rounded text-xs">
										bifrost run my_workflow.py
									</code>
								</div>
							</div>
						</div>
					</div>

					<div className="flex gap-2">
						<Button variant="outline" asChild>
							<a href={sdkService.getSdkDownloadUrl()} download>
								<Download className="h-4 w-4 mr-2" />
								Download SDK
							</a>
						</Button>
						<Button variant="outline" asChild>
							<a
								href="https://docs.bifrost.io/sdk"
								target="_blank"
								rel="noopener noreferrer"
							>
								<ExternalLink className="h-4 w-4 mr-2" />
								Documentation
							</a>
						</Button>
					</div>
				</CardContent>
			</Card>

			{/* Developer Context Settings */}
			<Card>
				<CardHeader>
					<CardTitle>Developer Context</CardTitle>
					<CardDescription>
						Configure default settings for local SDK development
					</CardDescription>
				</CardHeader>
				<CardContent className="space-y-4">
					<div className="space-y-2">
						<Label htmlFor="default-org">
							Default Organization
						</Label>
						<Select
							value={selectedOrg}
							onValueChange={setSelectedOrg}
						>
							<SelectTrigger id="default-org">
								<SelectValue placeholder="Select organization" />
							</SelectTrigger>
							<SelectContent>
								<SelectItem value="__none__">
									None (personal)
								</SelectItem>
								{organizations.map((org) => (
									<SelectItem key={org.id} value={org.id}>
										<div className="flex items-center gap-2">
											{org.is_provider && (
												<Star className="h-3 w-3 text-amber-500 fill-amber-500" />
											)}
											<span>{org.name}</span>
											{org.is_provider && (
												<span className="text-xs text-amber-600">
													Provider
												</span>
											)}
										</div>
									</SelectItem>
								))}
							</SelectContent>
						</Select>
						<p className="text-xs text-muted-foreground">
							Organization context for workflow executions run
							from the SDK
						</p>
					</div>

					<div className="flex items-center justify-between">
						<div className="space-y-0.5">
							<Label htmlFor="track-executions">
								Track Executions
							</Label>
							<p className="text-xs text-muted-foreground">
								Log SDK executions in the Executions panel
							</p>
						</div>
						<Switch
							id="track-executions"
							checked={trackExecutions}
							onCheckedChange={setTrackExecutions}
						/>
					</div>

					<div className="flex justify-end">
						<Button onClick={handleSaveContext} disabled={saving}>
							{saving ? (
								<>
									<Loader2 className="h-4 w-4 mr-2 animate-spin" />
									Saving...
								</>
							) : (
								"Save Settings"
							)}
						</Button>
					</div>
				</CardContent>
			</Card>
		</div>
	);
}

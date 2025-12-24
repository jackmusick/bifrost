import { useEffect, useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { TabActions } from "@/components/ui/tab-actions";
import { WorkflowKeys } from "@/pages/WorkflowKeys";
import { Branding } from "@/pages/settings/Branding";
import { GitHub } from "@/pages/settings/GitHub";
import { LLMConfig } from "@/pages/settings/LLMConfig";
import { Maintenance } from "@/pages/settings/Maintenance";

export function Settings() {
	const navigate = useNavigate();
	const location = useLocation();
	const [tabActions, setTabActions] = useState<React.ReactNode>(null);

	// Parse the current tab from the URL path
	const currentTab =
		location.pathname.split("/settings/")[1] || "workflow-keys";

	const handleTabChange = (value: string) => {
		navigate(`/settings/${value}`);
	};

	// Redirect /settings to /settings/workflow-keys
	useEffect(() => {
		if (location.pathname === "/settings") {
			navigate("/settings/workflow-keys", { replace: true });
		}
	}, [location.pathname, navigate]);

	return (
		<div className="max-w-3xl mx-auto space-y-6">
			<div>
				<h1 className="text-4xl font-extrabold tracking-tight">
					Settings
				</h1>
				<p className="mt-2 text-muted-foreground">
					Manage platform settings and configuration
				</p>
			</div>

			<Tabs value={currentTab} onValueChange={handleTabChange}>
				<div className="flex items-center justify-between">
					<TabsList>
						<TabsTrigger value="workflow-keys">
							Workflow Keys
						</TabsTrigger>
						<TabsTrigger value="github">GitHub</TabsTrigger>
						<TabsTrigger value="branding">Branding</TabsTrigger>
						<TabsTrigger value="ai">AI</TabsTrigger>
						<TabsTrigger value="maintenance">
							Maintenance
						</TabsTrigger>
					</TabsList>

					{tabActions && <TabActions>{tabActions}</TabActions>}
				</div>

				<TabsContent value="workflow-keys" className="mt-6">
					<WorkflowKeys />
				</TabsContent>

				<TabsContent value="github" className="mt-6">
					<GitHub />
				</TabsContent>

				<TabsContent value="branding" className="mt-6">
					<Branding onActionsChange={setTabActions} />
				</TabsContent>

				<TabsContent value="ai" className="mt-6">
					<LLMConfig />
				</TabsContent>

				<TabsContent value="maintenance" className="mt-6">
					<Maintenance />
				</TabsContent>
			</Tabs>
		</div>
	);
}

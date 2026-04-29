import { useEffect } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { $api } from "@/lib/api-client";
import { WorkflowKeys } from "@/pages/settings/WorkflowKeys";
import { Branding } from "@/pages/settings/Branding";
import { Email } from "@/pages/settings/Email";
import { OAuth } from "@/pages/settings/OAuth";
import { GitHub } from "@/pages/settings/GitHub";
import { LLMConfig } from "@/pages/settings/LLMConfig";
import { ModelsSettings } from "@/pages/settings/ModelsSettings";
import { MCP } from "@/pages/settings/MCP";
import { Maintenance } from "@/pages/settings/Maintenance";
import { Bot, Key, Mail, Palette, Plug, Shield, Wrench } from "lucide-react";
import { Github } from "@/components/icons/GithubIcon";

export function Settings() {
	const navigate = useNavigate();
	const location = useLocation();

	// Hide the per-org Models section until the LLM provider is configured —
	// curating an allowlist when no provider exists is meaningless and the
	// /api/organizations endpoint may not even be reachable for the user yet.
	const { data: llmConfig } = $api.useQuery(
		"get",
		"/api/admin/llm/config",
		undefined,
		{ staleTime: 5 * 60 * 1000 },
	);
	const aiConfigured = Boolean(llmConfig?.provider && llmConfig?.model);

	// Parse the current tab from the URL path
	const currentTab = location.pathname.split("/settings/")[1] || "ai";

	const handleTabChange = (value: string) => {
		navigate(`/settings/${value}`);
	};

	// Redirect /settings to /settings/ai (first tab)
	useEffect(() => {
		if (location.pathname === "/settings") {
			navigate("/settings/ai", { replace: true });
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
				<div className="overflow-x-auto">
				<TabsList>
					<TabsTrigger value="ai">
						<Bot className="h-4 w-4 mr-1" />
						AI
					</TabsTrigger>
					<TabsTrigger value="mcp">
						<Plug className="h-4 w-4 mr-1" />
						MCP
					</TabsTrigger>
					<TabsTrigger value="branding">
						<Palette className="h-4 w-4 mr-1" />
						Branding
					</TabsTrigger>
					<TabsTrigger value="email">
						<Mail className="h-4 w-4 mr-1" />
						Email
					</TabsTrigger>
					<TabsTrigger value="sso">
						<Shield className="h-4 w-4 mr-1" />
						SSO
					</TabsTrigger>
					<TabsTrigger value="github">
						<Github className="h-4 w-4 mr-1" />
						GitHub
					</TabsTrigger>
					<TabsTrigger value="workflow-keys">
						<Key className="h-4 w-4 mr-1" />
						Workflow Keys
					</TabsTrigger>
					<TabsTrigger value="maintenance">
						<Wrench className="h-4 w-4 mr-1" />
						Maintenance
					</TabsTrigger>
				</TabsList>
				</div>

				<TabsContent value="ai" className="mt-6 space-y-6">
					<LLMConfig />
					{aiConfigured && <ModelsSettings />}
				</TabsContent>

				<TabsContent value="mcp" className="mt-6">
					<MCP />
				</TabsContent>

				<TabsContent value="branding" className="mt-6">
					<Branding />
				</TabsContent>

				<TabsContent value="email" className="mt-6">
					<Email />
				</TabsContent>

				<TabsContent value="sso" className="mt-6">
					<OAuth />
				</TabsContent>

				<TabsContent value="github" className="mt-6">
					<GitHub />
				</TabsContent>

				<TabsContent value="workflow-keys" className="mt-6">
					<WorkflowKeys />
				</TabsContent>

				<TabsContent value="maintenance" className="mt-6">
					<Maintenance />
				</TabsContent>
			</Tabs>
		</div>
	);
}

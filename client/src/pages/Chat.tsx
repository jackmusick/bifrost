/**
 * Chat Page
 *
 * Main chat interface for interacting with AI agents.
 * Supports conversation management, real-time streaming, and Chat V2 workspace
 * mode (re-scoped sidebar + right rail) when `?workspace=<id>` is present.
 *
 * If no LLM provider is configured, the entire route is replaced with a setup
 * prompt — chat is unusable without one, so we don't try to render the shell.
 */

import { useEffect } from "react";
import { useParams, useSearchParams, Link } from "react-router-dom";
import { Bot, Settings } from "lucide-react";

import { ChatLayout } from "@/components/chat";
import { Button } from "@/components/ui/button";
import { useChatStore } from "@/stores/chatStore";
import { useLLMConfig } from "@/hooks/useLLMConfig";
import { PageLoader } from "@/components/PageLoader";
import { useWorkspace } from "@/services/workspaceService";

export function Chat() {
	const { conversationId } = useParams<{ conversationId?: string }>();
	const [searchParams] = useSearchParams();
	const workspaceId = searchParams.get("workspace") ?? undefined;
	const { setActiveConversation, reset } = useChatStore();
	const {
		isConfigured,
		isPlatformAdmin,
		isLoading: configLoading,
	} = useLLMConfig();

	const { data: activeWorkspace } = useWorkspace(workspaceId);

	useEffect(() => {
		if (conversationId) {
			setActiveConversation(conversationId);
		}
	}, [conversationId, setActiveConversation]);

	useEffect(() => {
		return () => {
			reset();
		};
	}, [reset]);

	if (configLoading) {
		return <PageLoader message="Loading chat..." />;
	}

	// Gate the entire route until an LLM provider is configured.
	if (isConfigured === false) {
		return (
			<div className="h-full flex items-center justify-center">
				<div className="max-w-md text-center space-y-6 p-8">
					<div className="mx-auto w-16 h-16 rounded-full bg-muted flex items-center justify-center">
						<Bot className="h-8 w-8 text-muted-foreground" />
					</div>
					<div className="space-y-2">
						<h1 className="text-2xl font-semibold">
							AI Chat Not Configured
						</h1>
						<p className="text-muted-foreground">
							{isPlatformAdmin
								? "To enable AI chat, you need to configure an LLM provider (OpenAI or Anthropic) with a valid API key."
								: "Your platform admin needs to configure an LLM provider before chat is available."}
						</p>
					</div>
					{isPlatformAdmin && (
						<Button asChild>
							<Link to="/settings/ai">
								<Settings className="h-4 w-4 mr-2" />
								Configure AI Provider
							</Link>
						</Button>
					)}
				</div>
			</div>
		);
	}

	return (
		<div className="h-full">
			<ChatLayout
				initialConversationId={conversationId}
				activeWorkspace={activeWorkspace ?? null}
			/>
		</div>
	);
}

export default Chat;

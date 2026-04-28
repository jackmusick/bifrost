// Static mock data for preview routes. No API calls anywhere.

export type Tier = "fast" | "balanced" | "premium";

export const TIER_GLYPH: Record<Tier, string> = {
	fast: "⚡",
	balanced: "⚖",
	premium: "💎",
};

export const TIER_LABEL: Record<Tier, string> = {
	fast: "Fast",
	balanced: "Balanced",
	premium: "Premium",
};

export type Model = {
	id: string;
	display_name: string;
	provider: string;
	tier: Tier;
	context_window: number;
	is_alias?: boolean;
	target_id?: string; // when is_alias
	restricted_by?: "platform" | "org" | "role" | "workspace";
};

export const MODELS: Model[] = [
	// aliases
	{
		id: "bifrost-fast",
		display_name: "Fast",
		provider: "alias",
		tier: "fast",
		context_window: 200_000,
		is_alias: true,
		target_id: "claude-haiku-4-5",
	},
	{
		id: "bifrost-balanced",
		display_name: "Balanced",
		provider: "alias",
		tier: "balanced",
		context_window: 200_000,
		is_alias: true,
		target_id: "claude-sonnet-4-6",
	},
	{
		id: "bifrost-premium",
		display_name: "Premium",
		provider: "alias",
		tier: "premium",
		context_window: 200_000,
		is_alias: true,
		target_id: "claude-opus-4-7",
	},
	// real models — available
	{
		id: "claude-haiku-4-5",
		display_name: "Claude Haiku 4.5",
		provider: "Anthropic",
		tier: "fast",
		context_window: 200_000,
	},
	{
		id: "claude-sonnet-4-6",
		display_name: "Claude Sonnet 4.6",
		provider: "Anthropic",
		tier: "balanced",
		context_window: 200_000,
	},
	{
		id: "claude-opus-4-7",
		display_name: "Claude Opus 4.7",
		provider: "Anthropic",
		tier: "premium",
		context_window: 200_000,
		restricted_by: "role",
	},
	// real models — restricted
	{
		id: "gpt-5",
		display_name: "GPT-5",
		provider: "OpenAI",
		tier: "premium",
		context_window: 256_000,
		restricted_by: "org",
	},
	{
		id: "gpt-4o-mini",
		display_name: "GPT-4o mini",
		provider: "OpenAI",
		tier: "fast",
		context_window: 128_000,
		restricted_by: "workspace",
	},
	{
		id: "llama-3.3-70b",
		display_name: "Llama 3.3 70B",
		provider: "self-hosted",
		tier: "balanced",
		context_window: 128_000,
		restricted_by: "platform",
	},
];

export type Workspace = {
	id: string;
	name: string;
	scope: "personal" | "org" | "role";
	role_label?: string; // when scope=role
	conversations: { id: string; title: string; preview: string; ts: string }[];
};

export const WORKSPACES: Workspace[] = [
	{
		id: "personal",
		name: "Personal",
		scope: "personal",
		conversations: [
			{
				id: "p1",
				title: "Quick notes",
				preview: "I'll send the customer a follow-up later",
				ts: "2h ago",
			},
			{
				id: "p2",
				title: "Recipe ideas for tonight",
				preview: "Let me think about what's in the fridge",
				ts: "yesterday",
			},
		],
	},
	{
		id: "ws-onboarding",
		name: "Customer Onboarding",
		scope: "org",
		conversations: [
			{
				id: "o1",
				title: "Acme Corp setup",
				preview: "I created the initial folder structure",
				ts: "12m ago",
			},
			{
				id: "o2",
				title: "Welcome email draft",
				preview: "Here's a polished version",
				ts: "1h ago",
			},
			{
				id: "o3",
				title: "Office365 baseline",
				preview: "All conditional access policies validated",
				ts: "3d ago",
			},
		],
	},
	{
		id: "ws-tickets",
		name: "Ticket Triage",
		scope: "role",
		role_label: "Senior Tech",
		conversations: [
			{
				id: "t1",
				title: "VPN performance — Acme",
				preview: "Likely the inbound rule on FortiGate",
				ts: "30m ago",
			},
			{
				id: "t2",
				title: "Outlook crash loop — RKL",
				preview: "Try resetting the autodiscover",
				ts: "2h ago",
			},
		],
	},
	{
		id: "ws-sandbox",
		name: "Sandbox & experiments",
		scope: "personal",
		conversations: [
			{
				id: "s1",
				title: "Playing with the new agent",
				preview: "Try a smaller model next time",
				ts: "5d ago",
			},
		],
	},
];

export type Msg = {
	id: string;
	role: "user" | "assistant" | "system";
	content: string;
	model?: string;
	tier?: Tier;
	tokens?: number;
	delegated?: { agent_name: string; description: string; body: string };
};

export const MESSAGES: Msg[] = [
	{
		id: "m1",
		role: "user",
		content:
			"Hey, can you draft a follow-up email to Acme Corp about their VPN issue? They've been waiting since Tuesday.",
	},
	{
		id: "m2",
		role: "assistant",
		content:
			"I drafted a follow-up below. I checked the ticket history — last update was Tuesday at 2:14 PM, and the issue was about intermittent drops on the SSL VPN.\n\n> **Subject:** Quick update on your VPN issue\n>\n> Hi Sarah,\n>\n> Following up on ticket #4821. We identified the cause (a misconfigured firewall rule on the inbound side) and we'll have the fix deployed before EOD. I'll let you know once it's verified.\n>\n> Best,\n> [your name]\n\nWant me to send it directly, or revise the tone?",
		model: "claude-sonnet-4-6",
		tier: "balanced",
		tokens: 1247,
	},
	{
		id: "m3",
		role: "user",
		content:
			"Could you also tag in the network specialist agent for confirmation? I'd feel better having them double-check the firewall theory.",
	},
	{
		id: "m4",
		role: "assistant",
		content:
			"Confirmed — Network Specialist agreed it's the inbound rule. Sending the email now.",
		model: "claude-sonnet-4-6",
		tier: "balanced",
		tokens: 892,
		delegated: {
			agent_name: "Network Specialist",
			description: "Tier-3 networking & firewall expertise",
			body: "Looking at the ticket and FortiGate config: yes, the inbound SSL VPN rule is missing the `match-source-address` condition we added two weeks ago. That would explain the intermittent drops — connections from Acme's secondary ISP fail the policy match. Fix is to add `match-source-address all` to that rule. ETA 3 minutes once you're in the FortiGate.",
		},
	},
];

export type Attachment = {
	id: string;
	filename: string;
	size: string;
	type: "image" | "pdf" | "csv" | "text";
	progress?: number;
	tokens?: number;
	pages?: number;
	error?: string;
};

export const ATTACHMENTS_DEMO: Attachment[] = [
	{ id: "a1", filename: "server-rack-photo.jpg", size: "2.4 MB", type: "image" },
	{
		id: "a2",
		filename: "Acme_VPN_logs.pdf",
		size: "1.2 MB",
		type: "pdf",
		pages: 3,
		tokens: 2100,
	},
	{
		id: "a3",
		filename: "ticket-export.csv",
		size: "48 KB",
		type: "csv",
	},
	{
		id: "a4",
		filename: "uploading-now.txt",
		size: "12 KB",
		type: "text",
		progress: 64,
	},
	{
		id: "a5",
		filename: "broken-upload.png",
		size: "3.8 MB",
		type: "image",
		error: "Upload failed — connection lost",
	},
];

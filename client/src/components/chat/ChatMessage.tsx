/**
 * ChatMessage Component
 *
 * Renders a single chat message with role-based styling.
 * Clean, modern design similar to ChatGPT/Claude.
 * Supports full markdown rendering for AI responses.
 */

import { Bot, Wrench } from "lucide-react";
import { cn } from "@/lib/utils";
import type { components } from "@/lib/v1";
import { Badge } from "@/components/ui/badge";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";

type MessagePublic = components["schemas"]["MessagePublic"];
type ToolCall = components["schemas"]["ToolCall"];

/**
 * Parse message content and render @mentions as styled tags
 * Supports both @[Agent Name] (new) and @AgentName (legacy) formats
 */
function renderWithMentions(content: string): React.ReactNode[] {
	// Match both formats:
	// 1. @[Agent Name] - bracketed format (preferred)
	// 2. @Word - single word without brackets (legacy fallback)
	const mentionRegex = /@\[([^\]]+)\]|@(\w+)/g;
	const parts: React.ReactNode[] = [];
	let lastIndex = 0;
	let match;

	while ((match = mentionRegex.exec(content)) !== null) {
		// Add text before the mention
		if (match.index > lastIndex) {
			parts.push(content.slice(lastIndex, match.index));
		}

		// Get agent name from either capture group
		const agentName = match[1] || match[2];
		parts.push(
			<span
				key={`mention-${match.index}`}
				className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-black/25 font-medium text-sm"
			>
				<Bot className="h-3 w-3 shrink-0" />
				{agentName}
			</span>,
		);

		lastIndex = match.index + match[0].length;
	}

	// Add remaining text
	if (lastIndex < content.length) {
		parts.push(content.slice(lastIndex));
	}

	return parts.length > 0 ? parts : [content];
}

interface ChatMessageProps {
	message: MessagePublic;
	isStreaming?: boolean;
	onToolCallClick?: (toolCall: ToolCall) => void;
	hideToolBadges?: boolean;
}

export function ChatMessage({
	message,
	isStreaming,
	onToolCallClick,
	hideToolBadges,
}: ChatMessageProps) {
	const isUser = message.role === "user";

	// User message - clean right-aligned bubble with @mention badges
	if (isUser) {
		return (
			<div className="flex justify-end py-2 px-4">
				<div className="max-w-[80%] bg-primary text-primary-foreground rounded-2xl px-4 py-2.5 whitespace-pre-wrap">
					{renderWithMentions(message.content || "")}
				</div>
			</div>
		);
	}

	// Assistant message - full markdown rendering
	return (
		<div className={cn("py-3 px-4 group", isStreaming && "animate-pulse")}>
			<div className="max-w-4xl">
				{/* Markdown Content */}
				<div className="prose prose-slate dark:prose-invert max-w-none prose-p:my-2 prose-p:leading-7 prose-headings:font-semibold prose-h1:text-xl prose-h2:text-lg prose-h3:text-base prose-ul:my-2 prose-ol:my-2 prose-li:my-0.5 prose-pre:my-2 prose-pre:p-0 prose-pre:bg-transparent">
					<ReactMarkdown
						remarkPlugins={[remarkGfm]}
						components={{
							code({ className, children }) {
								const match = /language-(\w+)/.exec(
									className || "",
								);
								const isInline = !className;
								const content = String(children).replace(
									/\n$/,
									"",
								);

								if (!isInline && match) {
									return (
										<SyntaxHighlighter
											style={oneDark}
											language={match[1]}
											PreTag="div"
											className="rounded-md !my-2"
										>
											{content}
										</SyntaxHighlighter>
									);
								}

								// Code block without language
								if (!isInline) {
									return (
										<SyntaxHighlighter
											style={oneDark}
											language="text"
											PreTag="div"
											className="rounded-md !my-2"
										>
											{content}
										</SyntaxHighlighter>
									);
								}

								// Inline code
								return (
									<code className="bg-muted px-1.5 py-0.5 rounded text-sm font-mono">
										{children}
									</code>
								);
							},
							// Tighter spacing for chat context
							p: ({ children }) => (
								<p className="my-2 leading-7">{children}</p>
							),
							ul: ({ children }) => (
								<ul className="my-2 ml-4 list-disc space-y-1">
									{children}
								</ul>
							),
							ol: ({ children }) => (
								<ol className="my-2 ml-4 list-decimal space-y-1">
									{children}
								</ol>
							),
							li: ({ children }) => (
								<li className="leading-6">{children}</li>
							),
							// Links
							a: ({ href, children }) => (
								<a
									href={href}
									target="_blank"
									rel="noopener noreferrer"
									className="text-primary hover:underline"
								>
									{children}
								</a>
							),
							// Blockquotes
							blockquote: ({ children }) => (
								<blockquote className="border-l-2 border-muted-foreground/30 pl-4 my-2 italic text-muted-foreground">
									{children}
								</blockquote>
							),
							// Tables
							table: ({ children }) => (
								<div className="my-2 overflow-x-auto">
									<table className="min-w-full border-collapse border border-border">
										{children}
									</table>
								</div>
							),
							th: ({ children }) => (
								<th className="border border-border px-3 py-2 bg-muted font-semibold text-left">
									{children}
								</th>
							),
							td: ({ children }) => (
								<td className="border border-border px-3 py-2">
									{children}
								</td>
							),
							// Horizontal rule
							hr: () => <hr className="my-4 border-border" />,
						}}
					>
						{message.content || ""}
					</ReactMarkdown>
				</div>

				{/* Tool Calls - inline badges (hidden when cards are rendered separately) */}
				{!hideToolBadges && message.tool_calls && message.tool_calls.length > 0 && (
					<div className="mt-3 flex flex-wrap gap-2">
						{message.tool_calls.map((tc) => (
							<Badge
								key={tc.id}
								variant="secondary"
								className="cursor-pointer hover:bg-secondary/80 transition-colors"
								onClick={() => onToolCallClick?.(tc)}
							>
								<Wrench className="h-3 w-3 mr-1" />
								{tc.name}
							</Badge>
						))}
					</div>
				)}

				{/* Token Usage - shown on hover */}
				{(message.token_count_input || message.token_count_output) && (
					<div className="mt-2 flex gap-3 text-xs text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity">
						{message.token_count_input && (
							<span>In: {message.token_count_input}</span>
						)}
						{message.token_count_output && (
							<span>Out: {message.token_count_output}</span>
						)}
						{message.duration_ms && (
							<span>{message.duration_ms}ms</span>
						)}
					</div>
				)}
			</div>
		</div>
	);
}

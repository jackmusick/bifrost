import { useState, useEffect, useMemo } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ChevronRight, ChevronDown, FileText, Folder } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import ReactMarkdown from "react-markdown";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";

interface DocFile {
	name: string;
	path: string; // Internal path with .md extension
	slug: string; // URL-friendly slug without .md
	content?: string;
}

interface DocFolder {
	name: string;
	files: DocFile[];
	folders: DocFolder[];
	isOpen: boolean;
}

// This would ideally be generated at build time or loaded from an API
// For now, we'll maintain this structure manually
const docsStructure: DocFolder = {
	name: "Docs",
	isOpen: true,
	folders: [
		{
			name: "Troubleshooting",
			isOpen: true,
			files: [
				{
					name: "Workflow Engine Unavailable",
					path: "Troubleshooting/Workflow Engine Unavailable.md",
					slug: "troubleshooting/workflow-engine-unavailable",
				},
			],
			folders: [],
		},
	],
	files: [],
};

export function Docs() {
	const navigate = useNavigate();
	const params = useParams();
	const [structure, setStructure] = useState<DocFolder>(docsStructure);
	const [content, setContent] = useState<string>("");

	// Get document slug from URL params
	const docSlug = params["*"] || "";

	// Derive selectedDoc from docSlug and structure (no useEffect needed)
	const selectedDoc = useMemo(() => {
		if (!docSlug) return null;

		// Find the doc in the structure by slug
		const findDoc = (folder: DocFolder): DocFile | null => {
			for (const file of folder.files) {
				if (file.slug === docSlug) {
					return file;
				}
			}
			for (const subfolder of folder.folders) {
				const found = findDoc(subfolder);
				if (found) return found;
			}
			return null;
		};

		return findDoc(structure);
	}, [docSlug, structure]);

	useEffect(() => {
		if (selectedDoc?.path) {
			// Load the markdown file from public folder
			fetch(`/docs/${selectedDoc.path}`)
				.then((res) => {
					if (!res.ok) {
						throw new Error(`Failed to load: ${res.statusText}`);
					}
					return res.text();
				})
				.then((text) => setContent(text))
				.catch(() => {
					console.error("Failed to load documentation");
					setContent("# Error\n\nFailed to load documentation.");
				});
		}
	}, [selectedDoc]);

	const toggleFolder = (folderPath: string[]) => {
		const updateFolder = (folder: DocFolder, path: string[]): DocFolder => {
			if (path.length === 0) {
				return { ...folder, isOpen: !folder.isOpen };
			}

			const [current, ...rest] = path;
			return {
				...folder,
				folders: folder.folders.map((f) =>
					f.name === current ? updateFolder(f, rest) : f,
				),
			};
		};

		setStructure(updateFolder(structure, folderPath));
	};

	const renderFolder = (folder: DocFolder, path: string[] = []) => {
		return (
			<div key={folder.name}>
				<button
					onClick={() => toggleFolder(path)}
					className="flex items-center gap-2 w-full px-2 py-1 text-sm hover:bg-accent rounded-md transition-colors"
				>
					{folder.isOpen ? (
						<ChevronDown className="h-4 w-4" />
					) : (
						<ChevronRight className="h-4 w-4" />
					)}
					<Folder className="h-4 w-4" />
					<span>{folder.name}</span>
				</button>

				{folder.isOpen && (
					<div className="ml-4 mt-1 space-y-1">
						{folder.files.map((file) => (
							<button
								key={file.slug}
								onClick={() => navigate(`/docs/${file.slug}`)}
								className={cn(
									"flex items-center gap-2 w-full px-2 py-1 text-sm hover:bg-accent rounded-md transition-colors",
									selectedDoc?.slug === file.slug &&
										"bg-accent",
								)}
							>
								<FileText className="h-4 w-4 ml-4" />
								<span>{file.name}</span>
							</button>
						))}

						{folder.folders.map((subfolder) =>
							renderFolder(subfolder, [...path, folder.name]),
						)}
					</div>
				)}
			</div>
		);
	};

	return (
		<div className="flex h-[calc(100vh-8rem)] gap-4 overflow-hidden">
			{/* Sidebar with tree */}
			<Card className="w-80 flex-shrink-0 h-full flex flex-col">
				<CardContent className="p-4 flex-1 overflow-y-auto">
					<h2 className="text-lg font-semibold mb-4">
						Documentation
					</h2>
					<div className="space-y-1">
						{structure.folders.map((folder) =>
							renderFolder(folder, []),
						)}
						{structure.files.map((file) => (
							<button
								key={file.slug}
								onClick={() => navigate(`/docs/${file.slug}`)}
								className={cn(
									"flex items-center gap-2 w-full px-2 py-1 text-sm hover:bg-accent rounded-md transition-colors",
									selectedDoc?.slug === file.slug &&
										"bg-accent",
								)}
							>
								<FileText className="h-4 w-4" />
								<span>{file.name}</span>
							</button>
						))}
					</div>
				</CardContent>
			</Card>

			{/* Content area */}
			<Card className="flex-1 h-full flex flex-col overflow-hidden">
				<CardContent className="p-6 flex-1 overflow-y-auto">
					{selectedDoc ? (
						<div className="prose prose-slate dark:prose-invert max-w-none prose-headings:font-bold prose-h1:text-3xl prose-h2:text-2xl prose-h2:mt-8 prose-h3:text-xl prose-p:my-4 prose-ul:my-4 prose-ol:my-4 prose-li:my-2">
							<ReactMarkdown
								components={{
									code({ className, children }) {
										const match = /language-(\w+)/.exec(
											className || "",
										);
										const isInline = !className;
										return !isInline && match ? (
											<SyntaxHighlighter
												style={oneDark}
												language={match[1]}
												PreTag="div"
												className="rounded-md my-4"
											>
												{String(children).replace(
													/\n$/,
													"",
												)}
											</SyntaxHighlighter>
										) : (
											<code className="bg-muted px-1.5 py-0.5 rounded text-sm">
												{children}
											</code>
										);
									},
									h1: ({ ...props }) => (
										<h1
											className="text-3xl font-bold mb-4 mt-8"
											{...props}
										/>
									),
									h2: ({ ...props }) => (
										<h2
											className="text-2xl font-bold mb-3 mt-6"
											{...props}
										/>
									),
									h3: ({ ...props }) => (
										<h3
											className="text-xl font-semibold mb-2 mt-4"
											{...props}
										/>
									),
									h4: ({ ...props }) => (
										<h4
											className="text-lg font-semibold mb-2 mt-3"
											{...props}
										/>
									),
									p: ({ ...props }) => (
										<p
											className="my-3 leading-7"
											{...props}
										/>
									),
									ul: ({ ...props }) => (
										<ul
											className="my-4 ml-6 list-disc space-y-2"
											{...props}
										/>
									),
									ol: ({ ...props }) => (
										<ol
											className="my-4 ml-6 list-decimal space-y-2"
											{...props}
										/>
									),
									li: ({ ...props }) => (
										<li className="leading-7" {...props} />
									),
									strong: ({ ...props }) => (
										<strong
											className="font-semibold"
											{...props}
										/>
									),
								}}
							>
								{content}
							</ReactMarkdown>
						</div>
					) : (
						<div className="flex items-center justify-center h-full text-muted-foreground">
							<div className="text-center">
								<FileText className="h-12 w-12 mx-auto mb-4 opacity-50" />
								<p>Select a document to view</p>
							</div>
						</div>
					)}
				</CardContent>
			</Card>
		</div>
	);
}

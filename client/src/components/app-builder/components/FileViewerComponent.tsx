/**
 * FileViewer Component for App Builder
 *
 * Displays files with support for inline viewing, modal preview, or download.
 * Supports images, PDFs, and other file types.
 */

import { useState, useMemo } from "react";
import {
	Download,
	ExternalLink,
	File,
	FileImage,
	FileText,
	FileVideo,
	FileAudio,
	type LucideIcon,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
	Dialog,
	DialogContent,
	DialogHeader,
	DialogTitle,
	DialogTrigger,
} from "@/components/ui/dialog";
import type { FileViewerComponentProps } from "@/lib/app-builder-types";
import type { RegisteredComponentProps } from "../ComponentRegistry";
import { evaluateExpression } from "@/lib/expression-parser";

type FileCategory = "image" | "pdf" | "video" | "audio" | "text" | "other";

/**
 * Detect MIME type from file extension
 */
function detectMimeType(url: string, providedMimeType?: string): string {
	if (providedMimeType) return providedMimeType;

	const extension = url.split(".").pop()?.toLowerCase() || "";
	const mimeTypes: Record<string, string> = {
		// Images
		jpg: "image/jpeg",
		jpeg: "image/jpeg",
		png: "image/png",
		gif: "image/gif",
		webp: "image/webp",
		svg: "image/svg+xml",
		ico: "image/x-icon",
		bmp: "image/bmp",
		// Documents
		pdf: "application/pdf",
		// Text
		txt: "text/plain",
		csv: "text/csv",
		json: "application/json",
		xml: "application/xml",
		html: "text/html",
		md: "text/markdown",
		// Video
		mp4: "video/mp4",
		webm: "video/webm",
		ogg: "video/ogg",
		// Audio
		mp3: "audio/mpeg",
		wav: "audio/wav",
		m4a: "audio/mp4",
	};

	return mimeTypes[extension] || "application/octet-stream";
}

/**
 * Get file type category
 */
function getFileCategory(mimeType: string): FileCategory {
	if (mimeType.startsWith("image/")) return "image";
	if (mimeType === "application/pdf") return "pdf";
	if (mimeType.startsWith("video/")) return "video";
	if (mimeType.startsWith("audio/")) return "audio";
	if (
		mimeType.startsWith("text/") ||
		mimeType === "application/json" ||
		mimeType === "application/xml"
	)
		return "text";
	return "other";
}

/**
 * Icon mapping by category - defined as constant to avoid component recreation
 */
const FILE_ICONS: Record<FileCategory, LucideIcon> = {
	image: FileImage,
	pdf: FileText,
	text: FileText,
	video: FileVideo,
	audio: FileAudio,
	other: File,
};

/**
 * Extract filename from URL or use provided name
 */
function getFileName(url: string, providedName?: string): string {
	if (providedName) return providedName;
	const parts = url.split("/");
	const filename = parts[parts.length - 1] || "file";
	// Remove query string if present
	return filename.split("?")[0];
}

interface FileContentProps {
	src: string;
	mimeType: string;
	category: FileCategory;
	maxWidth?: number | string;
	maxHeight?: number | string;
	className?: string;
}

/**
 * Render file content based on type
 */
function FileContent({
	src,
	mimeType,
	category,
	maxWidth,
	maxHeight,
	className,
}: FileContentProps) {
	const style: React.CSSProperties = {};

	if (maxWidth) {
		style.maxWidth =
			typeof maxWidth === "number" ? `${maxWidth}px` : maxWidth;
	}
	if (maxHeight) {
		style.maxHeight =
			typeof maxHeight === "number" ? `${maxHeight}px` : maxHeight;
	}

	switch (category) {
		case "image":
			return (
				<img
					src={src}
					alt="File preview"
					style={style}
					className={cn("object-contain", className)}
				/>
			);

		case "pdf":
			return (
				<iframe
					src={src}
					title="PDF viewer"
					style={{
						...style,
						width: style.maxWidth || "100%",
						height: style.maxHeight || "600px",
					}}
					className={cn("border-0", className)}
				/>
			);

		case "video":
			return (
				<video
					src={src}
					controls
					style={style}
					className={cn("max-w-full", className)}
				>
					Your browser does not support video playback.
				</video>
			);

		case "audio":
			return (
				<audio
					src={src}
					controls
					className={cn("w-full max-w-md", className)}
				>
					Your browser does not support audio playback.
				</audio>
			);

		case "text":
			return (
				<iframe
					src={src}
					title="Text viewer"
					style={{
						...style,
						width: style.maxWidth || "100%",
						height: style.maxHeight || "400px",
					}}
					className={cn("border rounded bg-muted", className)}
				/>
			);

		default:
			// For unsupported types, show a file icon with download option
			return (
				<div
					className={cn(
						"flex flex-col items-center gap-4 p-8 border rounded-lg bg-muted/50",
						className,
					)}
				>
					<File className="h-16 w-16 text-muted-foreground" />
					<p className="text-sm text-muted-foreground">
						Preview not available for {mimeType}
					</p>
				</div>
			);
	}
}

/**
 * Icon component that renders based on category
 */
function FileIcon({
	category,
	className,
}: {
	category: FileCategory;
	className?: string;
}) {
	const IconComponent = FILE_ICONS[category];
	return <IconComponent className={className} />;
}

export function FileViewerComponent({
	component,
	context,
}: RegisteredComponentProps) {
	const { props } = component as FileViewerComponentProps;
	const [isModalOpen, setIsModalOpen] = useState(false);

	// Evaluate expressions
	const src = String(evaluateExpression(props.src, context) ?? "");
	const fileName = props.fileName
		? String(evaluateExpression(props.fileName, context) ?? "")
		: undefined;

	// Detect file type
	const mimeType = useMemo(
		() => detectMimeType(src, props.mimeType),
		[src, props.mimeType],
	);
	const category = useMemo(() => getFileCategory(mimeType), [mimeType]);
	const displayName = useMemo(
		() => getFileName(src, fileName),
		[src, fileName],
	);

	const displayMode = props.displayMode || "inline";
	const showDownloadButton =
		props.showDownloadButton ?? displayMode !== "download";

	// Download handler
	const handleDownload = () => {
		const link = document.createElement("a");
		link.href = src;
		link.download = displayName;
		link.target = "_blank";
		link.rel = "noopener noreferrer";
		document.body.appendChild(link);
		link.click();
		document.body.removeChild(link);
	};

	// Download mode - just show a download button/link
	if (displayMode === "download") {
		return (
			<Button
				variant="outline"
				onClick={handleDownload}
				className={cn("gap-2", props.className)}
			>
				<FileIcon category={category} className="h-4 w-4" />
				{props.downloadLabel || displayName}
				<Download className="h-4 w-4" />
			</Button>
		);
	}

	// Modal mode - show a button that opens the file in a modal
	if (displayMode === "modal") {
		return (
			<Dialog open={isModalOpen} onOpenChange={setIsModalOpen}>
				<DialogTrigger asChild>
					<Button
						variant="outline"
						className={cn("gap-2", props.className)}
					>
						<FileIcon category={category} className="h-4 w-4" />
						{props.downloadLabel || displayName}
						<ExternalLink className="h-4 w-4" />
					</Button>
				</DialogTrigger>
				<DialogContent className="max-w-4xl max-h-[90vh] overflow-auto">
					<DialogHeader>
						<DialogTitle className="flex items-center gap-2">
							<FileIcon category={category} className="h-5 w-5" />
							{displayName}
						</DialogTitle>
					</DialogHeader>
					<div className="mt-4">
						<FileContent
							src={src}
							mimeType={mimeType}
							category={category}
							maxWidth="100%"
							maxHeight="70vh"
						/>
					</div>
					{showDownloadButton && (
						<div className="mt-4 flex justify-end">
							<Button
								variant="outline"
								onClick={handleDownload}
								className="gap-2"
							>
								<Download className="h-4 w-4" />
								Download
							</Button>
						</div>
					)}
				</DialogContent>
			</Dialog>
		);
	}

	// Inline mode - embed the file directly
	return (
		<div className={cn("relative", props.className)}>
			<FileContent
				src={src}
				mimeType={mimeType}
				category={category}
				maxWidth={props.maxWidth}
				maxHeight={props.maxHeight}
			/>
			{showDownloadButton && (
				<div className="mt-2 flex justify-end">
					<Button
						variant="ghost"
						size="sm"
						onClick={handleDownload}
						className="gap-2"
					>
						<Download className="h-4 w-4" />
						Download
					</Button>
				</div>
			)}
		</div>
	);
}

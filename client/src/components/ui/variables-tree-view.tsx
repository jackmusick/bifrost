import { ChevronRight, ChevronDown, Copy, Check } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

interface VariablesTreeViewProps {
	data: Record<string, unknown>;
}

/**
 * VS Code-style variables tree view
 * Displays variables in a clean, YAML-like format similar to VS Code debugger
 */
export function VariablesTreeView({ data }: VariablesTreeViewProps) {
	// Debug: log the data to see what we're receiving

	return (
		<div className="font-mono text-xs space-y-0.5 overflow-x-auto min-w-0">
			{Object.entries(data).map(([key, value]) => {
				return (
					<VariableItem
						key={key}
						name={key}
						value={value}
						depth={0}
					/>
				);
			})}
		</div>
	);
}

interface VariableItemProps {
	name: string;
	value: unknown;
	depth: number;
}

function VariableItem({ name, value, depth }: VariableItemProps) {
	const [isExpanded, setIsExpanded] = useState(false);
	const [copied, setCopied] = useState(false);
	const [isHovering, setIsHovering] = useState(false);
	const indent = depth * 12; // 12px per level

	// Determine if value is expandable
	const isObject =
		value !== null && typeof value === "object" && !Array.isArray(value);
	const isArray = Array.isArray(value);
	const isExpandable = isObject || isArray;
	const isPrimitive =
		!isObject && !isArray && value !== null && value !== undefined;

	// Get display value
	const getDisplayValue = () => {
		if (value === null) return "null";
		if (value === undefined) return "undefined";
		if (typeof value === "string") {
			// Show empty string explicitly
			if (value === "") return '""';
			return `"${value}"`;
		}
		if (typeof value === "number") return String(value);
		if (typeof value === "boolean") return String(value);
		if (isArray) return `Array(${(value as unknown[]).length})`;
		if (isObject) return `{...}`;
		return String(value);
	};

	// Copy value to clipboard
	const handleCopy = async (e: React.MouseEvent) => {
		e.stopPropagation();
		try {
			let textToCopy: string;
			if (isPrimitive) {
				// For primitives, copy the raw value
				textToCopy = String(value);
			} else {
				// For objects/arrays, copy as JSON
				textToCopy = JSON.stringify(value, null, 2);
			}
			await navigator.clipboard.writeText(textToCopy);
			setCopied(true);
			toast.success("Copied to clipboard");
			setTimeout(() => setCopied(false), 2000);
		} catch {
			toast.error("Failed to copy to clipboard");
		}
	};

	return (
		<div>
			<div
				className="hover:bg-muted/50 py-0.5 px-1 rounded group relative"
				style={{ paddingLeft: `${indent + 4}px` }}
				onMouseEnter={() => setIsHovering(true)}
				onMouseLeave={() => setIsHovering(false)}
			>
				<div className="flex items-center pr-8">
					{/* Expand/collapse icon */}
					<div
						className="cursor-pointer flex items-center"
						onClick={() =>
							isExpandable && setIsExpanded(!isExpanded)
						}
					>
						{isExpandable ? (
							<div className="w-4 h-4 flex items-center justify-center mr-1 flex-shrink-0">
								{isExpanded ? (
									<ChevronDown className="w-3 h-3 text-muted-foreground" />
								) : (
									<ChevronRight className="w-3 h-3 text-muted-foreground" />
								)}
							</div>
						) : (
							<div className="w-4 mr-1 flex-shrink-0" />
						)}

						{/* Variable name */}
						<span className="text-primary mr-2 flex-shrink-0">
							{name}:
						</span>

						{/* Variable value */}
						{(!isExpanded || !isExpandable) && (
							<span className="text-foreground opacity-80 whitespace-nowrap">
								{getDisplayValue()}
							</span>
						)}
					</div>

					{/* Copy button - shown on hover, positioned at the right edge */}
					{isHovering && (
						<button
							onClick={handleCopy}
							className="absolute right-1 p-0.5 hover:bg-muted rounded opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0 bg-background"
							title="Copy value"
						>
							{copied ? (
								<Check className="w-3 h-3 text-green-500" />
							) : (
								<Copy className="w-3 h-3 text-muted-foreground" />
							)}
						</button>
					)}
				</div>
			</div>

			{/* Expanded children */}
			{isExpanded && isExpandable && (
				<div>
					{isArray
						? // Array items
							(value as unknown[]).map((item, index) => (
								<VariableItem
									key={index}
									name={`[${index}]`}
									value={item}
									depth={depth + 1}
								/>
							))
						: // Object properties
							Object.entries(
								value as Record<string, unknown>,
							).map(([key, val]) => (
								<VariableItem
									key={key}
									name={key}
									value={val}
									depth={depth + 1}
								/>
							))}
				</div>
			)}
		</div>
	);
}

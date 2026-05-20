import { useRef, useState } from "react";
import { toast } from "sonner";
import { EntityLogo } from "@/components/EntityLogo";

export type AgentLogoDropZoneProps = {
	agentId: string;
	agentName: string;
	onUploaded: () => void;
	size?: number;
	className?: string;
};

function initials(name: string): string {
	return name
		.split(/\s+/)
		.filter(Boolean)
		.slice(0, 2)
		.map((p) => p[0]?.toUpperCase() ?? "")
		.join("");
}

export function AgentLogoDropZone({
	agentId,
	agentName,
	onUploaded,
	size = 56,
	className,
}: AgentLogoDropZoneProps) {
	const inputRef = useRef<HTMLInputElement>(null);
	const [dragOver, setDragOver] = useState(false);
	const [cacheKey, setCacheKey] = useState(() => String(Date.now()));
	const [busy, setBusy] = useState(false);

	async function upload(file: File) {
		setBusy(true);
		const fd = new FormData();
		fd.append("file", file);
		try {
			const resp = await fetch(`/api/agents/${agentId}/logo`, {
				method: "POST",
				body: fd,
			});
			if (!resp.ok) throw new Error(`Upload failed (${resp.status})`);
			setCacheKey(String(Date.now()));
			onUploaded();
			toast.success("Logo updated");
		} catch (err) {
			toast.error((err as Error).message);
		} finally {
			setBusy(false);
		}
	}

	async function remove() {
		setBusy(true);
		try {
			const resp = await fetch(`/api/agents/${agentId}/logo`, {
				method: "DELETE",
			});
			if (!resp.ok && resp.status !== 204) {
				throw new Error(`Remove failed (${resp.status})`);
			}
			setCacheKey(String(Date.now()));
			onUploaded();
			toast.success("Logo removed");
		} catch (err) {
			toast.error((err as Error).message);
		} finally {
			setBusy(false);
		}
	}

	return (
		<div
			data-testid="agent-logo-zone"
			role="button"
			tabIndex={0}
			onClick={() => inputRef.current?.click()}
			onKeyDown={(e) => {
				if (e.key === "Enter" || e.key === " ") inputRef.current?.click();
			}}
			onDragOver={(e) => {
				e.preventDefault();
				setDragOver(true);
			}}
			onDragLeave={() => setDragOver(false)}
			onDrop={(e) => {
				e.preventDefault();
				setDragOver(false);
				const f = e.dataTransfer.files[0];
				if (f) void upload(f);
			}}
			onContextMenu={(e) => {
				e.preventDefault();
				void remove();
			}}
			style={{ width: size, height: size }}
			className={[
				"rounded-md border-2 flex items-center justify-center overflow-hidden cursor-pointer transition-colors shrink-0",
				dragOver
					? "border-primary border-dashed bg-primary/10"
					: "border-transparent bg-muted/40",
				busy ? "opacity-50" : "",
				className ?? "",
			]
				.filter(Boolean)
				.join(" ")}
			aria-label="Upload agent logo (drop or click); right-click to remove"
		>
			<EntityLogo
				entityType="agent"
				entityId={agentId}
				fallback={
					<span className="text-sm font-medium text-muted-foreground">
						{initials(agentName) || "?"}
					</span>
				}
				size={size}
				cacheKey={cacheKey}
				className="h-full w-full object-cover"
			/>
			<input
				ref={inputRef}
				type="file"
				accept="image/png,image/jpeg,image/svg+xml"
				className="hidden"
				onChange={(e) => {
					const f = e.target.files?.[0];
					if (f) void upload(f);
					e.target.value = "";
				}}
			/>
		</div>
	);
}

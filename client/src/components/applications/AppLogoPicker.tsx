import { useRef, useState } from "react";
import { Image as ImageIcon, X } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { EntityLogo } from "@/components/EntityLogo";

export type AppLogoPickerProps = {
	applicationId: string;
	onUploaded: () => void;
	onRemoved: () => void;
};

export function AppLogoPicker({
	applicationId,
	onUploaded,
	onRemoved,
}: AppLogoPickerProps) {
	const inputRef = useRef<HTMLInputElement>(null);
	const [cacheKey, setCacheKey] = useState(() => String(Date.now()));
	const [busy, setBusy] = useState(false);

	async function handleFile(file: File) {
		setBusy(true);
		const fd = new FormData();
		fd.append("file", file);
		try {
			const resp = await fetch(`/api/applications/${applicationId}/logo`, {
				method: "POST",
				body: fd,
			});
			if (!resp.ok) {
				const txt = await resp.text();
				throw new Error(txt || `Upload failed (${resp.status})`);
			}
			setCacheKey(String(Date.now()));
			onUploaded();
			toast.success("Logo updated");
		} catch (err) {
			toast.error((err as Error).message);
		} finally {
			setBusy(false);
		}
	}

	async function handleRemove() {
		setBusy(true);
		try {
			const resp = await fetch(`/api/applications/${applicationId}/logo`, {
				method: "DELETE",
			});
			if (!resp.ok && resp.status !== 204) {
				throw new Error(`Remove failed (${resp.status})`);
			}
			setCacheKey(String(Date.now()));
			onRemoved();
			toast.success("Logo removed");
		} catch (err) {
			toast.error((err as Error).message);
		} finally {
			setBusy(false);
		}
	}

	return (
		<div className="flex items-center gap-3">
			<div className="h-10 w-10 rounded border bg-muted/40 flex items-center justify-center overflow-hidden">
				<EntityLogo
					entityType="app"
					entityId={applicationId}
					fallback={<ImageIcon className="h-5 w-5 text-muted-foreground" />}
					size={40}
					cacheKey={cacheKey}
				/>
			</div>
			<input
				ref={inputRef}
				type="file"
				accept="image/png,image/jpeg,image/svg+xml"
				aria-label="Upload logo"
				className="hidden"
				onChange={(e) => {
					const f = e.target.files?.[0];
					if (f) void handleFile(f);
					e.target.value = "";
				}}
			/>
			<Button
				type="button"
				variant="outline"
				size="sm"
				disabled={busy}
				onClick={() => inputRef.current?.click()}
			>
				Choose file
			</Button>
			<Button
				type="button"
				variant="ghost"
				size="sm"
				disabled={busy}
				onClick={handleRemove}
			>
				<X className="h-4 w-4 mr-1" /> Remove
			</Button>
		</div>
	);
}

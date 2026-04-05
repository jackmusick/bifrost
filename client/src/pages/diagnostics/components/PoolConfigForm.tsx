import { useState } from "react";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
	Dialog,
	DialogContent,
	DialogDescription,
	DialogFooter,
	DialogHeader,
	DialogTitle,
} from "@/components/ui/dialog";
import { toast } from "sonner";

interface PoolConfigFormProps {
	currentMin: number;
	currentMax: number;
	open: boolean;
	onOpenChange: (open: boolean) => void;
}

export function PoolConfigForm({
	currentMin,
	currentMax,
	open,
	onOpenChange,
}: PoolConfigFormProps) {
	const [minWorkers, setMinWorkers] = useState(currentMin);
	const [maxWorkers, setMaxWorkers] = useState(currentMax);
	const [error, setError] = useState<string | null>(null);

	// Reset form when dialog opens (syncs with latest prop values)
	const handleOpenChange = (newOpen: boolean) => {
		if (newOpen) {
			setMinWorkers(currentMin);
			setMaxWorkers(currentMax);
			setError(null);
		}
		onOpenChange(newOpen);
	};

	const validate = (): boolean => {
		if (minWorkers < 2) {
			setError("Minimum workers must be at least 2");
			return false;
		}
		if (minWorkers > maxWorkers) {
			setError("Minimum workers cannot exceed maximum workers");
			return false;
		}
		setError(null);
		return true;
	};

	const [isSaving, setIsSaving] = useState(false);

	const handleSave = async () => {
		if (!validate()) return;

		setIsSaving(true);
		try {
			// TODO(Task 8): re-implement with updated config endpoint
			toast.info("Pool configuration (coming soon)");
			onOpenChange(false);
		} finally {
			setIsSaving(false);
		}
	};

	const hasChanges = minWorkers !== currentMin || maxWorkers !== currentMax;

	return (
		<Dialog open={open} onOpenChange={handleOpenChange}>
			<DialogContent className="sm:max-w-[425px]">
				<DialogHeader>
					<DialogTitle>Global Pool Configuration</DialogTitle>
					<DialogDescription>
						Configure the minimum and maximum worker processes for all pools.
						Changes apply to all connected workers.
					</DialogDescription>
				</DialogHeader>
				<div className="grid gap-4 py-4">
					<div className="grid grid-cols-4 items-center gap-4">
						<Label htmlFor="min-workers" className="text-right">
							Min Workers
						</Label>
						<Input
							id="min-workers"
							type="number"
							min={2}
							value={minWorkers}
							onChange={(e) => setMinWorkers(Number(e.target.value))}
							className="col-span-3"
						/>
					</div>
					<div className="grid grid-cols-4 items-center gap-4">
						<Label htmlFor="max-workers" className="text-right">
							Max Workers
						</Label>
						<Input
							id="max-workers"
							type="number"
							min={2}
							value={maxWorkers}
							onChange={(e) => setMaxWorkers(Number(e.target.value))}
							className="col-span-3"
						/>
					</div>
					{error && (
						<p className="text-sm text-destructive text-center">{error}</p>
					)}
					<p className="text-sm text-muted-foreground">
						Minimum workers are kept warm and ready. Maximum limits scaling
						under load. These settings apply globally to all worker pools.
					</p>
				</div>
				<DialogFooter>
					<Button variant="outline" onClick={() => onOpenChange(false)}>
						Cancel
					</Button>
					<Button
						onClick={handleSave}
						disabled={isSaving || !hasChanges}
					>
						{isSaving && (
							<Loader2 className="mr-2 h-4 w-4 animate-spin" />
						)}
						Save Changes
					</Button>
				</DialogFooter>
			</DialogContent>
		</Dialog>
	);
}

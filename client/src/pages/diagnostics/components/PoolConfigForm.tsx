import { useState, useEffect } from "react";
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
import { useUpdatePoolConfig } from "@/services/workers";
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

	const updateConfig = useUpdatePoolConfig();

	// Sync form state when currentMin/currentMax changes (e.g., from config fetch)
	useEffect(() => {
		setMinWorkers(currentMin);
		setMaxWorkers(currentMax);
	}, [currentMin, currentMax]);

	// Reset form when dialog opens
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

	const handleSave = async () => {
		if (!validate()) return;

		try {
			const result = await updateConfig.mutateAsync({
				min_workers: minWorkers,
				max_workers: maxWorkers,
			});

			toast.success("Pool configuration updated", {
				description: `Workers: ${result.new_min}-${result.new_max}`,
			});

			onOpenChange(false);
		} catch (err) {
			const message = err instanceof Error ? err.message : "Unknown error";
			toast.error("Failed to update configuration", { description: message });
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
						disabled={updateConfig.isPending || !hasChanges}
					>
						{updateConfig.isPending && (
							<Loader2 className="mr-2 h-4 w-4 animate-spin" />
						)}
						Save Changes
					</Button>
				</DialogFooter>
			</DialogContent>
		</Dialog>
	);
}

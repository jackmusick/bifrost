import { useState, useEffect, useCallback } from "react";
import {
	Card,
	CardContent,
	CardDescription,
	CardHeader,
	CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
	AlertDialog,
	AlertDialogAction,
	AlertDialogCancel,
	AlertDialogContent,
	AlertDialogDescription,
	AlertDialogFooter,
	AlertDialogHeader,
	AlertDialogTitle,
	AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { toast } from "sonner";
import { Loader2, Upload, Palette, RotateCcw } from "lucide-react";
import {
	updateBranding,
	uploadLogo,
	resetLogo,
	resetColor,
	resetAllBranding,
	getBranding,
} from "@/hooks/useBranding";
import { applyBrandingTheme, type BrandingSettings } from "@/lib/branding";
import { useOrgScope } from "@/contexts/OrgScopeContext";
import type { components } from "@/lib/v1";

interface BrandingProps {
	onActionsChange?: (actions: React.ReactNode) => void;
}

export function Branding({ onActionsChange }: BrandingProps) {
	const { refreshBranding } = useOrgScope();
	const [branding, setBranding] = useState<components["schemas"]["BrandingSettings"] | null>(
		null,
	);
	const [loading, setLoading] = useState(true);
	const [saving, setSaving] = useState(false);
	const [uploading, setUploading] = useState<"square" | "rectangle" | null>(
		null,
	);
	const [resetting, setResetting] = useState<
		"square" | "rectangle" | "color" | "all" | null
	>(null);
	const [resetDialogOpen, setResetDialogOpen] = useState(false);
	const [primaryColor, setPrimaryColor] = useState("#0066CC");

	// Drag states
	const [dragActiveSquare, setDragActiveSquare] = useState(false);
	const [dragActiveRectangle, setDragActiveRectangle] = useState(false);

	// Load current branding
	useEffect(() => {
		async function loadBranding() {
			try {
				const data = await getBranding();
				if (data) {
					setBranding(data);
					if (data.primary_color) {
						setPrimaryColor(data.primary_color);
					}
				}
			} catch {
				toast.error("Failed to load branding settings");
			} finally {
				setLoading(false);
			}
		}

		loadBranding();
	}, []);

	// Update primary color
	const handleColorUpdate = async () => {
		setSaving(true);
		try {
			const updated = await updateBranding({
				primary_color: primaryColor,
			});
			setBranding(updated);
			applyBrandingTheme(updated as BrandingSettings);
			refreshBranding();

			toast.success("Branding updated", {
				description: "Primary color has been updated successfully",
			});
		} catch (err) {
			toast.error("Error", {
				description:
					err instanceof Error
						? err.message
						: "Failed to update branding",
			});
		} finally {
			setSaving(false);
		}
	};

	// Handle file upload
	const handleLogoUpload = useCallback(
		async (type: "square" | "rectangle", file: File) => {
			// Validate file type
			if (!file.type.startsWith("image/")) {
				toast.error("Invalid file type", {
					description:
						"Please upload an image file (PNG, JPG, or SVG)",
				});
				return;
			}

			// Validate file size (5MB)
			if (file.size > 5 * 1024 * 1024) {
				toast.error("File too large", {
					description: "Please upload an image smaller than 5MB",
				});
				return;
			}

			setUploading(type);
			try {
				await uploadLogo(type, file);

				// Reload branding to get updated logo URL
				const updated = await getBranding();
				if (updated) {
					setBranding(updated);
					applyBrandingTheme(updated as BrandingSettings);
					refreshBranding();
				}

				toast.success("Logo uploaded", {
					description: `${
						type === "square" ? "Square" : "Rectangle"
					} logo has been updated successfully`,
				});
			} catch (err) {
				toast.error("Error", {
					description:
						err instanceof Error
							? err.message
							: "Failed to upload logo",
				});
			} finally {
				setUploading(null);
			}
		},
		[refreshBranding],
	);

	// Drag and drop handlers
	const handleDrag = useCallback(
		(e: React.DragEvent, type: "square" | "rectangle") => {
			e.preventDefault();
			e.stopPropagation();
			if (e.type === "dragenter" || e.type === "dragover") {
				if (type === "square") setDragActiveSquare(true);
				else setDragActiveRectangle(true);
			} else if (e.type === "dragleave") {
				if (type === "square") setDragActiveSquare(false);
				else setDragActiveRectangle(false);
			}
		},
		[],
	);

	const handleDrop = useCallback(
		(e: React.DragEvent, type: "square" | "rectangle") => {
			e.preventDefault();
			e.stopPropagation();
			if (type === "square") setDragActiveSquare(false);
			else setDragActiveRectangle(false);

			if (e.dataTransfer.files && e.dataTransfer.files[0]) {
				handleLogoUpload(type, e.dataTransfer.files[0]);
			}
		},
		[handleLogoUpload],
	);

	const handleFileInput = useCallback(
		(
			e: React.ChangeEvent<HTMLInputElement>,
			type: "square" | "rectangle",
		) => {
			const file = e.target.files?.[0];
			if (file) {
				handleLogoUpload(type, file);
			}
		},
		[handleLogoUpload],
	);

	// Reset handlers
	const handleResetLogo = useCallback(
		async (type: "square" | "rectangle") => {
			setResetting(type);
			try {
				const updated = await resetLogo(type);
				setBranding(updated);
				applyBrandingTheme(updated as BrandingSettings);
				refreshBranding();

				toast.success("Logo reset", {
					description: `${
						type === "square" ? "Square" : "Rectangle"
					} logo has been reset to default`,
				});
			} catch (err) {
				toast.error("Error", {
					description:
						err instanceof Error
							? err.message
							: "Failed to reset logo",
				});
			} finally {
				setResetting(null);
			}
		},
		[refreshBranding],
	);

	const handleResetColor = useCallback(async () => {
		setResetting("color");
		try {
			const updated = await resetColor();
			setBranding(updated);
			setPrimaryColor(updated.primary_color || "#0066CC");
			applyBrandingTheme(updated as BrandingSettings);
			refreshBranding();

			toast.success("Color reset", {
				description: "Primary color has been reset to default",
			});
		} catch (err) {
			toast.error("Error", {
				description:
					err instanceof Error
						? err.message
						: "Failed to reset color",
			});
		} finally {
			setResetting(null);
		}
	}, [refreshBranding]);

	const handleResetAll = useCallback(async () => {
		setResetting("all");
		try {
			const updated = await resetAllBranding();
			setBranding(updated);
			setPrimaryColor(updated.primary_color || "#0066CC");
			applyBrandingTheme(updated as BrandingSettings);
			refreshBranding();

			toast.success("Branding reset", {
				description: "All branding has been reset to defaults",
			});
			setResetDialogOpen(false);
		} catch (err) {
			toast.error("Error", {
				description:
					err instanceof Error
						? err.message
						: "Failed to reset branding",
			});
		} finally {
			setResetting(null);
		}
	}, [refreshBranding]);

	// Set tab actions
	useEffect(() => {
		if (onActionsChange) {
			onActionsChange(
				<AlertDialog
					open={resetDialogOpen}
					onOpenChange={setResetDialogOpen}
				>
					<AlertDialogTrigger asChild>
						<Button
							variant="outline"
							size="sm"
							disabled={resetting === "all"}
						>
							{resetting === "all" ? (
								<Loader2 className="mr-2 h-4 w-4 animate-spin" />
							) : (
								<RotateCcw className="mr-2 h-4 w-4" />
							)}
							Reset Branding
						</Button>
					</AlertDialogTrigger>
					<AlertDialogContent>
						<AlertDialogHeader>
							<AlertDialogTitle>
								Reset all branding?
							</AlertDialogTitle>
							<AlertDialogDescription>
								This will reset all branding settings (logos and
								primary color) back to platform defaults. This
								action cannot be undone.
							</AlertDialogDescription>
						</AlertDialogHeader>
						<AlertDialogFooter>
							<AlertDialogCancel disabled={resetting === "all"}>
								Cancel
							</AlertDialogCancel>
							<AlertDialogAction
								onClick={handleResetAll}
								disabled={resetting === "all"}
								className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
							>
								{resetting === "all" ? (
									<Loader2 className="mr-2 h-4 w-4 animate-spin" />
								) : null}
								Reset All
							</AlertDialogAction>
						</AlertDialogFooter>
					</AlertDialogContent>
				</AlertDialog>,
			);
		}

		// Cleanup: remove actions when component unmounts
		return () => {
			if (onActionsChange) {
				onActionsChange(null);
			}
		};
	}, [onActionsChange, resetting, resetDialogOpen, handleResetAll]);

	if (loading) {
		return (
			<div className="flex items-center justify-center h-64">
				<Loader2 className="h-8 w-8 animate-spin" />
			</div>
		);
	}

	return (
		<div className="space-y-6">
			{/* Primary Color */}
			<Card>
				<CardHeader>
					<CardTitle className="flex items-center gap-2">
						<Palette className="h-5 w-5" />
						Primary Color
					</CardTitle>
					<CardDescription>
						Choose your organization's primary brand color
					</CardDescription>
				</CardHeader>
				<CardContent className="space-y-4">
					<div className="flex items-center gap-4">
						<div>
							<Label htmlFor="primaryColor">Color (Hex)</Label>
							<Input
								id="primaryColor"
								type="text"
								value={primaryColor}
								onChange={(e) =>
									setPrimaryColor(e.target.value)
								}
								placeholder="#0066CC"
								className="w-32 font-mono"
							/>
						</div>
						<div>
							<Label>Preview</Label>
							<div
								className="h-10 w-20 rounded border"
								style={{ backgroundColor: primaryColor }}
							/>
						</div>
					</div>
					<div className="flex gap-2">
						<Button
							onClick={handleColorUpdate}
							disabled={saving || resetting === "color"}
							variant="default"
						>
							{saving ? (
								<Loader2 className="mr-2 h-4 w-4 animate-spin" />
							) : null}
							Update Color
						</Button>
						<Button
							onClick={handleResetColor}
							disabled={saving || resetting === "color"}
							variant="outline"
							size="icon"
							title="Reset to default color"
						>
							{resetting === "color" ? (
								<Loader2 className="h-4 w-4 animate-spin" />
							) : (
								<RotateCcw className="h-4 w-4" />
							)}
						</Button>
					</div>
				</CardContent>
			</Card>

			{/* Logos */}
			<Card>
				<CardHeader>
					<CardTitle className="flex items-center gap-2">
						<Upload className="h-5 w-5" />
						Brand Logos
					</CardTitle>
					<CardDescription>
						Upload logos for your organization (PNG, JPG, or SVG,
						max 5MB)
					</CardDescription>
				</CardHeader>
				<CardContent>
					<div className="grid grid-cols-1 md:grid-cols-2 gap-6">
						{/* Square Logo */}
						<div className="space-y-3">
							<div className="flex items-center justify-between">
								<Label>Square Logo (1:1 ratio)</Label>
								{branding?.square_logo_url && (
									<Button
										size="sm"
										variant="ghost"
										onClick={(e) => {
											e.stopPropagation();
											handleResetLogo("square");
										}}
										disabled={
											uploading === "square" ||
											resetting === "square"
										}
									>
										{resetting === "square" ? (
											<Loader2 className="h-4 w-4 animate-spin" />
										) : (
											<RotateCcw className="h-4 w-4" />
										)}
									</Button>
								)}
							</div>
							<div
								className={`relative border-2 border-dashed rounded-lg p-6 transition-colors h-48 flex items-center justify-center ${
									dragActiveSquare
										? "border-primary bg-primary/5"
										: "border-border"
								} ${
									uploading === "square" ||
									resetting === "square"
										? "opacity-50 pointer-events-none"
										: "cursor-pointer hover:border-primary/50"
								}`}
								onDragEnter={(e) => handleDrag(e, "square")}
								onDragLeave={(e) => handleDrag(e, "square")}
								onDragOver={(e) => handleDrag(e, "square")}
								onDrop={(e) => handleDrop(e, "square")}
								onClick={() =>
									document
										.getElementById("squareLogoInput")
										?.click()
								}
							>
								<input
									id="squareLogoInput"
									type="file"
									accept="image/png,image/jpeg,image/svg+xml"
									onChange={(e) =>
										handleFileInput(e, "square")
									}
									className="hidden"
								/>
								{branding?.square_logo_url ? (
									<div className="flex flex-col items-center gap-3 w-full">
										<img
											src={branding.square_logo_url}
											alt="Square logo"
											className="max-h-24 max-w-24 object-contain"
										/>
										<p className="text-xs text-muted-foreground">
											Click or drag to replace
										</p>
									</div>
								) : (
									<div className="flex flex-col items-center gap-2 text-center">
										<Upload className="h-10 w-10 text-muted-foreground" />
										<p className="text-sm font-medium">
											Drop square logo here
										</p>
										<p className="text-xs text-muted-foreground">
											or click to browse
										</p>
									</div>
								)}
								{uploading === "square" && (
									<div className="absolute inset-0 flex items-center justify-center bg-background/50 rounded-lg">
										<Loader2 className="h-8 w-8 animate-spin" />
									</div>
								)}
							</div>
						</div>

						{/* Rectangle Logo */}
						<div className="space-y-3">
							<div className="flex items-center justify-between">
								<Label>Rectangle Logo (16:9 ratio)</Label>
								{branding?.rectangle_logo_url && (
									<Button
										size="sm"
										variant="ghost"
										onClick={(e) => {
											e.stopPropagation();
											handleResetLogo("rectangle");
										}}
										disabled={
											uploading === "rectangle" ||
											resetting === "rectangle"
										}
									>
										{resetting === "rectangle" ? (
											<Loader2 className="h-4 w-4 animate-spin" />
										) : (
											<RotateCcw className="h-4 w-4" />
										)}
									</Button>
								)}
							</div>
							<div
								className={`relative border-2 border-dashed rounded-lg p-6 transition-colors h-48 flex items-center justify-center ${
									dragActiveRectangle
										? "border-primary bg-primary/5"
										: "border-border"
								} ${
									uploading === "rectangle" ||
									resetting === "rectangle"
										? "opacity-50 pointer-events-none"
										: "cursor-pointer hover:border-primary/50"
								}`}
								onDragEnter={(e) => handleDrag(e, "rectangle")}
								onDragLeave={(e) => handleDrag(e, "rectangle")}
								onDragOver={(e) => handleDrag(e, "rectangle")}
								onDrop={(e) => handleDrop(e, "rectangle")}
								onClick={() =>
									document
										.getElementById("rectangleLogoInput")
										?.click()
								}
							>
								<input
									id="rectangleLogoInput"
									type="file"
									accept="image/png,image/jpeg,image/svg+xml"
									onChange={(e) =>
										handleFileInput(e, "rectangle")
									}
									className="hidden"
								/>
								{branding?.rectangle_logo_url ? (
									<div className="flex flex-col items-center gap-3 w-full">
										<img
											src={branding.rectangle_logo_url}
											alt="Rectangle logo"
											className="max-h-12 max-w-48 object-contain"
										/>
										<p className="text-xs text-muted-foreground">
											Click or drag to replace
										</p>
									</div>
								) : (
									<div className="flex flex-col items-center gap-2 text-center">
										<Upload className="h-10 w-10 text-muted-foreground" />
										<p className="text-sm font-medium">
											Drop rectangle logo here
										</p>
										<p className="text-xs text-muted-foreground">
											or click to browse
										</p>
									</div>
								)}
								{uploading === "rectangle" && (
									<div className="absolute inset-0 flex items-center justify-center bg-background/50 rounded-lg">
										<Loader2 className="h-8 w-8 animate-spin" />
									</div>
								)}
							</div>
						</div>
					</div>
				</CardContent>
			</Card>
		</div>
	);
}

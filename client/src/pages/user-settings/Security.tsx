/**
 * Security Settings - Passkeys Management
 *
 * Allows users to:
 * - Register new passkeys (Face ID, Touch ID, etc.)
 * - View and manage existing passkeys
 * - Delete passkeys
 */

import { useState } from "react";
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
} from "@/components/ui/alert-dialog";
import {
	Dialog,
	DialogContent,
	DialogDescription,
	DialogFooter,
	DialogHeader,
	DialogTitle,
} from "@/components/ui/dialog";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
	Fingerprint,
	Plus,
	Trash2,
	Loader2,
	Info,
	Smartphone,
	Cloud,
	Clock,
	ShieldCheck,
	AlertTriangle,
} from "lucide-react";
import { usePasskeys, usePasskeySupport } from "@/hooks/usePasskeys";
import type { PasskeyPublic } from "@/services/passkeys";
import { formatDistanceToNow } from "date-fns";

export function Security() {
	const support = usePasskeySupport();
	const {
		passkeys,
		passkeyCount,
		isLoading,
		isError,
		register,
		isRegistering,
		delete: deletePasskey,
		isDeleting,
	} = usePasskeys();

	// Dialog state
	const [showAddDialog, setShowAddDialog] = useState(false);
	const [deviceName, setDeviceName] = useState("");
	const [passkeyToDelete, setPasskeyToDelete] = useState<PasskeyPublic | null>(
		null,
	);

	const handleRegister = () => {
		register(deviceName || undefined, {
			onSuccess: () => {
				setShowAddDialog(false);
				setDeviceName("");
			},
		});
	};

	const handleDelete = () => {
		if (passkeyToDelete) {
			deletePasskey(passkeyToDelete.id, {
				onSuccess: () => {
					setPasskeyToDelete(null);
				},
			});
		}
	};

	const getDeviceIcon = (deviceType: string) => {
		if (deviceType === "multiDevice") {
			return <Cloud className="h-5 w-5 text-blue-500" />;
		}
		return <Smartphone className="h-5 w-5 text-gray-500" />;
	};

	// Show loading state
	if (support.isLoading) {
		return (
			<Card>
				<CardHeader>
					<Skeleton className="h-6 w-32" />
					<Skeleton className="h-4 w-64 mt-2" />
				</CardHeader>
				<CardContent>
					<Skeleton className="h-20 w-full" />
				</CardContent>
			</Card>
		);
	}

	// Show unsupported message
	if (!support.supported) {
		return (
			<Card>
				<CardHeader>
					<CardTitle className="flex items-center gap-2">
						<Fingerprint className="h-5 w-5" />
						Passkeys
					</CardTitle>
					<CardDescription>
						Sign in faster with Face ID, Touch ID, or security keys
					</CardDescription>
				</CardHeader>
				<CardContent>
					<Alert variant="default">
						<AlertTriangle className="h-4 w-4" />
						<AlertTitle>Passkeys not supported</AlertTitle>
						<AlertDescription>
							Your browser doesn't support passkeys. Try using a
							modern browser like Chrome, Safari, or Edge on a
							device with biometric authentication.
						</AlertDescription>
					</Alert>
				</CardContent>
			</Card>
		);
	}

	return (
		<div className="space-y-6">
			{/* Passkeys Section */}
			<Card>
				<CardHeader>
					<div className="flex items-center justify-between">
						<div>
							<CardTitle className="flex items-center gap-2">
								<Fingerprint className="h-5 w-5" />
								Passkeys
							</CardTitle>
							<CardDescription className="mt-1">
								Sign in faster with Face ID, Touch ID, or
								security keys
							</CardDescription>
						</div>
						<Button onClick={() => setShowAddDialog(true)}>
							<Plus className="h-4 w-4 mr-2" />
							Add Passkey
						</Button>
					</div>
				</CardHeader>
				<CardContent>
					{/* Info banner */}
					<Alert className="mb-6">
						<ShieldCheck className="h-4 w-4" />
						<AlertTitle>Passwordless login</AlertTitle>
						<AlertDescription>
							Passkeys let you sign in without a password using
							biometrics or your device PIN. They're phishing
							resistant and more secure than passwords.
						</AlertDescription>
					</Alert>

					{/* Loading state */}
					{isLoading && (
						<div className="space-y-3">
							<Skeleton className="h-16 w-full" />
							<Skeleton className="h-16 w-full" />
						</div>
					)}

					{/* Error state */}
					{isError && (
						<Alert variant="destructive">
							<AlertTriangle className="h-4 w-4" />
							<AlertDescription>
								Failed to load passkeys. Please try again.
							</AlertDescription>
						</Alert>
					)}

					{/* Empty state */}
					{!isLoading && !isError && passkeyCount === 0 && (
						<div className="text-center py-8 text-muted-foreground">
							<Fingerprint className="h-12 w-12 mx-auto mb-4 opacity-50" />
							<p className="font-medium">No passkeys yet</p>
							<p className="text-sm mt-1">
								Add a passkey to enable passwordless sign-in
							</p>
						</div>
					)}

					{/* Passkey list */}
					{!isLoading && !isError && passkeyCount > 0 && (
						<div className="space-y-3">
							{passkeys.map((passkey) => (
								<div
									key={passkey.id}
									className="flex items-center justify-between p-4 border rounded-lg hover:bg-muted/50 transition-colors"
								>
									<div className="flex items-center gap-4">
										{getDeviceIcon(passkey.device_type)}
										<div>
											<div className="flex items-center gap-2">
												<span className="font-medium">
													{passkey.name}
												</span>
												{passkey.backed_up && (
													<Badge
														variant="secondary"
														className="text-xs"
													>
														<Cloud className="h-3 w-3 mr-1" />
														Synced
													</Badge>
												)}
											</div>
											<div className="flex items-center gap-3 text-sm text-muted-foreground mt-1">
												<span className="flex items-center gap-1">
													<Clock className="h-3 w-3" />
													Created{" "}
													{formatDistanceToNow(
														new Date(
															passkey.created_at,
														),
														{ addSuffix: true },
													)}
												</span>
												{passkey.last_used_at && (
													<span>
														Last used{" "}
														{formatDistanceToNow(
															new Date(
																passkey.last_used_at,
															),
															{ addSuffix: true },
														)}
													</span>
												)}
											</div>
										</div>
									</div>
									<Button
										variant="ghost"
										size="icon"
										className="text-destructive hover:text-destructive hover:bg-destructive/10"
										onClick={() =>
											setPasskeyToDelete(passkey)
										}
									>
										<Trash2 className="h-4 w-4" />
									</Button>
								</div>
							))}
						</div>
					)}
				</CardContent>
			</Card>

			{/* Add Passkey Dialog */}
			<Dialog open={showAddDialog} onOpenChange={setShowAddDialog}>
				<DialogContent>
					<DialogHeader>
						<DialogTitle className="flex items-center gap-2">
							<Fingerprint className="h-5 w-5" />
							Add Passkey
						</DialogTitle>
						<DialogDescription>
							Register a new passkey for passwordless sign-in.
							You'll be prompted to use Face ID, Touch ID, or
							your device PIN.
						</DialogDescription>
					</DialogHeader>

					<form
						onSubmit={(e) => {
							e.preventDefault();
							handleRegister();
						}}
					>
						<div className="space-y-4 py-4">
							<div className="space-y-2">
								<Label htmlFor="device-name">
									Device Name (optional)
								</Label>
								<Input
									id="device-name"
									placeholder='e.g., "MacBook Pro" or "iPhone"'
									value={deviceName}
									onChange={(e) =>
										setDeviceName(e.target.value)
									}
								/>
								<p className="text-xs text-muted-foreground">
									A friendly name to help you identify this
									passkey later
								</p>
							</div>

							<Alert>
								<Info className="h-4 w-4" />
								<AlertDescription className="text-sm">
									When you click "Register", your browser will
									prompt you to create a passkey. This uses
									your device's built-in security (Face ID,
									Touch ID, Windows Hello, etc.)
								</AlertDescription>
							</Alert>
						</div>

						<DialogFooter>
							<Button
								type="button"
								variant="outline"
								onClick={() => setShowAddDialog(false)}
								disabled={isRegistering}
							>
								Cancel
							</Button>
							<Button type="submit" disabled={isRegistering}>
								{isRegistering ? (
									<>
										<Loader2 className="h-4 w-4 mr-2 animate-spin" />
										Registering...
									</>
								) : (
									<>
										<Fingerprint className="h-4 w-4 mr-2" />
										Register Passkey
									</>
								)}
							</Button>
						</DialogFooter>
					</form>
				</DialogContent>
			</Dialog>

			{/* Delete Confirmation Dialog */}
			<AlertDialog
				open={!!passkeyToDelete}
				onOpenChange={() => setPasskeyToDelete(null)}
			>
				<AlertDialogContent>
					<AlertDialogHeader>
						<AlertDialogTitle>Remove Passkey?</AlertDialogTitle>
						<AlertDialogDescription>
							Are you sure you want to remove "
							{passkeyToDelete?.name}"? You won't be able to use
							this passkey to sign in anymore.
						</AlertDialogDescription>
					</AlertDialogHeader>
					<AlertDialogFooter>
						<AlertDialogCancel disabled={isDeleting}>
							Cancel
						</AlertDialogCancel>
						<AlertDialogAction
							onClick={handleDelete}
							disabled={isDeleting}
							className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
						>
							{isDeleting ? (
								<>
									<Loader2 className="h-4 w-4 mr-2 animate-spin" />
									Removing...
								</>
							) : (
								"Remove Passkey"
							)}
						</AlertDialogAction>
					</AlertDialogFooter>
				</AlertDialogContent>
			</AlertDialog>
		</div>
	);
}

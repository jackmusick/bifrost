import { useState, useEffect, useRef, useCallback } from "react";
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
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { toast } from "sonner";
import {
	Loader2,
	Camera,
	Trash2,
	AlertCircle,
	Check,
	Eye,
	EyeOff,
} from "lucide-react";
import { profileService, type ProfileResponse } from "@/services/profile";
import { useAuth } from "@/contexts/AuthContext";

export function BasicInfo() {
	const { user } = useAuth();
	const [profile, setProfile] = useState<ProfileResponse | null>(null);
	const [loading, setLoading] = useState(true);
	const [error, setError] = useState<string | null>(null);

	// Profile form state
	const [name, setName] = useState("");
	const [savingName, setSavingName] = useState(false);
	const [nameChanged, setNameChanged] = useState(false);

	// Avatar state
	const [avatarUrl, setAvatarUrl] = useState<string | null>(null);
	const [uploadingAvatar, setUploadingAvatar] = useState(false);
	const [deletingAvatar, setDeletingAvatar] = useState(false);
	const [isDragging, setIsDragging] = useState(false);
	const fileInputRef = useRef<HTMLInputElement>(null);

	// Password form state
	const [currentPassword, setCurrentPassword] = useState("");
	const [newPassword, setNewPassword] = useState("");
	const [confirmPassword, setConfirmPassword] = useState("");
	const [showCurrentPassword, setShowCurrentPassword] = useState(false);
	const [showNewPassword, setShowNewPassword] = useState(false);
	const [showConfirmPassword, setShowConfirmPassword] = useState(false);
	const [changingPassword, setChangingPassword] = useState(false);
	const [passwordError, setPasswordError] = useState<string | null>(null);

	// Load profile data
	useEffect(() => {
		async function loadProfile() {
			try {
				const data = await profileService.getProfile();
				setProfile(data);
				setName(data.name || "");
				if (data.has_avatar) {
					// Add cache-busting timestamp
					setAvatarUrl(
						`${profileService.getAvatarUrl()}?t=${Date.now()}`,
					);
				}
			} catch (err) {
				console.error("Failed to load profile:", err);
				setError("Failed to load profile. Please try again.");
			} finally {
				setLoading(false);
			}
		}

		loadProfile();
	}, []);

	// Track name changes
	useEffect(() => {
		setNameChanged(name !== (profile?.name || ""));
	}, [name, profile?.name]);

	// Handle name save
	const handleSaveName = async () => {
		setSavingName(true);
		try {
			const updated = await profileService.updateProfile({
				name: name || null,
			});
			setProfile(updated);
			toast.success("Profile updated");
		} catch (err) {
			console.error("Failed to update profile:", err);
			toast.error("Failed to update profile");
		} finally {
			setSavingName(false);
		}
	};

	// Handle avatar upload
	const handleAvatarUpload = async (file: File) => {
		// Validate file type
		if (!["image/png", "image/jpeg", "image/jpg"].includes(file.type)) {
			toast.error("Please upload a PNG or JPEG image");
			return;
		}

		// Validate file size (2MB max)
		if (file.size > 2 * 1024 * 1024) {
			toast.error("Image must be less than 2MB");
			return;
		}

		setUploadingAvatar(true);
		try {
			const updated = await profileService.uploadAvatar(file);
			setProfile(updated);
			setAvatarUrl(`${profileService.getAvatarUrl()}?t=${Date.now()}`);
			toast.success("Avatar uploaded");
		} catch (err) {
			console.error("Failed to upload avatar:", err);
			toast.error("Failed to upload avatar");
		} finally {
			setUploadingAvatar(false);
		}
	};

	// Handle avatar delete
	const handleDeleteAvatar = async () => {
		setDeletingAvatar(true);
		try {
			const updated = await profileService.deleteAvatar();
			setProfile(updated);
			setAvatarUrl(null);
			toast.success("Avatar removed");
		} catch (err) {
			console.error("Failed to delete avatar:", err);
			toast.error("Failed to delete avatar");
		} finally {
			setDeletingAvatar(false);
		}
	};

	// Handle file input change
	const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
		const file = e.target.files?.[0];
		if (file) {
			handleAvatarUpload(file);
		}
	};

	// Handle drag and drop
	const handleDragOver = useCallback((e: React.DragEvent) => {
		e.preventDefault();
		setIsDragging(true);
	}, []);

	const handleDragLeave = useCallback((e: React.DragEvent) => {
		e.preventDefault();
		setIsDragging(false);
	}, []);

	const handleDrop = useCallback((e: React.DragEvent) => {
		e.preventDefault();
		setIsDragging(false);
		const file = e.dataTransfer.files[0];
		if (file) {
			handleAvatarUpload(file);
		}
	}, []);

	// Handle password change/set
	const handleChangePassword = async () => {
		setPasswordError(null);

		const hasPassword = profile?.has_password ?? false;

		// Validate passwords
		if (hasPassword && !currentPassword) {
			setPasswordError("Current password is required");
			return;
		}
		if (!newPassword) {
			setPasswordError("New password is required");
			return;
		}
		if (newPassword.length < 8) {
			setPasswordError("New password must be at least 8 characters");
			return;
		}
		if (newPassword !== confirmPassword) {
			setPasswordError("Passwords do not match");
			return;
		}

		setChangingPassword(true);
		try {
			await profileService.changePassword(
				hasPassword ? currentPassword : null,
				newPassword,
			);
			toast.success(
				hasPassword
					? "Password changed successfully"
					: "Password set successfully",
			);
			// Clear form and update profile state
			setCurrentPassword("");
			setNewPassword("");
			setConfirmPassword("");
			// Refresh profile to get updated has_password
			const updatedProfile = await profileService.getProfile();
			setProfile(updatedProfile);
		} catch (err) {
			console.error("Failed to change password:", err);
			const errorMessage =
				err instanceof Error
					? err.message
					: "Failed to change password";
			setPasswordError(errorMessage);
		} finally {
			setChangingPassword(false);
		}
	};

	// Get initials for avatar fallback
	const getInitials = () => {
		if (profile?.name) {
			return profile.name
				.split(" ")
				.map((n) => n[0])
				.join("")
				.toUpperCase()
				.slice(0, 2);
		}
		if (profile?.email) {
			return profile.email[0].toUpperCase();
		}
		return "U";
	};

	if (loading) {
		return (
			<div className="flex items-center justify-center py-12">
				<Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
			</div>
		);
	}

	if (error) {
		return (
			<Card>
				<CardContent className="p-6">
					<Alert variant="destructive">
						<AlertCircle className="h-4 w-4" />
						<AlertDescription>{error}</AlertDescription>
					</Alert>
					<Button
						onClick={() => window.location.reload()}
						className="mt-4"
					>
						Retry
					</Button>
				</CardContent>
			</Card>
		);
	}

	return (
		<div className="space-y-6">
			{/* Profile Picture */}
			<Card>
				<CardHeader>
					<CardTitle>Profile Picture</CardTitle>
					<CardDescription>
						Upload a profile picture (PNG or JPEG, max 2MB)
					</CardDescription>
				</CardHeader>
				<CardContent>
					<div className="flex items-start gap-6">
						{/* Avatar Preview */}
						<div
							className={`relative group cursor-pointer ${isDragging ? "ring-2 ring-primary ring-offset-2" : ""}`}
							onDragOver={handleDragOver}
							onDragLeave={handleDragLeave}
							onDrop={handleDrop}
							onClick={() => fileInputRef.current?.click()}
						>
							<Avatar className="h-24 w-24">
								<AvatarImage src={avatarUrl || undefined} />
								<AvatarFallback className="text-2xl">
									{getInitials()}
								</AvatarFallback>
							</Avatar>
							<div className="absolute inset-0 flex items-center justify-center bg-black/50 rounded-full opacity-0 group-hover:opacity-100 transition-opacity">
								{uploadingAvatar ? (
									<Loader2 className="h-6 w-6 text-white animate-spin" />
								) : (
									<Camera className="h-6 w-6 text-white" />
								)}
							</div>
							<input
								ref={fileInputRef}
								type="file"
								accept="image/png,image/jpeg,image/jpg"
								onChange={handleFileChange}
								className="hidden"
							/>
						</div>

						{/* Upload Instructions & Actions */}
						<div className="flex-1 space-y-3">
							<div className="text-sm text-muted-foreground">
								<p>
									Click on the avatar or drag and drop an
									image.
								</p>
								<p className="mt-1">
									Recommended: Square image, at least
									128x128px.
								</p>
							</div>
							{profile?.has_avatar && (
								<Button
									variant="outline"
									size="sm"
									onClick={(e) => {
										e.stopPropagation();
										handleDeleteAvatar();
									}}
									disabled={deletingAvatar}
								>
									{deletingAvatar ? (
										<>
											<Loader2 className="h-4 w-4 mr-2 animate-spin" />
											Removing...
										</>
									) : (
										<>
											<Trash2 className="h-4 w-4 mr-2" />
											Remove picture
										</>
									)}
								</Button>
							)}
						</div>
					</div>
				</CardContent>
			</Card>

			{/* Display Name */}
			<Card>
				<CardHeader>
					<CardTitle>Display Name</CardTitle>
					<CardDescription>
						This is how your name appears to other users
					</CardDescription>
				</CardHeader>
				<CardContent className="space-y-4">
					<div className="space-y-2">
						<Label htmlFor="name">Name</Label>
						<Input
							id="name"
							placeholder="Enter your name"
							value={name}
							onChange={(e) => setName(e.target.value)}
						/>
					</div>

					<div className="space-y-2">
						<Label htmlFor="email">Email</Label>
						<Input
							id="email"
							value={profile?.email || user?.email || ""}
							disabled
							className="bg-muted"
						/>
						<p className="text-xs text-muted-foreground">
							Email cannot be changed
						</p>
					</div>

					<div className="flex justify-end">
						<Button
							onClick={handleSaveName}
							disabled={savingName || !nameChanged}
						>
							{savingName ? (
								<>
									<Loader2 className="h-4 w-4 mr-2 animate-spin" />
									Saving...
								</>
							) : nameChanged ? (
								"Save Changes"
							) : (
								<>
									<Check className="h-4 w-4 mr-2" />
									Saved
								</>
							)}
						</Button>
					</div>
				</CardContent>
			</Card>

			{/* Change/Set Password */}
			<Card>
				<CardHeader>
					<CardTitle>
						{profile?.has_password ? "Change Password" : "Set Password"}
					</CardTitle>
					<CardDescription>
						{profile?.has_password
							? "Update your account password"
							: "Add a password to your account for email/password login"}
					</CardDescription>
				</CardHeader>
				<CardContent className="space-y-4">
					{passwordError && (
						<Alert variant="destructive">
							<AlertCircle className="h-4 w-4" />
							<AlertDescription>{passwordError}</AlertDescription>
						</Alert>
					)}

					{profile?.has_password && (
						<div className="space-y-2">
							<Label htmlFor="current-password">
								Current Password
							</Label>
							<div className="relative">
								<Input
									id="current-password"
									type={showCurrentPassword ? "text" : "password"}
									value={currentPassword}
									onChange={(e) =>
										setCurrentPassword(e.target.value)
									}
									placeholder="Enter current password"
								/>
								<Button
									type="button"
									variant="ghost"
									size="icon"
									className="absolute right-0 top-0 h-full px-3 hover:bg-transparent"
									onClick={() =>
										setShowCurrentPassword(!showCurrentPassword)
									}
								>
									{showCurrentPassword ? (
										<EyeOff className="h-4 w-4 text-muted-foreground" />
									) : (
										<Eye className="h-4 w-4 text-muted-foreground" />
									)}
								</Button>
							</div>
						</div>
					)}

					<div className="space-y-2">
						<Label htmlFor="new-password">
							{profile?.has_password ? "New Password" : "Password"}
						</Label>
						<div className="relative">
							<Input
								id="new-password"
								type={showNewPassword ? "text" : "password"}
								value={newPassword}
								onChange={(e) => setNewPassword(e.target.value)}
								placeholder={profile?.has_password ? "Enter new password" : "Enter password"}
							/>
							<Button
								type="button"
								variant="ghost"
								size="icon"
								className="absolute right-0 top-0 h-full px-3 hover:bg-transparent"
								onClick={() =>
									setShowNewPassword(!showNewPassword)
								}
							>
								{showNewPassword ? (
									<EyeOff className="h-4 w-4 text-muted-foreground" />
								) : (
									<Eye className="h-4 w-4 text-muted-foreground" />
								)}
							</Button>
						</div>
						<p className="text-xs text-muted-foreground">
							Minimum 8 characters
						</p>
					</div>

					<div className="space-y-2">
						<Label htmlFor="confirm-password">
							Confirm Password
						</Label>
						<div className="relative">
							<Input
								id="confirm-password"
								type={showConfirmPassword ? "text" : "password"}
								value={confirmPassword}
								onChange={(e) =>
									setConfirmPassword(e.target.value)
								}
								placeholder="Confirm password"
							/>
							<Button
								type="button"
								variant="ghost"
								size="icon"
								className="absolute right-0 top-0 h-full px-3 hover:bg-transparent"
								onClick={() =>
									setShowConfirmPassword(!showConfirmPassword)
								}
							>
								{showConfirmPassword ? (
									<EyeOff className="h-4 w-4 text-muted-foreground" />
								) : (
									<Eye className="h-4 w-4 text-muted-foreground" />
								)}
							</Button>
						</div>
					</div>

					<div className="flex justify-end">
						<Button
							onClick={handleChangePassword}
							disabled={
								changingPassword ||
								(profile?.has_password && !currentPassword) ||
								!newPassword ||
								!confirmPassword
							}
						>
							{changingPassword ? (
								<>
									<Loader2 className="h-4 w-4 mr-2 animate-spin" />
									{profile?.has_password ? "Changing..." : "Setting..."}
								</>
							) : profile?.has_password ? (
								"Change Password"
							) : (
								"Set Password"
							)}
						</Button>
					</div>
				</CardContent>
			</Card>
		</div>
	);
}

/**
 * Passkey Setup Banner
 *
 * Prompts users to set up a passkey for faster, more secure login.
 * Shows when:
 * - Browser supports passkeys
 * - User has no passkeys registered
 * - User hasn't dismissed the banner
 */

import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Fingerprint, X } from "lucide-react";
import { supportsPasskeys } from "@/services/passkeys";
import { usePasskeyList } from "@/hooks/usePasskeys";

const DISMISSED_KEY = "passkey_banner_dismissed";

export function PasskeySetupBanner() {
	const navigate = useNavigate();
	const [isDismissed, setIsDismissed] = useState(() => {
		return localStorage.getItem(DISMISSED_KEY) === "true";
	});

	// supportsPasskeys() is a synchronous check of browser capabilities
	// so we can call it directly without useEffect
	const isSupported = supportsPasskeys();

	const { data: passkeyData, isLoading } = usePasskeyList();

	// Don't show if:
	// - Still loading
	// - Browser doesn't support passkeys
	// - User already dismissed
	// - User already has passkeys
	if (
		isLoading ||
		!isSupported ||
		isDismissed ||
		(passkeyData && passkeyData.count > 0)
	) {
		return null;
	}

	const handleDismiss = () => {
		localStorage.setItem(DISMISSED_KEY, "true");
		setIsDismissed(true);
	};

	const handleSetup = () => {
		navigate("/user-settings/security");
	};

	return (
		<Alert className="mb-6 relative border-primary/20 bg-primary/5">
			<Fingerprint className="h-4 w-4" />
			<AlertTitle className="pr-8">Enable passwordless login</AlertTitle>
			<AlertDescription className="mt-2">
				<p className="text-sm text-muted-foreground mb-3">
					Add a passkey to sign in faster with Face ID, Touch ID, or
					your device PIN. It's more secure than passwords alone.
				</p>
				<div className="flex gap-2">
					<Button size="sm" onClick={handleSetup}>
						<Fingerprint className="h-4 w-4 mr-2" />
						Set up passkey
					</Button>
					<Button size="sm" variant="ghost" onClick={handleDismiss}>
						Maybe later
					</Button>
				</div>
			</AlertDescription>
			<Button
				variant="ghost"
				size="icon"
				className="absolute right-2 top-2 h-6 w-6"
				onClick={handleDismiss}
			>
				<X className="h-4 w-4" />
				<span className="sr-only">Dismiss</span>
			</Button>
		</Alert>
	);
}

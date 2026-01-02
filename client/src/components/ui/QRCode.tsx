/**
 * QR Code Component
 *
 * Generates QR codes locally using the qrcode library.
 * No external service dependencies, better privacy.
 */

import { useEffect, useState, useMemo } from "react";
import QRCodeLib from "qrcode";
import { Skeleton } from "@/components/ui/skeleton";
import { AlertCircle } from "lucide-react";

interface QRCodeProps {
	/** Data to encode in the QR code */
	data: string;
	/** Size in pixels (default: 200) */
	size?: number;
	/** CSS class for the container */
	className?: string;
	/** Alt text for accessibility */
	alt?: string;
}

/**
 * Inner component that handles a single QR code generation.
 * Remounted when data changes via key prop in parent.
 */
function QRCodeInner({
	data,
	size,
	className,
	alt,
}: Required<Omit<QRCodeProps, "className">> & { className: string }) {
	// Start with dataUrl null (loading state) - effect will populate it
	const [dataUrl, setDataUrl] = useState<string | null>(null);
	const [error, setError] = useState<string | null>(null);

	useEffect(() => {
		let cancelled = false;

		QRCodeLib.toDataURL(data, {
			width: size,
			margin: 2,
			color: {
				dark: "#000000",
				light: "#FFFFFF",
			},
			errorCorrectionLevel: "M",
		})
			.then((url) => {
				if (!cancelled) {
					setDataUrl(url);
				}
			})
			.catch((err) => {
				if (!cancelled) {
					console.error("QR code generation failed:", err);
					setError("Failed to generate QR code");
				}
			});

		return () => {
			cancelled = true;
		};
	}, [data, size]);

	// Loading: no dataUrl yet and no error
	if (!dataUrl && !error) {
		return (
			<Skeleton
				className={`rounded-lg ${className}`}
				style={{ width: size, height: size }}
			/>
		);
	}

	if (error) {
		return (
			<div
				className={`flex flex-col items-center justify-center bg-muted rounded-lg ${className}`}
				style={{ width: size, height: size }}
			>
				<AlertCircle className="h-8 w-8 text-destructive mb-2" />
				<span className="text-sm text-muted-foreground text-center px-4">
					{error}
				</span>
			</div>
		);
	}

	return (
		<img
			src={dataUrl || ""}
			alt={alt}
			width={size}
			height={size}
			className={`rounded-lg ${className}`}
		/>
	);
}

export function QRCode({
	data,
	size = 200,
	className = "",
	alt = "QR Code",
}: QRCodeProps) {
	// Validate data - derive error state from props
	const dataError = useMemo(
		() => (!data ? "No data provided" : null),
		[data],
	);

	// If no data, show error state
	if (dataError) {
		return (
			<div
				className={`flex flex-col items-center justify-center bg-muted rounded-lg ${className}`}
				style={{ width: size, height: size }}
			>
				<AlertCircle className="h-8 w-8 text-destructive mb-2" />
				<span className="text-sm text-muted-foreground text-center px-4">
					{dataError}
				</span>
			</div>
		);
	}

	// Render inner component with key to force remount on data change
	return (
		<QRCodeInner
			key={`${data}-${size}`}
			data={data}
			size={size}
			className={className}
			alt={alt}
		/>
	);
}

export default QRCode;

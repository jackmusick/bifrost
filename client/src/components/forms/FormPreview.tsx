import {
	Card,
	CardContent,
	CardDescription,
	CardHeader,
	CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import type { FormField } from "@/lib/client-types";

interface FormPreviewProps {
	formName: string;
	formDescription: string;
	fields: FormField[];
}

export function FormPreview({
	formName,
	formDescription,
	fields,
}: FormPreviewProps) {
	const renderField = (field: FormField) => {
		switch (field.type) {
			case "textarea":
				return (
					<Textarea
						placeholder={field.placeholder ?? undefined}
						defaultValue={field.default_value as string}
						disabled
					/>
				);
			case "checkbox":
				return (
					<div className="flex items-center space-x-2">
						<input
							type="checkbox"
							id={field.name}
							defaultChecked={field.default_value as boolean}
							disabled
							className="h-4 w-4"
						/>
						<Label htmlFor={field.name}>{field.label}</Label>
					</div>
				);
			case "select":
				return (
					<select
						className="flex h-8 w-full rounded-2xl border border-transparent bg-input/50 px-2.5 text-sm transition-[color,box-shadow] duration-200 outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/30 disabled:cursor-not-allowed disabled:opacity-50"
						disabled
					>
						<option>
							{field.placeholder || "Select an option..."}
						</option>
					</select>
				);
			default:
				return (
					<Input
						type={
							field.type === "email"
								? "email"
								: field.type === "number"
									? "number"
									: "text"
						}
						placeholder={field.placeholder ?? undefined}
						defaultValue={field.default_value as string}
						disabled
					/>
				);
		}
	};

	return (
		<div className="flex justify-center">
			<Card className="w-full max-w-2xl">
				<CardHeader>
					<CardTitle>{formName || "Form Preview"}</CardTitle>
					{formDescription && (
						<CardDescription>{formDescription}</CardDescription>
					)}
				</CardHeader>
				<CardContent>
					{fields.length > 0 ? (
						<div className="space-y-4">
							{fields.map((field, index) => (
								<div key={index} className="space-y-2">
									{field.type !== "checkbox" && (
										<Label>
											{field.label}
											{field.required && (
												<span className="text-destructive ml-1">
													*
												</span>
											)}
										</Label>
									)}
									{renderField(field)}
									{field.help_text && (
										<p className="text-sm text-muted-foreground">
											{field.help_text}
										</p>
									)}
								</div>
							))}
							<div className="pt-4">
								<Button disabled>Submit</Button>
							</div>
						</div>
					) : (
						<div className="flex flex-col items-center justify-center py-12 text-center">
							<p className="text-sm text-muted-foreground">
								Add fields to see the form preview
							</p>
						</div>
					)}
				</CardContent>
			</Card>
		</div>
	);
}

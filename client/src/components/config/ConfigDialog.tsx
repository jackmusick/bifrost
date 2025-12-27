import { useEffect } from "react";
import { useForm, useWatch } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
import { Loader2 } from "lucide-react";
import {
	Dialog,
	DialogContent,
	DialogDescription,
	DialogFooter,
	DialogHeader,
	DialogTitle,
} from "@/components/ui/dialog";
import {
	Form,
	FormControl,
	FormDescription,
	FormField,
	FormItem,
	FormLabel,
	FormMessage,
} from "@/components/ui/form";
import {
	Select,
	SelectContent,
	SelectItem,
	SelectTrigger,
	SelectValue,
} from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useSetConfig } from "@/hooks/useConfig";
import { useAuth } from "@/contexts/AuthContext";
import { OrganizationSelect } from "@/components/forms/OrganizationSelect";
import type { components } from "@/lib/v1";

type Config = components["schemas"]["ConfigResponse"];

const formSchema = z.object({
	key: z
		.string()
		.min(1, "Key is required")
		.regex(/^[a-zA-Z0-9_]+$/, "Key must be alphanumeric with underscores"),
	value: z.string().min(1, "Value is required"),
	type: z.enum(["string", "int", "bool", "json", "secret"]),
	description: z.string().optional(),
	organization_id: z.string().nullable(),
});

type FormValues = z.infer<typeof formSchema>;

interface ConfigDialogProps {
	config?: Config | undefined;
	open: boolean;
	onClose: () => void;
}

export function ConfigDialog({ config, open, onClose }: ConfigDialogProps) {
	const setConfig = useSetConfig();
	const { isPlatformAdmin, user } = useAuth();
	const isEditing = !!config;

	// Default organization_id for org users is their org, for platform admins it's null (global)
	const defaultOrgId = isPlatformAdmin ? null : (user?.organizationId ?? null);

	const form = useForm<FormValues>({
		resolver: zodResolver(formSchema),
		defaultValues: {
			key: "",
			value: "",
			type: "string",
			description: "",
			organization_id: defaultOrgId,
		},
	});

	// Watch the type field to conditionally render input type
	const selectedType = useWatch({ control: form.control, name: "type" });

	useEffect(() => {
		if (config) {
			// Cast config to access org_id which may exist on the response
			const configWithOrg = config as typeof config & { org_id?: string | null };
			form.reset({
				key: config.key,
				// For secrets, we don't show the actual value - user must enter new value to update
				value:
					config.type === "secret" ? "" : String(config.value ?? ""),
				type: config.type,
				description: config.description ?? "",
				organization_id: configWithOrg.org_id ?? null,
			});
		} else {
			form.reset({
				key: "",
				value: "",
				type: "string",
				description: "",
				organization_id: defaultOrgId,
			});
		}
	}, [config, form, open, defaultOrgId]);

	const onSubmit = async (values: FormValues) => {
		// Build body with organization_id (may not be in generated types yet)
		const body = {
			key: values.key,
			value: values.value,
			type: values.type,
			description: values.description ?? null,
			organization_id: values.organization_id,
		} as Parameters<typeof setConfig.mutateAsync>[0]["body"];

		await setConfig.mutateAsync({ body });
		onClose();
	};

	return (
		<Dialog open={open} onOpenChange={onClose}>
			<DialogContent className="sm:max-w-[600px]">
				<DialogHeader>
					<DialogTitle>
						{isEditing ? "Edit Configuration" : "Add Configuration"}
					</DialogTitle>
					<DialogDescription>
						{isEditing
							? "Update the configuration value"
							: "Create a new configuration entry"}
					</DialogDescription>
				</DialogHeader>

				<Form {...form}>
					<form
						onSubmit={form.handleSubmit(onSubmit)}
						className="space-y-4"
					>
						{/* Organization Scope - Only show for platform admins */}
						{isPlatformAdmin && (
							<FormField
								control={form.control}
								name="organization_id"
								render={({ field }) => (
									<FormItem>
										<FormLabel>Organization</FormLabel>
										<FormControl>
											<OrganizationSelect
												value={field.value}
												onChange={field.onChange}
												showGlobal={true}
											/>
										</FormControl>
										<FormDescription>
											Global config is available to all organizations
										</FormDescription>
										<FormMessage />
									</FormItem>
								)}
							/>
						)}

						<FormField
							control={form.control}
							name="key"
							render={({ field }) => (
								<FormItem>
									<FormLabel>Key</FormLabel>
									<FormControl>
										<Input
											placeholder="CONFIG_KEY_NAME"
											{...field}
											disabled={isEditing}
											className="font-mono"
										/>
									</FormControl>
									<FormDescription>
										Alphanumeric characters and underscores
										only
									</FormDescription>
									<FormMessage />
								</FormItem>
							)}
						/>

						<FormField
							control={form.control}
							name="type"
							render={({ field }) => (
								<FormItem>
									<FormLabel>Type</FormLabel>
									<Select
										onValueChange={field.onChange}
										defaultValue={field.value}
									>
										<FormControl>
											<SelectTrigger>
												<SelectValue placeholder="Select type" />
											</SelectTrigger>
										</FormControl>
										<SelectContent>
											<SelectItem value="string">
												String
											</SelectItem>
											<SelectItem value="int">
												Integer
											</SelectItem>
											<SelectItem value="bool">
												Boolean
											</SelectItem>
											<SelectItem value="json">
												JSON
											</SelectItem>
											<SelectItem value="secret">
												Secret
											</SelectItem>
										</SelectContent>
									</Select>
									<FormDescription>
										{selectedType === "secret" &&
											"Secret values are encrypted at rest"}
									</FormDescription>
									<FormMessage />
								</FormItem>
							)}
						/>

						<FormField
							control={form.control}
							name="value"
							render={({ field }) => (
								<FormItem>
									<FormLabel>Value</FormLabel>
									<FormControl>
										{selectedType === "secret" ? (
											<Input
												type="password"
												placeholder={
													isEditing
														? "Enter new value to update"
														: "Enter secret value"
												}
												className="font-mono"
												{...field}
											/>
										) : (
											<Textarea
												placeholder="Configuration value"
												className="font-mono"
												{...field}
											/>
										)}
									</FormControl>
									<FormDescription>
										{selectedType === "secret"
											? isEditing
												? "Enter a new value to update the secret"
												: "Secret will be encrypted and stored securely"
											: "Enter the configuration value"}
									</FormDescription>
									<FormMessage />
								</FormItem>
							)}
						/>

						<FormField
							control={form.control}
							name="description"
							render={({ field }) => (
								<FormItem>
									<FormLabel>
										Description (Optional)
									</FormLabel>
									<FormControl>
										<Input
											placeholder="What is this config for?"
											{...field}
										/>
									</FormControl>
									<FormMessage />
								</FormItem>
							)}
						/>

						<DialogFooter>
							<Button
								type="button"
								variant="outline"
								onClick={onClose}
							>
								Cancel
							</Button>
							<Button
								type="submit"
								disabled={
									setConfig.isPending ||
									!form.formState.isValid
								}
							>
								{setConfig.isPending && (
									<Loader2 className="mr-2 h-4 w-4 animate-spin" />
								)}
								{setConfig.isPending
									? "Saving..."
									: isEditing
										? "Update"
										: "Create"}
							</Button>
						</DialogFooter>
					</form>
				</Form>
			</DialogContent>
		</Dialog>
	);
}

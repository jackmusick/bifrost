import { useEffect } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
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
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useCreateRole, useUpdateRole } from "@/hooks/useRoles";
import type { components } from "@/lib/v1";
type Role = components["schemas"]["RolePublic"];

const formSchema = z.object({
	name: z.string().min(1, "Name is required").max(100, "Name too long"),
	description: z.string().optional(),
});

type FormValues = z.infer<typeof formSchema>;

interface RoleDialogProps {
	role?: Role | undefined;
	open: boolean;
	onClose: () => void;
}

export function RoleDialog({ role, open, onClose }: RoleDialogProps) {
	const createRole = useCreateRole();
	const updateRole = useUpdateRole();
	const isEditing = !!role;

	const form = useForm<FormValues>({
		resolver: zodResolver(formSchema),
		defaultValues: {
			name: "",
			description: "",
		},
	});

	useEffect(() => {
		if (role) {
			form.reset({
				name: role.name,
				description: role.description || "",
			});
		} else {
			form.reset({
				name: "",
				description: "",
			});
		}
	}, [role, form]);

	const onSubmit = async (values: FormValues) => {
		if (isEditing) {
			await updateRole.mutateAsync({
				params: { path: { role_id: role.id } },
				body: {
					name: values.name,
					description: values.description || null,
				},
			});
		} else {
			await createRole.mutateAsync({
				body: {
					name: values.name,
					description: values.description || null,
					is_active: true,
				},
			});
		}
		onClose();
	};

	const isPending = createRole.isPending || updateRole.isPending;

	return (
		<Dialog open={open} onOpenChange={onClose}>
			<DialogContent className="sm:max-w-[500px]">
				<DialogHeader>
					<DialogTitle>
						{isEditing ? "Edit Role" : "Create Role"}
					</DialogTitle>
					<DialogDescription>
						{isEditing
							? "Update the role information"
							: "Create a new role for organization users"}
					</DialogDescription>
				</DialogHeader>

				<Form {...form}>
					<form
						onSubmit={form.handleSubmit(onSubmit)}
						className="space-y-4"
					>
						<FormField
							control={form.control}
							name="name"
							render={({ field }) => (
								<FormItem>
									<FormLabel>Role Name</FormLabel>
									<FormControl>
										<Input
											placeholder="Admin, Viewer, Editor..."
											{...field}
										/>
									</FormControl>
									<FormDescription>
										A descriptive name for this role
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
										<Textarea
											placeholder="What permissions does this role have?"
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
							<Button type="submit" disabled={isPending}>
								{isPending
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

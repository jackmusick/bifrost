import { useState, useEffect, useMemo, useRef, useCallback, memo } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useForm, type Resolver } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { motion, AnimatePresence } from "framer-motion";
import { Card, CardContent } from "@/components/ui/card";
import { JsxTemplateRenderer } from "@/components/ui/jsx-template-renderer";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Combobox, type ComboboxOption } from "@/components/ui/combobox";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Skeleton } from "@/components/ui/skeleton";
import { Loader2, Upload } from "lucide-react";
import DOMPurify from "dompurify";
import ReactMarkdown from "react-markdown";
import type { components } from "@/lib/v1";
import type {
	FormField,
	FormSchema,
	DataProviderInputConfig,
} from "@/lib/client-types";

type Form = components["schemas"]["FormPublic"];
import { useSubmitForm } from "@/hooks/useForms";

import type { DataProviderOption } from "@/services/dataProviders";
import { getDataProviderOptions } from "@/services/dataProviders";
import { FormContextProvider, useFormContext } from "@/contexts/FormContext";
import { useLaunchWorkflow } from "@/hooks/useLaunchWorkflow";

interface FormRendererProps {
	form: Form;
}

// Helper function to convert DataProviderOption[] to ComboboxOption[]
function toComboboxOptions(
	options: DataProviderOption[] | undefined,
): ComboboxOption[] {
	if (!options) return [];
	return options.map((opt) => ({
		value: opt.value,
		label: opt.label,
		...(opt.description ? { description: opt.description } : {}),
	}));
}

// Type guard to check if form_schema is a valid FormSchema
function isFormSchema(schema: unknown): schema is FormSchema {
	return (
		schema !== null &&
		typeof schema === "object" &&
		"fields" in schema &&
		Array.isArray((schema as FormSchema).fields)
	);
}

/**
 * Inner component that uses FormContext
 * Separated to allow FormContextProvider to wrap it
 */
function FormRendererInner({ form }: FormRendererProps) {
	const navigate = useNavigate();
	const submitForm = useSubmitForm();
	const { context, isFieldVisible, setFieldValue, isLoadingLaunchWorkflow } =
		useFormContext();

	// Execute launch workflow if configured
	useLaunchWorkflow({ form });

	// Get typed fields array - memoized to prevent unnecessary re-renders
	const fields = useMemo(
		() => (isFormSchema(form.form_schema) ? form.form_schema.fields : []),
		[form.form_schema],
	);

	// Single state object for all data provider state to batch updates
	const [dataProviderState, setDataProviderState] = useState<{
		options: Record<string, DataProviderOption[]>;
		loading: Record<string, boolean>;
		errors: Record<string, string>;
		successfullyLoaded: Set<string>;
	}>({
		options: {},
		loading: {},
		errors: {},
		successfullyLoaded: new Set(),
	});

	// Track which inputs we've attempted to load (to prevent infinite loops)
	const loadedInputsRef = useRef<Record<string, string>>({});

	// Track blur events to trigger data provider loading
	const fieldBlurTriggerRef = useRef<number>(0);

	// Track if initial load is complete
	const [hasCompletedInitialLoad, setHasCompletedInitialLoad] =
		useState(false);

	// Track navigation state to keep button disabled through redirect
	const [isNavigating, setIsNavigating] = useState(false);

	// Helper to evaluate data provider inputs (T040, T055, T075 - All three modes)
	const evaluateDataProviderInputs = useCallback(
		(
			field: FormField,
		): {
			inputs: Record<string, unknown> | null;
			hasAllRequired: boolean;
		} => {
			if (!field.data_provider_inputs)
				return { inputs: null, hasAllRequired: true };

			const inputValues: Record<string, unknown> = {};
			let hasAllRequired = true;

			Object.entries(field.data_provider_inputs).forEach(
				([key, config]: [string, DataProviderInputConfig]) => {
					switch (config.mode) {
						case "static":
							if (
								config.value !== null &&
								config.value !== undefined &&
								config.value !== ""
							) {
								inputValues[key] = config.value;
							}
							break;

						case "fieldRef":
							if (
								config.field_name &&
								context.field[config.field_name] !==
									undefined &&
								context.field[config.field_name] !== ""
							) {
								inputValues[key] =
									context.field[config.field_name];
							} else {
								hasAllRequired = false;
							}
							break;

						case "expression":
							if (config.expression) {
								try {
									// Simple expression evaluation using Function constructor
									// context.field.fieldName or context.workflow.property
									const evalFunc = new Function(
										"context",
										`return ${config.expression}`,
									);
									const result = evalFunc(context);
									if (result && result !== "") {
										inputValues[key] = result;
									} else {
										hasAllRequired = false;
									}
								} catch {
									hasAllRequired = false;
								}
							}
							break;
					}
				},
			);

			return {
				inputs:
					Object.keys(inputValues).length > 0 ? inputValues : null,
				hasAllRequired,
			};
		},
		[context],
	);

	// Function to load data providers (called on mount and blur events)
	const loadDataProviders = useCallback(async () => {
		const selectFields = fields.filter(
			(field: FormField) => field.data_provider_id,
		);

		for (const field of selectFields) {
			if (!field.data_provider_id || typeof field.data_provider_id !== "string")
				continue;

			const providerId = field.data_provider_id as string;
			const cacheKey = `${providerId}_${field.name}`;

			// Evaluate inputs to check if all required fields are available
			const { inputs, hasAllRequired } =
				evaluateDataProviderInputs(field);

			// Skip if we don't have all required inputs
			if (!hasAllRequired) {
				// Clear any existing options and errors
				setDataProviderState((prev) => ({
					...prev,
					options: {
						...prev.options,
						[cacheKey]: undefined,
					} as Record<string, DataProviderOption[]>,
					errors: { ...prev.errors, [cacheKey]: undefined } as Record<
						string,
						string
					>,
				}));
				continue;
			}

			// Create a hash of the inputs to detect changes
			const inputsHash = JSON.stringify(inputs || {});

			// Skip if we've already loaded with these exact inputs
			if (loadedInputsRef.current[cacheKey] === inputsHash) {
				continue;
			}

			// Skip if already loading
			if (dataProviderState.loading[cacheKey]) {
				continue;
			}

			try {
				// Set loading state
				setDataProviderState((prev) => ({
					...prev,
					loading: { ...prev.loading, [cacheKey]: true },
					errors: { ...prev.errors, [cacheKey]: undefined } as Record<
						string,
						string
					>,
				}));

				const options = await getDataProviderOptions(
					providerId,
					inputs || undefined,
				);

				loadedInputsRef.current[cacheKey] = inputsHash;

				// Update all state in one batch
				setDataProviderState((prev) => {
					const newSuccessfullyLoaded = new Set(
						prev.successfullyLoaded,
					);
					newSuccessfullyLoaded.add(cacheKey);
					return {
						options: { ...prev.options, [cacheKey]: options },
						loading: { ...prev.loading, [cacheKey]: false },
						errors: prev.errors,
						successfullyLoaded: newSuccessfullyLoaded,
					};
				});
			} catch {
				// Update error state in one batch
				setDataProviderState((prev) => ({
					...prev,
					loading: { ...prev.loading, [cacheKey]: false },
					errors: {
						...prev.errors,
						[cacheKey]: "Unable to load data",
					},
					options: {
						...prev.options,
						[cacheKey]: undefined,
					} as Record<string, DataProviderOption[]>,
				}));
			}
		}
	}, [
		fields,
		evaluateDataProviderInputs,
		dataProviderState.loading,
	]);

	// Load data providers on mount and when fieldBlurTrigger changes
	useEffect(() => {
		loadDataProviders().then(() => {
			// Mark initial load as complete after first load
			if (!hasCompletedInitialLoad) {
				setHasCompletedInitialLoad(true);
			}
		});
		// eslint-disable-next-line react-hooks/exhaustive-deps
	}, [fields, fieldBlurTriggerRef.current]);

	// Handler for field blur events
	const handleFieldBlur = useCallback(() => {
		// Increment trigger to cause useEffect to re-run
		fieldBlurTriggerRef.current += 1;
		loadDataProviders();
	}, [loadDataProviders]);

	// Build Zod schema dynamically from form fields
	// Note: This function is called on every render to ensure the latest dataProviderState is used
	// The schema is only evaluated during form submission, so this doesn't cause performance issues
	const buildSchema = useCallback(() => {
		const schemaFields: Record<string, z.ZodTypeAny> = {};

		fields.forEach((field: FormField) => {
			let fieldSchema: z.ZodTypeAny;

			switch (field.type) {
				case "email":
					fieldSchema = z.string().email("Invalid email address");
					break;
				case "number":
					fieldSchema = z.coerce.number();
					break;
				case "checkbox":
					fieldSchema = z.boolean();
					break;
				default:
					fieldSchema = z.string();
			}

			// Apply required validation
			if (field.required) {
				if (field.type === "checkbox") {
					fieldSchema = z.boolean().refine((val) => val === true, {
						message: "This field is required",
					});
				} else {
					fieldSchema = fieldSchema.refine((val) => val !== "", {
						message: "This field is required",
					});
				}
			} else {
				fieldSchema = fieldSchema.optional();
			}

			// Add validation for data provider fields with required inputs
			if (field.data_provider_id && field.data_provider_inputs) {
				const providerId = field.data_provider_id as string;
				const cacheKey = `${providerId}_${field.name}`;

				// Check if any inputs are required
				const hasRequiredInputs = Object.values(
					field.data_provider_inputs,
				).some((inputConfig: DataProviderInputConfig) => {
					// An input is considered "required" if it has a configuration
					// (all configured inputs must be satisfied for the provider to load)
					return (
						inputConfig.mode === "static" ||
						inputConfig.mode === "fieldRef" ||
						inputConfig.mode === "expression"
					);
				});

				if (hasRequiredInputs) {
					// Add refinement to check if data provider has successfully loaded
					fieldSchema = fieldSchema.superRefine((_val, ctx) => {
						if (
							!dataProviderState.successfullyLoaded.has(cacheKey)
						) {
							ctx.addIssue({
								code: z.ZodIssueCode.custom,
								message:
									"Data must be loaded before submitting. Please complete all required input fields.",
							});
						}
					});
				}
			}

			schemaFields[field.name] = fieldSchema;
		});

		return z.object(schemaFields);
	}, [fields, dataProviderState.successfullyLoaded]);

	// Create a custom resolver that calls buildSchema() to get the latest schema
	const customResolver = useCallback<Resolver<Record<string, unknown>>>(
		async (data, context, options) => {
			const schema = buildSchema();
			const resolver = zodResolver(schema);
			return resolver(data, context, options);
		},
		[buildSchema],
	);

	const {
		register,
		handleSubmit,
		formState: { errors, isValid },
		setValue,
		watch,
	} = useForm({
		resolver: customResolver,
		mode: "onChange", // Validate on change to keep isValid up-to-date
		defaultValues: fields.reduce(
			(acc: Record<string, unknown>, field: FormField) => {
				acc[field.name] =
					field.default_value ||
					(field.type === "checkbox" ? false : "");
				return acc;
			},
			{} as Record<string, unknown>,
		),
	});

	// Watch all field values and sync to FormContext for visibility evaluation
	// Use ref to track previous values to avoid infinite loops
	const formValues = watch();
	const prevValuesRef = useRef<Record<string, unknown>>({});

	useEffect(() => {
		// Track which fields changed
		const changedFields: string[] = [];

		// Only update fields that have actually changed
		Object.entries(formValues).forEach(([fieldName, value]) => {
			if (prevValuesRef.current[fieldName] !== value) {
				prevValuesRef.current[fieldName] = value;
				setFieldValue(fieldName, value);
				changedFields.push(fieldName);
			}
		});

		// Clear data provider data for any fields that depend on changed fields
		if (changedFields.length > 0) {
			const fieldsWithProviders = fields.filter(
				(field: FormField) =>
					field.data_provider_id && field.data_provider_inputs,
			);

			const fieldsToClear: string[] = [];

			fieldsWithProviders.forEach((field: FormField) => {
				// Check if this field depends on any of the changed fields
				Object.values(field.data_provider_inputs || {}).forEach(
					(inputConfig: DataProviderInputConfig) => {
						if (
							inputConfig.mode === "fieldRef" &&
							inputConfig.field_name
						) {
							if (
								changedFields.includes(inputConfig.field_name)
							) {
								const providerId =
									field.data_provider_id as string;
								const cacheKey = `${providerId}_${field.name}`;
								fieldsToClear.push(cacheKey);
							}
						}
					},
				);
			});

			// Clear data for dependent fields
			if (fieldsToClear.length > 0) {
				setDataProviderState((prev) => {
					const newOptions = { ...prev.options };
					const newSuccessfullyLoaded = new Set(
						prev.successfullyLoaded,
					);

					fieldsToClear.forEach((cacheKey) => {
						delete newOptions[cacheKey];
						newSuccessfullyLoaded.delete(cacheKey);
					});

					return {
						...prev,
						options: newOptions,
						successfullyLoaded: newSuccessfullyLoaded,
					};
				});
			}
		}
	}, [formValues, setFieldValue, fields]);

	const onSubmit = async (data: Record<string, unknown>) => {
		setIsNavigating(true);
		try {
			const result = await submitForm.mutateAsync({
				params: { path: { form_id: form.id } },
				body: data,
			});
			navigate(`/history/${result.execution_id}`);
			// Don't reset isNavigating - component will unmount on navigation
		} catch {
			setIsNavigating(false); // Only re-enable button on error
		}
	};

	// Props interface for DataProviderField
	interface DataProviderFieldProps {
		fieldName: string;
		fieldLabel: string | null;
		fieldRequired: boolean;
		fieldPlaceholder: string | null;
		fieldHelpText: string | null;
		options: ComboboxOption[];
		isLoading: boolean;
		error: { message?: string } | undefined;
		providerError: string | undefined;
		isEnabled: boolean;
		value: string;
		onValueChange: (value: string) => void;
	}

	// Memoized data provider field renderer - only re-renders when its specific data changes
	const DataProviderField = memo(
		({
			fieldName,
			fieldLabel,
			fieldRequired,
			fieldPlaceholder,
			fieldHelpText,
			options,
			isLoading,
			error: fieldError,
			providerError,
			isEnabled,
			value,
			onValueChange,
		}: DataProviderFieldProps) => (
			<div className="space-y-2">
				<Label htmlFor={fieldName}>
					{fieldLabel}
					{fieldRequired && (
						<span className="text-destructive ml-1">*</span>
					)}
				</Label>
				<Combobox
					id={fieldName}
					options={options && options.length > 0 ? options : []}
					value={value}
					onValueChange={onValueChange}
					placeholder={fieldPlaceholder || "Select an option..."}
					emptyText="No options available"
					isLoading={isLoading}
					disabled={!isEnabled || isLoading}
				/>
				{providerError && (
					<p className="text-sm text-destructive">{providerError}</p>
				)}
				{!providerError && fieldHelpText && (
					<p className="text-sm text-muted-foreground">
						{fieldHelpText}
					</p>
				)}
				{fieldError && (
					<p className="text-sm text-destructive">
						{fieldError.message as string}
					</p>
				)}
			</div>
		),
		(prevProps, nextProps) => {
			// Only re-render if these specific props change
			return (
				prevProps.fieldName === nextProps.fieldName &&
				prevProps.fieldLabel === nextProps.fieldLabel &&
				prevProps.fieldRequired === nextProps.fieldRequired &&
				prevProps.fieldPlaceholder === nextProps.fieldPlaceholder &&
				prevProps.fieldHelpText === nextProps.fieldHelpText &&
				prevProps.options === nextProps.options &&
				prevProps.isLoading === nextProps.isLoading &&
				prevProps.providerError === nextProps.providerError &&
				prevProps.isEnabled === nextProps.isEnabled &&
				prevProps.value === nextProps.value &&
				prevProps.error === nextProps.error &&
				prevProps.onValueChange === nextProps.onValueChange
			);
		},
	);

	DataProviderField.displayName = "DataProviderField";

	// Create stable callbacks for field value changes
	const fieldValueChangeCallbacks = useRef<
		Record<string, (value: string) => void>
	>({});

	const getFieldValueChangeCallback = useCallback(
		(fieldName: string) => {
			if (!fieldValueChangeCallbacks.current[fieldName]) {
				fieldValueChangeCallbacks.current[fieldName] = (
					value: string,
				) => setValue(fieldName, value, { shouldValidate: true });
			}
			return fieldValueChangeCallbacks.current[fieldName];
		},
		[setValue],
	);

	const renderField = (field: FormField) => {
		const error = errors[field.name];

		// If field has a data provider, render it as a dropdown regardless of type
		if (field.data_provider_id) {
			const providerId =
				typeof field.data_provider_id === "string"
					? field.data_provider_id
					: undefined;
			const cacheKey = providerId
				? `${providerId}_${field.name}`
				: undefined;
			const options = cacheKey ? dataProviderState.options[cacheKey] : [];
			const isLoadingOptions = cacheKey
				? dataProviderState.loading[cacheKey]
				: false;
			const providerError = cacheKey
				? dataProviderState.errors[cacheKey]
				: undefined;
			const hasSuccessfullyLoaded = cacheKey
				? dataProviderState.successfullyLoaded.has(cacheKey)
				: false;

			return (
				<DataProviderField
					fieldName={field.name}
					fieldLabel={field.label ?? null}
					fieldRequired={field.required ?? false}
					fieldPlaceholder={field.placeholder ?? null}
					fieldHelpText={field.help_text ?? null}
					options={toComboboxOptions(options)}
					isLoading={!!isLoadingOptions}
					error={error}
					providerError={providerError || undefined}
					isEnabled={hasSuccessfullyLoaded}
					value={(formValues[field.name] as string) || ""}
					onValueChange={getFieldValueChangeCallback(field.name)}
				/>
			);
		}

		switch (field.type) {
			case "textarea":
				return (
					<div className="space-y-2">
						<Label htmlFor={field.name}>
							{field.label}
							{field.required && (
								<span className="text-destructive ml-1">*</span>
							)}
						</Label>
						<Textarea
							id={field.name}
							placeholder={field.placeholder ?? undefined}
							{...register(field.name)}
							onBlur={handleFieldBlur}
						/>
						{field.help_text && (
							<p className="text-sm text-muted-foreground">
								{field.help_text}
							</p>
						)}
						{error && (
							<p className="text-sm text-destructive">
								{error.message as string}
							</p>
						)}
					</div>
				);

			case "checkbox":
				return (
					<div className="space-y-2">
						<div className="flex items-center space-x-2">
							<Checkbox
								id={field.name}
								onCheckedChange={(checked) =>
									setValue(field.name, checked, {
										shouldValidate: true,
									})
								}
							/>
							<Label
								htmlFor={field.name}
								className="cursor-pointer"
							>
								{field.label}
								{field.required && (
									<span className="text-destructive ml-1">
										*
									</span>
								)}
							</Label>
						</div>
						{field.help_text && (
							<p className="text-sm text-muted-foreground">
								{field.help_text}
							</p>
						)}
						{error && (
							<p className="text-sm text-destructive">
								{error.message as string}
							</p>
						)}
					</div>
				);

			case "select": {
				const providerId =
					typeof field.data_provider_id === "string"
						? field.data_provider_id
						: undefined;
				const cacheKey = providerId
					? `${providerId}_${field.name}`
					: undefined;
				const staticOptions = (field.options || []) as Array<{
					label: string;
					value: string;
				}>;
				const dynamicOptions = cacheKey
					? dataProviderState.options[cacheKey]
					: [];
				const options = providerId ? dynamicOptions : staticOptions;
				const isLoadingOptions = cacheKey
					? dataProviderState.loading[cacheKey]
					: false;
				const providerError = cacheKey
					? dataProviderState.errors[cacheKey]
					: undefined;
				const hasSuccessfullyLoaded = cacheKey
					? dataProviderState.successfullyLoaded.has(cacheKey)
					: true; // Static options are always "loaded"

				return (
					<div className="space-y-2">
						<Label htmlFor={field.name}>
							{field.label}
							{field.required && (
								<span className="text-destructive ml-1">*</span>
							)}
						</Label>
						<Combobox
							id={field.name}
							options={
								options && options.length > 0 ? options : []
							}
							value={formValues[field.name] as string}
							onValueChange={(value) =>
								setValue(field.name, value, {
									shouldValidate: true,
								})
							}
							placeholder={
								field.placeholder || "Select an option..."
							}
							emptyText="No options available"
							isLoading={!!isLoadingOptions}
							disabled={
								!!isLoadingOptions ||
								(!!providerId && !hasSuccessfullyLoaded)
							}
						/>
						{providerError && (
							<p className="text-sm text-destructive">
								{providerError}
							</p>
						)}
						{!providerError && field.help_text && (
							<p className="text-sm text-muted-foreground">
								{field.help_text}
							</p>
						)}
						{error && (
							<p className="text-sm text-destructive">
								{error.message as string}
							</p>
						)}
					</div>
				);
			}

			case "radio": {
				const radioOptions = (field.options || []) as Array<{
					label: string;
					value: string;
				}>;
				const defaultVal = field.default_value as
					| string
					| null
					| undefined;
				return (
					<div className="space-y-2">
						<Label>
							{field.label}
							{field.required && (
								<span className="text-destructive ml-1">*</span>
							)}
						</Label>
						<RadioGroup
							onValueChange={(value: string) =>
								setValue(field.name, value, {
									shouldValidate: true,
								})
							}
							{...(defaultVal
								? { defaultValue: defaultVal }
								: {})}
						>
							{radioOptions.map((option) => (
								<div
									key={option["value"]}
									className="flex items-center space-x-2"
								>
									<RadioGroupItem
										value={option["value"]}
										id={`${field.name}-${option["value"]}`}
									/>
									<Label
										htmlFor={`${field.name}-${option["value"]}`}
										className="cursor-pointer font-normal"
									>
										{option["label"]}
									</Label>
								</div>
							))}
						</RadioGroup>
						{field.help_text && (
							<p className="text-sm text-muted-foreground">
								{field.help_text}
							</p>
						)}
						{error && (
							<p className="text-sm text-destructive">
								{error.message as string}
							</p>
						)}
					</div>
				);
			}

			case "datetime":
				return (
					<div className="space-y-2">
						<Label htmlFor={field.name}>
							{field.label}
							{field.required && (
								<span className="text-destructive ml-1">*</span>
							)}
						</Label>
						<Input
							id={field.name}
							type="datetime-local"
							placeholder={field.placeholder ?? undefined}
							{...register(field.name)}
						/>
						{field.help_text && (
							<p className="text-sm text-muted-foreground">
								{field.help_text}
							</p>
						)}
						{error && (
							<p className="text-sm text-destructive">
								{error.message as string}
							</p>
						)}
					</div>
				);

			case "markdown":
				return (
					<div className="space-y-2">
						<div className="prose prose-sm max-w-none dark:prose-invert">
							{field.content ? (
								<ReactMarkdown
									components={{
										// Ensure headings render properly
										h1: ({ ...props }) => (
											<h1
												className="text-2xl font-bold mt-4 mb-2"
												{...props}
											/>
										),
										h2: ({ ...props }) => (
											<h2
												className="text-xl font-bold mt-3 mb-2"
												{...props}
											/>
										),
										h3: ({ ...props }) => (
											<h3
												className="text-lg font-bold mt-2 mb-1"
												{...props}
											/>
										),
										h4: ({ ...props }) => (
											<h4
												className="text-base font-bold mt-2 mb-1"
												{...props}
											/>
										),
										h5: ({ ...props }) => (
											<h5
												className="text-sm font-bold mt-1 mb-1"
												{...props}
											/>
										),
										h6: ({ ...props }) => (
											<h6
												className="text-xs font-bold mt-1 mb-1"
												{...props}
											/>
										),
									}}
								>
									{field.content}
								</ReactMarkdown>
							) : (
								<span className="text-muted-foreground italic">
									No content provided
								</span>
							)}
						</div>
						{field.help_text && (
							<p className="text-sm text-muted-foreground">
								{field.help_text}
							</p>
						)}
					</div>
				);

			case "html": {
				// Support both JSX templates and static HTML
				// HTML fields are display-only components and should not show labels
				const content =
					field.content ||
					'<p className="text-muted-foreground italic">No content provided</p>';

				// Check if content looks like JSX (contains React-style attributes or JSX expressions)
				const isJsxTemplate =
					content.includes("className=") ||
					content.includes("{context.");

				if (isJsxTemplate) {
					// Render as JSX template with full context access
					return (
						<div className="space-y-2">
							<JsxTemplateRenderer
								template={content}
								context={context}
							/>
							{field.help_text && (
								<p className="text-sm text-muted-foreground">
									{field.help_text}
								</p>
							)}
						</div>
					);
				} else {
					// Fallback to sanitized HTML for backwards compatibility
					const sanitizedHtml = DOMPurify.sanitize(content);
					return (
						<div className="space-y-2">
							<div
								className="border rounded-md p-4 bg-muted/30"
								dangerouslySetInnerHTML={{
									__html: sanitizedHtml,
								}}
							/>
							{field.help_text && (
								<p className="text-sm text-muted-foreground">
									{field.help_text}
								</p>
							)}
						</div>
					);
				}
			}

			case "file":
				return (
					<div className="space-y-2">
						<Label htmlFor={field.name}>
							{field.label}
							{field.required && (
								<span className="text-destructive ml-1">*</span>
							)}
						</Label>
						<div className="border-2 border-dashed rounded-lg p-6 hover:border-primary/50 transition-colors">
							<div className="flex flex-col items-center gap-2">
								<Upload className="h-8 w-8 text-muted-foreground" />
								<div className="text-center">
									<Label
										htmlFor={field.name}
										className="cursor-pointer text-sm font-medium text-primary hover:underline"
									>
										Choose file{field.multiple ? "s" : ""}
									</Label>
									<Input
										id={field.name}
										type="file"
										className="hidden"
										{...register(field.name)}
										accept={
											field.allowed_types?.join(",") ??
											undefined
										}
										multiple={field.multiple ?? undefined}
									/>
									<p className="text-xs text-muted-foreground mt-1">
										{field.allowed_types &&
										field.allowed_types.length > 0
											? `Allowed: ${field.allowed_types.join(", ")}`
											: "All file types allowed"}
										{field.max_size_mb &&
											` • Max ${field.max_size_mb}MB`}
									</p>
								</div>
							</div>
						</div>
						{field.help_text && (
							<p className="text-sm text-muted-foreground">
								{field.help_text}
							</p>
						)}
						{error && (
							<p className="text-sm text-destructive">
								{error.message as string}
							</p>
						)}
					</div>
				);

			default:
				return (
					<div className="space-y-2">
						<Label htmlFor={field.name}>
							{field.label}
							{field.required && (
								<span className="text-destructive ml-1">*</span>
							)}
						</Label>
						<Input
							id={field.name}
							type={
								field.type === "email"
									? "email"
									: field.type === "number"
										? "number"
										: "text"
							}
							placeholder={field.placeholder ?? undefined}
							{...register(field.name)}
							onBlur={handleFieldBlur}
						/>
						{field.help_text && (
							<p className="text-sm text-muted-foreground">
								{field.help_text}
							</p>
						)}
						{error && (
							<p className="text-sm text-destructive">
								{error.message as string}
							</p>
						)}
					</div>
				);
		}
	};

	// Filter fields by visibility
	// Context changes trigger re-evaluation through isFieldVisible
	const visibleFields = useMemo(() => {
		return fields.filter(isFieldVisible);
		// eslint-disable-next-line react-hooks/exhaustive-deps
	}, [fields, context]);

	// Show loading state while launch workflow executes or data providers load (only on initial load)
	const isAnyDataProviderLoading = Object.values(
		dataProviderState.loading,
	).some((loading) => loading);
	const showLoadingState =
		isLoadingLaunchWorkflow ||
		(!hasCompletedInitialLoad && isAnyDataProviderLoading);

	if (showLoadingState) {
		return (
			<div className="flex justify-center">
				<Card className="w-full max-w-2xl">
					<CardContent className="pt-6">
						<div className="space-y-6">
							{/* Loading indicator */}
							<div className="flex items-center gap-3 p-4 bg-muted/50 rounded-lg">
								<Loader2 className="h-5 w-5 animate-spin text-primary" />
								<div className="flex-1">
									<p className="text-sm font-medium">
										{isLoadingLaunchWorkflow
											? "Loading form data..."
											: "Loading form options..."}
									</p>
									<p className="text-xs text-muted-foreground mt-0.5">
										{isLoadingLaunchWorkflow
											? "Executing launch workflow to populate form context"
											: "Fetching dynamic options from data providers"}
									</p>
								</div>
							</div>

							{/* Skeleton loader for form fields */}
							<div className="space-y-4">
								<Skeleton className="h-12 w-full" />
								<Skeleton className="h-12 w-full" />
								<Skeleton className="h-24 w-full" />
								<Skeleton className="h-12 w-full" />
								<Skeleton className="h-10 w-32" />
							</div>
						</div>
					</CardContent>
				</Card>
			</div>
		);
	}

	return (
		<div className="flex justify-center">
			<Card className="w-full max-w-2xl">
				<CardContent className="pt-6">
					<form
						onSubmit={handleSubmit(onSubmit)}
						className="space-y-4"
					>
						<AnimatePresence mode="popLayout" initial={false}>
							{visibleFields.map((field: FormField) => (
								<motion.div
									key={field.name}
									initial={{
										opacity: 0,
										height: 0,
										marginBottom: 0,
									}}
									animate={{
										opacity: 1,
										height: "auto",
										marginBottom: 16,
									}}
									exit={{
										opacity: 0,
										height: 0,
										marginBottom: 0,
									}}
									transition={{
										opacity: { duration: 0.15 },
										height: {
											duration: 0.2,
											ease: "easeInOut",
										},
										marginBottom: {
											duration: 0.2,
											ease: "easeInOut",
										},
									}}
									style={{ overflow: "hidden" }}
								>
									{renderField(field)}
								</motion.div>
							))}
						</AnimatePresence>
						<div className="pt-4">
							<Button
								type="submit"
								disabled={
									!isValid ||
									submitForm.isPending ||
									isNavigating
								}
							>
								{submitForm.isPending || isNavigating
									? "Submitting..."
									: "Submit"}
							</Button>
						</div>
					</form>
				</CardContent>
			</Card>
		</div>
	);
}

/**
 * FormRenderer with FormContext wrapper
 * Extracts query parameters from URL and provides them to context
 */
export function FormRenderer({ form }: FormRendererProps) {
	const [searchParams] = useSearchParams();

	// Convert URLSearchParams to plain object
	const queryParams = useMemo(() => {
		const params: Record<string, string> = {};
		searchParams.forEach((value, key) => {
			params[key] = value;
		});
		return params;
	}, [searchParams]);

	return (
		<FormContextProvider form={form} queryParams={queryParams}>
			<FormRendererInner form={form} />
		</FormContextProvider>
	);
}

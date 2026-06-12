import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { components } from "@/lib/v1";

type WorkflowParameter = components["schemas"]["WorkflowParameter"];

interface InputMappingFormProps {
	parameters: WorkflowParameter[];
	values: Record<string, unknown>;
	onChange: (values: Record<string, unknown>) => void;
}

const TYPE_HINTS: Record<string, string> = {
	str: 'e.g. "hello" or {{ payload.name }}',
	string: 'e.g. "hello" or {{ payload.name }}',
	int: "e.g. 42 or {{ payload.count }}",
	float: "e.g. 3.14 or {{ payload.score }}",
	bool: "e.g. true or {{ payload.enabled }}",
	json: "e.g. {{ payload.data }}",
	dict: "e.g. {{ payload.data }}",
	list: "e.g. {{ payload.items }}",
	email: "e.g. user@example.com or {{ payload.email }}",
};

/**
 * Input mapping form for event subscriptions.
 *
 * Unlike WorkflowParametersForm, this renders ALL parameters as plain text
 * inputs so users can enter template expressions like {{ payload.field }}
 * regardless of the parameter's type.
 */
export function InputMappingForm({
	parameters,
	values,
	onChange,
}: InputMappingFormProps) {
	const handleChange = (paramName: string, value: string) => {
		onChange({
			...values,
			[paramName]: value || undefined,
		});
	};

	return (
		<div className="space-y-3">
			{parameters.map((param) => {
				const displayName = param.label || param.name;
				const hint =
					TYPE_HINTS[param.type ?? "str"] ?? TYPE_HINTS["str"];

				return (
					<div key={param.name} className="space-y-1.5">
						<Label
							htmlFor={`mapping-${param.name}`}
							className="text-sm"
						>
							{displayName}
							<span className="text-muted-foreground font-normal ml-1.5">
								({param.type ?? "str"})
							</span>
						</Label>
						<Input
							id={`mapping-${param.name}`}
							type="text"
							value={
								((values[param.name ?? ""] as string) ?? "")
							}
							onChange={(e) =>
								handleChange(param.name ?? "", e.target.value)
							}
							placeholder={hint}
						/>
						{param.description && (
							<p className="text-xs text-muted-foreground">
								{param.description}
							</p>
						)}
					</div>
				);
			})}
			<div className="rounded-md bg-muted/50 ring-1 ring-foreground/5 px-3 py-2 text-xs text-muted-foreground space-y-1">
				<p className="font-medium">Template variables:</p>
				<ul className="list-disc list-inside space-y-0.5">
					<li>
						<code className="bg-muted px-1 rounded">
							{"{{ payload }}"}
						</code>{" "}
						or{" "}
						<code className="bg-muted px-1 rounded">
							{"{{ payload.field }}"}
						</code>{" "}
						— event body
					</li>
					<li>
						<code className="bg-muted px-1 rounded">
							{"{{ headers.X-Something }}"}
						</code>{" "}
						— request headers
					</li>
					<li>
						<code className="bg-muted px-1 rounded">
							{"{{ scheduled_time }}"}
						</code>{" "}
						— schedule trigger time
					</li>
					<li>
						<code className="bg-muted px-1 rounded">
							{"{{ cron_expression }}"}
						</code>{" "}
						— cron expression
					</li>
				</ul>
				<p className="font-medium mt-2">
					Auto-injected context:
				</p>
				<p>
					Your workflow also receives{" "}
					<code className="bg-muted px-1 rounded">
						{"context.parameters[\"_event\"]"}
					</code>{" "}
					automatically with event metadata:{" "}
					<code className="bg-muted px-1 rounded">id</code>,{" "}
					<code className="bg-muted px-1 rounded">type</code>,{" "}
					<code className="bg-muted px-1 rounded">body</code>,{" "}
					<code className="bg-muted px-1 rounded">headers</code>,{" "}
					<code className="bg-muted px-1 rounded">received_at</code>,{" "}
					<code className="bg-muted px-1 rounded">source_ip</code>
				</p>
			</div>
		</div>
	);
}

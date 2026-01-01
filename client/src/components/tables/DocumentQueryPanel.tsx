import { useState } from "react";
import { Plus, Trash2, Search, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
	Select,
	SelectContent,
	SelectItem,
	SelectTrigger,
	SelectValue,
} from "@/components/ui/select";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import type { QueryOperator } from "@/services/tables";

interface FilterCondition {
	id: string;
	field: string;
	operator: QueryOperator;
	value: string;
}

interface DocumentQueryPanelProps {
	onApplyFilters: (where: Record<string, unknown>) => void;
	onClearFilters: () => void;
	hasActiveFilters: boolean;
}

const OPERATORS: { value: QueryOperator; label: string }[] = [
	{ value: "eq", label: "equals" },
	{ value: "ne", label: "not equals" },
	{ value: "contains", label: "contains" },
	{ value: "starts_with", label: "starts with" },
	{ value: "ends_with", label: "ends with" },
	{ value: "gt", label: "greater than" },
	{ value: "gte", label: "greater or equal" },
	{ value: "lt", label: "less than" },
	{ value: "lte", label: "less or equal" },
	{ value: "in", label: "in list (comma separated)" },
	{ value: "is_null", label: "is null" },
	{ value: "has_key", label: "has field" },
];

function generateId() {
	return Math.random().toString(36).substring(2, 9);
}

export function DocumentQueryPanel({
	onApplyFilters,
	onClearFilters,
	hasActiveFilters,
}: DocumentQueryPanelProps) {
	const [conditions, setConditions] = useState<FilterCondition[]>([]);
	const [isExpanded, setIsExpanded] = useState(false);

	const addCondition = () => {
		setConditions((prev) => [
			...prev,
			{
				id: generateId(),
				field: "",
				operator: "eq",
				value: "",
			},
		]);
		setIsExpanded(true);
	};

	const removeCondition = (id: string) => {
		setConditions((prev) => prev.filter((c) => c.id !== id));
	};

	const updateCondition = (
		id: string,
		updates: Partial<FilterCondition>,
	) => {
		setConditions((prev) =>
			prev.map((c) => (c.id === id ? { ...c, ...updates } : c)),
		);
	};

	const buildWhereClause = (): Record<string, unknown> => {
		const where: Record<string, unknown> = {};

		for (const condition of conditions) {
			if (!condition.field.trim()) continue;

			let value: unknown;

			switch (condition.operator) {
				case "is_null":
					value = { is_null: condition.value === "true" };
					break;
				case "has_key":
					value = { has_key: condition.value === "true" };
					break;
				case "in":
					value = {
						in: condition.value.split(",").map((v) => v.trim()),
					};
					break;
				case "eq":
					// Simple equality - just use the value directly
					value = condition.value;
					break;
				default:
					value = { [condition.operator]: condition.value };
			}

			where[condition.field] = value;
		}

		return where;
	};

	const handleApply = () => {
		const where = buildWhereClause();
		onApplyFilters(where);
	};

	const handleClear = () => {
		setConditions([]);
		onClearFilters();
	};

	return (
		<Card>
			<CardHeader className="py-3">
				<div className="flex items-center justify-between">
					<CardTitle className="text-sm font-medium flex items-center gap-2">
						<Search className="h-4 w-4" />
						Query Filters
						{hasActiveFilters && (
							<Badge variant="secondary" className="ml-2">
								Active
							</Badge>
						)}
					</CardTitle>
					<div className="flex items-center gap-2">
						{hasActiveFilters && (
							<Button
								variant="ghost"
								size="sm"
								onClick={handleClear}
							>
								<X className="h-4 w-4 mr-1" />
								Clear
							</Button>
						)}
						<Button variant="outline" size="sm" onClick={addCondition}>
							<Plus className="h-4 w-4 mr-1" />
							Add Filter
						</Button>
					</div>
				</div>
			</CardHeader>

			{(isExpanded || conditions.length > 0) && (
				<CardContent className="pt-0">
					<div className="space-y-3">
						{conditions.map((condition) => (
							<div
								key={condition.id}
								className="flex items-center gap-2"
							>
								<Input
									placeholder="Field name (e.g., status)"
									value={condition.field}
									onChange={(e) =>
										updateCondition(condition.id, {
											field: e.target.value,
										})
									}
									className="flex-1"
								/>
								<Select
									value={condition.operator}
									onValueChange={(value: QueryOperator) =>
										updateCondition(condition.id, {
											operator: value,
										})
									}
								>
									<SelectTrigger className="w-[180px]">
										<SelectValue />
									</SelectTrigger>
									<SelectContent>
										{OPERATORS.map((op) => (
											<SelectItem
												key={op.value}
												value={op.value}
											>
												{op.label}
											</SelectItem>
										))}
									</SelectContent>
								</Select>
								{condition.operator === "is_null" ||
								condition.operator === "has_key" ? (
									<Select
										value={condition.value || "true"}
										onValueChange={(value) =>
											updateCondition(condition.id, {
												value,
											})
										}
									>
										<SelectTrigger className="flex-1">
											<SelectValue />
										</SelectTrigger>
										<SelectContent>
											<SelectItem value="true">
												true
											</SelectItem>
											<SelectItem value="false">
												false
											</SelectItem>
										</SelectContent>
									</Select>
								) : (
									<Input
										placeholder="Value"
										value={condition.value}
										onChange={(e) =>
											updateCondition(condition.id, {
												value: e.target.value,
											})
										}
										className="flex-1"
									/>
								)}
								<Button
									variant="ghost"
									size="icon"
									onClick={() => removeCondition(condition.id)}
								>
									<Trash2 className="h-4 w-4" />
								</Button>
							</div>
						))}

						{conditions.length > 0 && (
							<div className="flex justify-end pt-2">
								<Button onClick={handleApply}>
									<Search className="h-4 w-4 mr-2" />
									Apply Filters
								</Button>
							</div>
						)}
					</div>
				</CardContent>
			)}
		</Card>
	);
}

/**
 * AskUserQuestionCard
 *
 * Inline card for handling SDK AskUserQuestion tool calls.
 * Displays questions with radio/checkbox options and an "Other" text input option.
 * Appears at the end of the chat message stream.
 */

import { useState, useCallback } from "react";
import { HelpCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import type { AskUserQuestion } from "@/services/websocket";

interface AskUserQuestionCardProps {
	questions: AskUserQuestion[];
	onSubmit: (answers: Record<string, string>) => void;
	onCancel: () => void;
}

interface QuestionState {
	selected: string[];
	otherText: string;
	showOther: boolean;
}

export function AskUserQuestionCard({
	questions,
	onSubmit,
	onCancel,
}: AskUserQuestionCardProps) {
	// Track state for each question
	const [questionStates, setQuestionStates] = useState<
		Record<string, QuestionState>
	>(() => {
		const initial: Record<string, QuestionState> = {};
		for (const q of questions) {
			initial[q.question] = {
				selected: [],
				otherText: "",
				showOther: false,
			};
		}
		return initial;
	});

	const handleSingleSelect = useCallback(
		(questionText: string, value: string) => {
			setQuestionStates((prev) => ({
				...prev,
				[questionText]: {
					...prev[questionText],
					selected: value === "__other__" ? [] : [value],
					showOther: value === "__other__",
				},
			}));
		},
		[],
	);

	const handleMultiSelect = useCallback(
		(questionText: string, value: string, checked: boolean) => {
			setQuestionStates((prev) => {
				const current = prev[questionText];
				let newSelected: string[];

				if (value === "__other__") {
					return {
						...prev,
						[questionText]: {
							...current,
							showOther: checked,
						},
					};
				}

				if (checked) {
					newSelected = [...current.selected, value];
				} else {
					newSelected = current.selected.filter((v) => v !== value);
				}

				return {
					...prev,
					[questionText]: {
						...current,
						selected: newSelected,
					},
				};
			});
		},
		[],
	);

	const handleOtherTextChange = useCallback(
		(questionText: string, text: string) => {
			setQuestionStates((prev) => ({
				...prev,
				[questionText]: {
					...prev[questionText],
					otherText: text,
				},
			}));
		},
		[],
	);

	const handleSubmit = useCallback(() => {
		const answers: Record<string, string> = {};

		for (const q of questions) {
			const state = questionStates[q.question];
			if (state.showOther && state.otherText.trim()) {
				// User selected "Other" and provided text
				if (q.multi_select) {
					// For multi-select, combine selected options with other text
					const allSelected = [
						...state.selected,
						state.otherText.trim(),
					];
					answers[q.question] = allSelected.join(", ");
				} else {
					answers[q.question] = state.otherText.trim();
				}
			} else if (state.selected.length > 0) {
				answers[q.question] = state.selected.join(", ");
			}
		}

		onSubmit(answers);
	}, [questions, questionStates, onSubmit]);

	// Check if all required questions have answers
	const isValid = questions.every((q) => {
		const state = questionStates[q.question];
		if (state.showOther) {
			return state.otherText.trim().length > 0;
		}
		return state.selected.length > 0;
	});

	return (
		<div className="border rounded-lg bg-card overflow-hidden border-primary/50 max-w-2xl">
			{/* Header */}
			<div className="flex items-center gap-2 px-4 py-3 bg-primary/5 border-b border-primary/20">
				<HelpCircle className="h-4 w-4 text-primary" />
				<span className="text-sm font-medium">
					Question from Assistant
				</span>
			</div>

			{/* Questions */}
			<div className="p-4 space-y-4">
				{questions.map((q) => (
					<div key={q.question} className="space-y-3">
						<div className="space-y-1">
							<span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
								{q.header}
							</span>
							<p className="text-sm font-medium">{q.question}</p>
						</div>

						{q.multi_select ? (
							// Multi-select with checkboxes
							<div className="space-y-2">
								{q.options.map((option) => (
									<div
										key={option.label}
										className="flex items-start space-x-3"
									>
										<Checkbox
											id={`${q.question}-${option.label}`}
											checked={questionStates[
												q.question
											]?.selected.includes(option.label)}
											onCheckedChange={(checked) =>
												handleMultiSelect(
													q.question,
													option.label,
													!!checked,
												)
											}
										/>
										<div className="space-y-0.5">
											<Label
												htmlFor={`${q.question}-${option.label}`}
												className="text-sm font-medium cursor-pointer"
											>
												{option.label}
											</Label>
											{option.description && (
												<p className="text-xs text-muted-foreground">
													{option.description}
												</p>
											)}
										</div>
									</div>
								))}
								{/* Other option */}
								<div className="flex items-start space-x-3">
									<Checkbox
										id={`${q.question}-other`}
										checked={
											questionStates[q.question]
												?.showOther
										}
										onCheckedChange={(checked) =>
											handleMultiSelect(
												q.question,
												"__other__",
												!!checked,
											)
										}
									/>
									<div className="flex-1 space-y-1">
										<Label
											htmlFor={`${q.question}-other`}
											className="text-sm font-medium cursor-pointer"
										>
											Other
										</Label>
										{questionStates[q.question]
											?.showOther && (
											<Input
												placeholder="Enter your response..."
												value={
													questionStates[q.question]
														?.otherText || ""
												}
												onChange={(e) =>
													handleOtherTextChange(
														q.question,
														e.target.value,
													)
												}
												className="mt-1"
												autoFocus
											/>
										)}
									</div>
								</div>
							</div>
						) : (
							// Single-select with radio buttons
							<RadioGroup
								value={
									questionStates[q.question]?.showOther
										? "__other__"
										: questionStates[q.question]
												?.selected[0] || ""
								}
								onValueChange={(value) =>
									handleSingleSelect(q.question, value)
								}
							>
								{q.options.map((option) => (
									<div
										key={option.label}
										className="flex items-start space-x-3"
									>
										<RadioGroupItem
											value={option.label}
											id={`${q.question}-${option.label}`}
										/>
										<div className="space-y-0.5">
											<Label
												htmlFor={`${q.question}-${option.label}`}
												className="text-sm font-medium cursor-pointer"
											>
												{option.label}
											</Label>
											{option.description && (
												<p className="text-xs text-muted-foreground">
													{option.description}
												</p>
											)}
										</div>
									</div>
								))}
								{/* Other option */}
								<div className="flex items-start space-x-3">
									<RadioGroupItem
										value="__other__"
										id={`${q.question}-other`}
									/>
									<div className="flex-1 space-y-1">
										<Label
											htmlFor={`${q.question}-other`}
											className="text-sm font-medium cursor-pointer"
										>
											Other
										</Label>
										{questionStates[q.question]
											?.showOther && (
											<Input
												placeholder="Enter your response..."
												value={
													questionStates[q.question]
														?.otherText || ""
												}
												onChange={(e) =>
													handleOtherTextChange(
														q.question,
														e.target.value,
													)
												}
												className="mt-1"
												autoFocus
											/>
										)}
									</div>
								</div>
							</RadioGroup>
						)}
					</div>
				))}
			</div>

			{/* Footer */}
			<div className="flex justify-end gap-2 px-4 py-3 bg-muted/30 border-t">
				<Button variant="ghost" size="sm" onClick={onCancel}>
					Cancel
				</Button>
				<Button size="sm" onClick={handleSubmit} disabled={!isValid}>
					Submit
				</Button>
			</div>
		</div>
	);
}

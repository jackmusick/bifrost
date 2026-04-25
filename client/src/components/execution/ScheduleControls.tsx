import * as React from "react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { DateTimePicker } from "@/components/ui/date-time-picker";

export interface Schedule {
	/** ISO-8601 UTC string, set when the user picks an absolute time. */
	scheduled_at?: string;
	/** Positive int seconds from submit; set for relative quick picks. */
	delay_seconds?: number;
}

export interface ScheduleControlsProps {
	/** null = "run now"; non-null = "run later" with either delay_seconds or scheduled_at set. */
	value: Schedule | null;
	onChange: (next: Schedule | null) => void;
	disabled?: boolean;
}

const DEFAULT_DELAY_SECONDS = 900; // 15 min — reasonable default on first check.
const MAX_DELAY_SECONDS = 365 * 24 * 60 * 60; // 1 year, matches backend.

function computeTomorrow9Am(now: Date): Date {
	const next = new Date(now);
	next.setDate(next.getDate() + 1);
	next.setHours(9, 0, 0, 0);
	return next;
}

function pickToIso(date: Date): string {
	return date.toISOString();
}

function matchesDelay(
	value: Schedule | null,
	seconds: number,
	toleranceSec = 30,
): boolean {
	if (!value || value.delay_seconds === undefined) return false;
	return Math.abs(value.delay_seconds - seconds) <= toleranceSec;
}

function matchesTomorrow9Am(value: Schedule | null, now: Date): boolean {
	if (!value || !value.scheduled_at) return false;
	const target = computeTomorrow9Am(now);
	try {
		return new Date(value.scheduled_at).getTime() === target.getTime();
	} catch {
		return false;
	}
}

interface QuickPick {
	label: string;
	/** Called with the live "now" so Tomorrow 9 AM is computed at click time. */
	toSchedule: (now: Date) => Schedule;
	isActive: (value: Schedule | null, now: Date) => boolean;
}

const QUICK_PICKS: QuickPick[] = [
	{
		label: "In 15 min",
		toSchedule: () => ({ delay_seconds: 900 }),
		isActive: (v) => matchesDelay(v, 900),
	},
	{
		label: "In 1 hour",
		toSchedule: () => ({ delay_seconds: 3600 }),
		isActive: (v) => matchesDelay(v, 3600),
	},
	{
		label: "In 4 hours",
		toSchedule: () => ({ delay_seconds: 4 * 3600 }),
		isActive: (v) => matchesDelay(v, 4 * 3600),
	},
	{
		label: "Tomorrow 9 AM",
		toSchedule: (now) => ({ scheduled_at: pickToIso(computeTomorrow9Am(now)) }),
		isActive: (v, now) => matchesTomorrow9Am(v, now),
	},
];

export function ScheduleControls({
	value,
	onChange,
	disabled,
}: ScheduleControlsProps): React.JSX.Element {
	const checked = value !== null;
	// Snapshot "now" once per render so quick-pick activity checks are stable
	// within a paint, but we use a fresh Date() when the user actually clicks.
	const now = new Date();

	const handleCheckedChange = (next: boolean | "indeterminate") => {
		if (next === true) {
			onChange({ delay_seconds: DEFAULT_DELAY_SECONDS });
		} else {
			onChange(null);
		}
	};

	const handleQuickPick = (pick: QuickPick) => {
		onChange(pick.toSchedule(new Date()));
	};

	const handlePickerChange = (date: Date | null) => {
		if (!date) return;
		onChange({ scheduled_at: pickToIso(date) });
	};

	const pickerValue = value?.scheduled_at
		? new Date(value.scheduled_at)
		: null;

	const minDate = new Date(now.getTime() + 60_000);
	const maxDate = new Date(now.getTime() + MAX_DELAY_SECONDS * 1000);

	const scheduledInPast =
		value?.scheduled_at !== undefined &&
		new Date(value.scheduled_at).getTime() < now.getTime();

	return (
		<div className="flex flex-col gap-3">
			<Label className="flex items-center gap-2">
				<Checkbox
					checked={checked}
					onCheckedChange={handleCheckedChange}
					disabled={disabled}
					aria-label="Schedule for later"
				/>
				<span>Schedule for later</span>
			</Label>

			{checked && (
				<div className="flex flex-col gap-3 pl-6">
					<div className="flex flex-wrap gap-2">
						{QUICK_PICKS.map((pick) => {
							const active = pick.isActive(value, now);
							return (
								<Button
									key={pick.label}
									type="button"
									size="sm"
									variant={active ? "default" : "outline"}
									aria-pressed={active}
									disabled={disabled}
									onClick={() => handleQuickPick(pick)}
								>
									{pick.label}
								</Button>
							);
						})}
					</div>

					<div className="flex flex-col gap-1.5">
						<span className="text-sm text-muted-foreground">
							Or pick a specific time:
						</span>
						<DateTimePicker
							value={pickerValue}
							onChange={handlePickerChange}
							minDate={minDate}
							maxDate={maxDate}
							disabled={disabled}
						/>
					</div>

					{scheduledInPast && (
						<p
							className={cn(
								"text-sm text-destructive",
								"mt-0.5",
							)}
							role="alert"
						>
							Time is in the past
						</p>
					)}
				</div>
			)}
		</div>
	);
}

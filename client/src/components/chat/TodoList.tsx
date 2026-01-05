/**
 * TodoList Component
 *
 * Displays a persistent checklist from the SDK's TodoWrite tool.
 * Shows task progress with status icons and animations.
 */

import { useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Circle, CircleDot, CheckCircle2, ListTodo } from "lucide-react";
import { cn } from "@/lib/utils";
import type { TodoItem } from "@/services/websocket";

interface TodoListProps {
	todos: TodoItem[];
	className?: string;
}

/** Status icon component with appropriate styling */
function StatusIcon({ status }: { status: TodoItem["status"] }) {
	switch (status) {
		case "pending":
			return (
				<Circle className="h-4 w-4 text-muted-foreground flex-shrink-0" />
			);
		case "in_progress":
			return (
				<motion.div
					animate={{ rotate: 360 }}
					transition={{
						duration: 2,
						repeat: Infinity,
						ease: "linear",
					}}
				>
					<CircleDot className="h-4 w-4 text-primary flex-shrink-0" />
				</motion.div>
			);
		case "completed":
			return (
				<CheckCircle2 className="h-4 w-4 text-green-500 flex-shrink-0" />
			);
	}
}

/** Individual todo item with animation */
function TodoItemRow({ todo, index }: { todo: TodoItem; index: number }) {
	const isInProgress = todo.status === "in_progress";
	const isCompleted = todo.status === "completed";

	return (
		<motion.div
			initial={{ opacity: 0, x: -10 }}
			animate={{ opacity: 1, x: 0 }}
			exit={{ opacity: 0, x: 10 }}
			transition={{ delay: index * 0.05 }}
			className={cn(
				"flex items-start gap-2 py-1.5 px-2 rounded-md transition-colors",
				isInProgress && "bg-primary/5",
				isCompleted && "opacity-60",
			)}
		>
			<div className="mt-0.5">
				<StatusIcon status={todo.status} />
			</div>
			<div className="flex-1 min-w-0">
				<span
					className={cn(
						"text-sm leading-relaxed",
						isCompleted && "line-through text-muted-foreground",
						isInProgress && "font-medium text-foreground",
					)}
				>
					{isInProgress ? todo.active_form : todo.content}
				</span>
			</div>
		</motion.div>
	);
}

export function TodoList({ todos, className }: TodoListProps) {
	// Calculate progress
	const progress = useMemo(() => {
		if (todos.length === 0) return { completed: 0, total: 0, percent: 0 };
		const completed = todos.filter((t) => t.status === "completed").length;
		return {
			completed,
			total: todos.length,
			percent: Math.round((completed / todos.length) * 100),
		};
	}, [todos]);

	if (todos.length === 0) {
		return null;
	}

	return (
		<div
			className={cn(
				"border rounded-lg bg-card overflow-hidden max-w-2xl",
				className,
			)}
		>
			{/* Header with progress */}
			<div className="flex items-center justify-between px-4 py-2.5 bg-muted/30 border-b">
				<div className="flex items-center gap-2">
					<ListTodo className="h-4 w-4 text-muted-foreground" />
					<span className="text-sm font-medium">Task Progress</span>
				</div>
				<div className="flex items-center gap-2">
					<span className="text-xs text-muted-foreground">
						{progress.completed}/{progress.total}
					</span>
					{/* Progress bar */}
					<div className="w-16 h-1.5 bg-muted rounded-full overflow-hidden">
						<motion.div
							className="h-full bg-primary rounded-full"
							initial={{ width: 0 }}
							animate={{ width: `${progress.percent}%` }}
							transition={{ duration: 0.3 }}
						/>
					</div>
				</div>
			</div>

			{/* Todo items */}
			<div className="p-2 space-y-0.5 max-h-64 overflow-y-auto scrollbar-thin scrollbar-thumb-muted scrollbar-track-transparent">
				<AnimatePresence mode="popLayout">
					{todos.map((todo, index) => (
						<TodoItemRow
							key={`${todo.content}-${index}`}
							todo={todo}
							index={index}
						/>
					))}
				</AnimatePresence>
			</div>
		</div>
	);
}

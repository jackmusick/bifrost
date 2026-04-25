import { ThumbsUp, ThumbsDown } from "lucide-react";
import { cn } from "@/lib/utils";

export type Verdict = "up" | "down" | null;

export interface VerdictToggleProps {
  value: Verdict;
  onChange: (v: Verdict) => void;
  disabled?: boolean;
  size?: "sm" | "md";
  className?: string;
}

export function VerdictToggle({
  value,
  onChange,
  disabled,
  size = "md",
  className,
}: VerdictToggleProps) {
  function toggle(target: "up" | "down") {
    if (disabled) return;
    onChange(value === target ? null : target);
  }

  const dim = size === "sm" ? 28 : 32;
  const iconSize = size === "sm" ? 14 : 16;

  return (
    <div className={cn("inline-flex gap-1.5", className)} role="group" aria-label="Verdict">
      <button
        type="button"
        aria-label="Mark as good"
        aria-pressed={value === "up"}
        disabled={disabled}
        onClick={() => toggle("up")}
        className={cn(
          "grid place-items-center rounded-full border transition-all",
          "hover:scale-110 active:scale-95",
          value === "up"
            ? "bg-emerald-500/15 border-emerald-500 text-emerald-600 dark:text-emerald-400"
            : "bg-background border-border text-muted-foreground hover:text-foreground",
          disabled && "opacity-50 cursor-not-allowed hover:scale-100",
        )}
        style={{ width: dim, height: dim }}
      >
        <ThumbsUp size={iconSize} />
      </button>
      <button
        type="button"
        aria-label="Mark as bad"
        aria-pressed={value === "down"}
        disabled={disabled}
        onClick={() => toggle("down")}
        className={cn(
          "grid place-items-center rounded-full border transition-all",
          "hover:scale-110 active:scale-95",
          value === "down"
            ? "bg-rose-500/15 border-rose-500 text-rose-600 dark:text-rose-400"
            : "bg-background border-border text-muted-foreground hover:text-foreground",
          disabled && "opacity-50 cursor-not-allowed hover:scale-100",
        )}
        style={{ width: dim, height: dim }}
      >
        <ThumbsDown size={iconSize} />
      </button>
    </div>
  );
}

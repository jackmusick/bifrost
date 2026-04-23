import { Send } from "lucide-react";
import { useState } from "react";
import { cn } from "@/lib/utils";

export interface ChatComposerProps {
  placeholder?: string;
  onSend: (text: string) => void;
  pending?: boolean;
  className?: string;
  autoFocus?: boolean;
}

export function ChatComposer({
  placeholder = "Type a message...",
  onSend,
  pending = false,
  className,
  autoFocus,
}: ChatComposerProps) {
  const [value, setValue] = useState("");

  function submit() {
    if (!value.trim() || pending) return;
    onSend(value.trim());
    setValue("");
  }

  return (
    <div
      className={cn(
        "flex items-end gap-2 rounded-[20px] border bg-background px-4 py-2.5 transition-all",
        "focus-within:border-primary focus-within:ring-2 focus-within:ring-primary/20",
        className,
      )}
    >
      <textarea
        autoFocus={autoFocus}
        placeholder={placeholder}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            submit();
          }
        }}
        className="flex-1 resize-none border-none bg-transparent text-sm outline-none placeholder:text-muted-foreground min-h-[22px] max-h-[180px] py-0.5"
        rows={1}
      />
      <button
        type="button"
        onClick={submit}
        disabled={!value.trim() || pending}
        aria-label="Send"
        className={cn(
          "w-[30px] h-[30px] rounded-full grid place-items-center transition-colors shrink-0",
          "bg-primary text-primary-foreground hover:bg-primary/90",
          "disabled:bg-muted disabled:text-muted-foreground disabled:cursor-not-allowed",
        )}
      >
        <Send size={13} />
      </button>
    </div>
  );
}

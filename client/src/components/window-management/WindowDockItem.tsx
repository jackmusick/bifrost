// client/src/components/window-management/WindowDockItem.tsx

import { motion } from "framer-motion";
import { Loader2 } from "lucide-react";
import { dockItemVariants, windowTransition } from "./animations";
import type { DockItem } from "./types";

type WindowDockItemProps = DockItem;

/**
 * Individual item in the window dock bar.
 * Shows icon, label, and loading state.
 */
export function WindowDockItem({
  id: _id,
  icon,
  label,
  isLoading,
  onRestore,
}: WindowDockItemProps) {
  return (
    <motion.button
      layout
      variants={dockItemVariants}
      initial="hidden"
      animate="visible"
      exit="exit"
      transition={windowTransition}
      onClick={onRestore}
      className="flex items-center gap-2 rounded-2xl bg-background px-3 py-2 shadow-lg ring-1 ring-foreground/5 dark:ring-foreground/10 hover:bg-muted hover:scale-[1.02] transition-all duration-150"
      whileHover={{ scale: 1.02 }}
      whileTap={{ scale: 0.98 }}
    >
      {isLoading ? (
        <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
      ) : (
        <span className="h-4 w-4 flex items-center justify-center text-muted-foreground">
          {icon}
        </span>
      )}
      <span className="text-sm font-medium truncate max-w-[150px]">
        {label}
      </span>
    </motion.button>
  );
}

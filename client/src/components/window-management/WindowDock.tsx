import { AnimatePresence, motion } from "framer-motion";
import { dockVariants, windowTransition } from "./animations";
import { WindowDockItem } from "./WindowDockItem";
import type { DockItem } from "./types";

interface WindowDockProps {
  /** Items to display in the dock */
  items: DockItem[];
}

/**
 * Unified dock bar for all minimized windows.
 * Appears fixed at bottom-right when any items are present.
 */
export function WindowDock({ items }: WindowDockProps) {
  if (items.length === 0) {
    return null;
  }

  return (
    <motion.div
      className="fixed bottom-4 right-4 z-50 flex gap-2"
      variants={dockVariants}
      initial="hidden"
      animate="visible"
      transition={windowTransition}
    >
      <AnimatePresence mode="popLayout">
        {items.map((item) => (
          <WindowDockItem key={item.id} {...item} />
        ))}
      </AnimatePresence>
    </motion.div>
  );
}

// client/src/components/window-management/WindowOverlay.tsx

import { motion } from "framer-motion";
import { overlayVariants, windowTransition } from "./animations";

interface WindowOverlayProps {
  children: React.ReactNode;
}

/**
 * Animated fullscreen overlay wrapper for maximized windows.
 * Provides consistent enter/exit animations.
 */
export function WindowOverlay({ children }: WindowOverlayProps) {
  return (
    <motion.div
      className="fixed inset-0 z-[100] bg-background"
      variants={overlayVariants}
      initial="hidden"
      animate="visible"
      exit="hidden"
      transition={windowTransition}
      style={{ originX: 1, originY: 1 }}
    >
      {children}
    </motion.div>
  );
}

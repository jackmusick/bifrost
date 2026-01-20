// client/src/components/window-management/animations.ts

/**
 * Framer Motion animation variants for window management
 */

import type { Variants, Transition } from "framer-motion";

/** Standard easing for window animations */
export const windowTransition: Transition = {
  duration: 0.2,
  ease: "easeOut",
};

/** Overlay animation variants (maximize/minimize) */
export const overlayVariants: Variants = {
  hidden: {
    opacity: 0,
    scale: 0.95,
  },
  visible: {
    opacity: 1,
    scale: 1,
  },
};

/** Dock bar animation variants (slide up from bottom) */
export const dockVariants: Variants = {
  hidden: {
    opacity: 0,
    y: 20,
  },
  visible: {
    opacity: 1,
    y: 0,
  },
};

/** Dock item animation variants (for AnimatePresence) */
export const dockItemVariants: Variants = {
  hidden: {
    opacity: 0,
    scale: 0.8,
    x: 20,
  },
  visible: {
    opacity: 1,
    scale: 1,
    x: 0,
  },
  exit: {
    opacity: 0,
    scale: 0.8,
    x: -20,
  },
};

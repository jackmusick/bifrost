/**
 * Shared types for window management (dock, overlays)
 */

export interface DockItem {
  /** Unique identifier for the dock item */
  id: string;
  /** Icon to display (React node) */
  icon: React.ReactNode;
  /** Label to display */
  label: string;
  /** Whether this item has activity in progress (shows spinner) */
  isLoading?: boolean;
  /** Callback when item is clicked to restore */
  onRestore: () => void;
}

export type OverlayLayoutMode = "maximized" | "minimized" | null;

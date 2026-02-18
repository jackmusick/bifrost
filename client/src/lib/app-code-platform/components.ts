/**
 * App Code Platform Component Library
 *
 * Exposes UI components to the runtime for use in user-authored code.
 * These components come from our shadcn/ui based component library.
 *
 * All components maintain their original props interface and can be used
 * directly in code without imports.
 */

// =============================================================================
// Layout Components
// =============================================================================

import {
	Card,
	CardHeader,
	CardFooter,
	CardTitle,
	CardAction,
	CardDescription,
	CardContent,
} from "@/components/ui/card";

// =============================================================================
// Form Components
// =============================================================================

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
	Select,
	SelectContent,
	SelectGroup,
	SelectItem,
	SelectLabel,
	SelectTrigger,
	SelectValue,
	SelectSeparator,
} from "@/components/ui/select";
import { Checkbox } from "@/components/ui/checkbox";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Combobox } from "@/components/ui/combobox";
import { MultiCombobox } from "@/components/ui/multi-combobox";
import { TagsInput } from "@/components/ui/tags-input";

// =============================================================================
// Display Components
// =============================================================================

import { Badge } from "@/components/ui/badge";
import { Avatar, AvatarImage, AvatarFallback } from "@/components/ui/avatar";
import { Alert, AlertTitle, AlertDescription } from "@/components/ui/alert";
import { Skeleton } from "@/components/ui/skeleton";
import { Progress } from "@/components/ui/progress";

// =============================================================================
// Navigation Components
// =============================================================================

import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import {
	Pagination,
	PaginationContent,
	PaginationEllipsis,
	PaginationItem,
	PaginationLink,
	PaginationNext,
	PaginationPrevious,
} from "@/components/ui/pagination";

// =============================================================================
// Feedback Components
// =============================================================================

import {
	Dialog,
	DialogClose,
	DialogContent,
	DialogDescription,
	DialogFooter,
	DialogHeader,
	DialogTitle,
	DialogTrigger,
} from "@/components/ui/dialog";

import {
	AlertDialog,
	AlertDialogTrigger,
	AlertDialogContent,
	AlertDialogHeader,
	AlertDialogFooter,
	AlertDialogTitle,
	AlertDialogDescription,
	AlertDialogAction,
	AlertDialogCancel,
} from "@/components/ui/alert-dialog";

import {
	Tooltip,
	TooltipContent,
	TooltipProvider,
	TooltipTrigger,
} from "@/components/ui/tooltip";

import {
	Popover,
	PopoverContent,
	PopoverTrigger,
	PopoverAnchor,
} from "@/components/ui/popover";

// Calendar and Date Components
import { Calendar as CalendarPicker } from "@/components/ui/calendar";
import { DateRangePicker } from "@/components/ui/date-range-picker";

// Toast notifications via Sonner
import { toast } from "sonner";

// Utilities - date-fns
import { format } from "date-fns";

// =============================================================================
// Data Display Components
// =============================================================================

import {
	Table,
	TableHeader,
	TableBody,
	TableFooter,
	TableHead,
	TableRow,
	TableCell,
	TableCaption,
} from "@/components/ui/table";

// =============================================================================
// App Code Components Export
// =============================================================================

/**
 * Object containing all UI components available to user code.
 *
 * This is merged into the platform scope so users can write:
 * ```jsx
 * <Card>
 *   <CardHeader>
 *     <CardTitle>My Card</CardTitle>
 *   </CardHeader>
 *   <CardContent>
 *     <Button onClick={() => toast.success('Clicked!')}>
 *       Click me
 *     </Button>
 *   </CardContent>
 * </Card>
 * ```
 */
export const APP_CODE_COMPONENTS = {
	// Layout
	Card,
	CardHeader,
	CardFooter,
	CardTitle,
	CardAction,
	CardDescription,
	CardContent,

	// Forms
	Button,
	Input,
	Select,
	SelectContent,
	SelectGroup,
	SelectItem,
	SelectLabel,
	SelectTrigger,
	SelectValue,
	SelectSeparator,
	Checkbox,
	Textarea,
	Label,
	Switch,
	RadioGroup,
	RadioGroupItem,
	Combobox,
	MultiCombobox,
	TagsInput,

	// Display
	Badge,
	Avatar,
	AvatarImage,
	AvatarFallback,
	Alert,
	AlertTitle,
	AlertDescription,
	Skeleton,
	Progress,

	// Navigation
	Tabs,
	TabsList,
	TabsTrigger,
	TabsContent,
	Pagination,
	PaginationContent,
	PaginationEllipsis,
	PaginationItem,
	PaginationLink,
	PaginationNext,
	PaginationPrevious,

	// Feedback - Dialog
	Dialog,
	DialogClose,
	DialogContent,
	DialogDescription,
	DialogFooter,
	DialogHeader,
	DialogTitle,
	DialogTrigger,

	// Feedback - Alert Dialog
	AlertDialog,
	AlertDialogTrigger,
	AlertDialogContent,
	AlertDialogHeader,
	AlertDialogFooter,
	AlertDialogTitle,
	AlertDialogDescription,
	AlertDialogAction,
	AlertDialogCancel,

	// Feedback - Tooltip
	Tooltip,
	TooltipContent,
	TooltipProvider,
	TooltipTrigger,

	// Feedback - Popover
	Popover,
	PopoverContent,
	PopoverTrigger,
	PopoverAnchor,

	// Feedback - Toast (function, not component)
	toast,

	// Data Display
	Table,
	TableHeader,
	TableBody,
	TableFooter,
	TableHead,
	TableRow,
	TableCell,
	TableCaption,

	// Calendar and Date
	CalendarPicker,
	DateRangePicker,

	// Utilities
	format,
} as const;

/**
 * Type for the app code components object.
 * Useful for type checking and IDE support.
 */
export type AppCodeComponents = typeof APP_CODE_COMPONENTS;

// =============================================================================
// Re-exports for convenience
// =============================================================================

// Layout
export {
	Card,
	CardHeader,
	CardFooter,
	CardTitle,
	CardAction,
	CardDescription,
	CardContent,
};

// Forms
export { Button };
export { Input };
export {
	Select,
	SelectContent,
	SelectGroup,
	SelectItem,
	SelectLabel,
	SelectTrigger,
	SelectValue,
	SelectSeparator,
};
export { Checkbox };
export { Textarea };
export { Label };
export { Switch };
export { RadioGroup, RadioGroupItem };
export { Combobox };
export { MultiCombobox };
export { TagsInput };

// Display
export { Badge };
export { Avatar, AvatarImage, AvatarFallback };
export { Alert, AlertTitle, AlertDescription };
export { Skeleton };
export { Progress };

// Navigation
export { Tabs, TabsList, TabsTrigger, TabsContent };
export {
	Pagination,
	PaginationContent,
	PaginationEllipsis,
	PaginationItem,
	PaginationLink,
	PaginationNext,
	PaginationPrevious,
};

// Feedback
export {
	Dialog,
	DialogClose,
	DialogContent,
	DialogDescription,
	DialogFooter,
	DialogHeader,
	DialogTitle,
	DialogTrigger,
};

export {
	AlertDialog,
	AlertDialogTrigger,
	AlertDialogContent,
	AlertDialogHeader,
	AlertDialogFooter,
	AlertDialogTitle,
	AlertDialogDescription,
	AlertDialogAction,
	AlertDialogCancel,
};

export { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger };

export { Popover, PopoverContent, PopoverTrigger, PopoverAnchor };

export { toast };

// Data Display
export {
	Table,
	TableHeader,
	TableBody,
	TableFooter,
	TableHead,
	TableRow,
	TableCell,
	TableCaption,
};

// Calendar and Date
export { Calendar as CalendarPicker } from "@/components/ui/calendar";
export { DateRangePicker };

// Utilities
export { format };

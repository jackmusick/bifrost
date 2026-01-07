/**
 * Organization Select Component
 *
 * A reusable select component for choosing an organization scope.
 * Platform admins can select "Global" (null) or any organization.
 * Org users should have this component hidden with their org pre-selected.
 */

import { Building2, Globe, Star } from "lucide-react";
import {
	Select,
	SelectContent,
	SelectGroup,
	SelectItem,
	SelectLabel,
	SelectSeparator,
	SelectTrigger,
	SelectValue,
} from "@/components/ui/select";
import { useOrganizations } from "@/hooks/useOrganizations";
import type { components } from "@/lib/v1";

type Organization = components["schemas"]["OrganizationPublic"];

export interface OrganizationSelectProps {
	/** Selected organization ID, null for global scope, or undefined for all */
	value: string | null | undefined;
	/** Callback when selection changes */
	onChange: (value: string | null | undefined) => void;
	/** Whether the select is disabled */
	disabled?: boolean;
	/** Custom label for the field */
	label?: string;
	/** Whether to show the "Global" option (default true) */
	showGlobal?: boolean;
	/** Whether to show the "All organizations" option for filtering (default false) */
	showAll?: boolean;
	/** Placeholder text when nothing is selected */
	placeholder?: string;
}

// Special values for the Select (since null/undefined aren't valid values)
const GLOBAL_VALUE = "__GLOBAL__";
const ALL_VALUE = "__ALL__";

export function OrganizationSelect({
	value,
	onChange,
	disabled = false,
	showGlobal = true,
	showAll = false,
	placeholder = "Select organization...",
}: OrganizationSelectProps) {
	const { data: organizations, isLoading } = useOrganizations();

	// Convert null/undefined to our special values for the Select component
	const selectValue =
		value === undefined ? ALL_VALUE : value === null ? GLOBAL_VALUE : value;

	const handleValueChange = (newValue: string) => {
		// Convert our special values back to null/undefined
		if (newValue === ALL_VALUE) {
			onChange(undefined);
		} else if (newValue === GLOBAL_VALUE) {
			onChange(null);
		} else {
			onChange(newValue);
		}
	};

	// Find the selected organization for display
	const selectedOrg = organizations?.find(
		(org: Organization) => org.id === value,
	);

	return (
		<Select
			value={selectValue}
			onValueChange={handleValueChange}
			disabled={disabled || isLoading}
		>
			<SelectTrigger className="w-full">
				<SelectValue
					placeholder={isLoading ? "Loading..." : placeholder}
				>
					{value === undefined && showAll ? (
						<span>All</span>
					) : value === null ? (
						<div className="flex items-center gap-2">
							<Globe className="h-4 w-4 text-muted-foreground" />
							<span>Global</span>
						</div>
					) : selectedOrg ? (
						<div className="flex items-center gap-2">
							{selectedOrg.is_provider ? (
								<Star className="h-4 w-4 text-amber-500 fill-amber-500" />
							) : (
								<Building2 className="h-4 w-4 text-muted-foreground" />
							)}
							<span>{selectedOrg.name}</span>
						</div>
					) : (
						placeholder
					)}
				</SelectValue>
			</SelectTrigger>
			<SelectContent>
				{showAll && (
					<>
						<SelectGroup>
							<SelectItem value={ALL_VALUE}>
								<div className="flex flex-col">
									<span className="font-medium">All</span>
									<span className="text-xs text-muted-foreground">
										Show all organizations
									</span>
								</div>
							</SelectItem>
						</SelectGroup>
						<SelectSeparator />
					</>
				)}
				{showGlobal && (
					<>
						<SelectGroup>
							<SelectItem value={GLOBAL_VALUE}>
								<div className="flex items-center gap-2">
									<Globe className="h-4 w-4 text-muted-foreground" />
									<div className="flex flex-col">
										<span className="font-medium">
											Global
										</span>
										<span className="text-xs text-muted-foreground">
											Available to all organizations
										</span>
									</div>
								</div>
							</SelectItem>
						</SelectGroup>
						<SelectSeparator />
					</>
				)}
				<SelectGroup>
					<SelectLabel>Organizations</SelectLabel>
					{isLoading ? (
						<SelectItem value="loading" disabled>
							Loading organizations...
						</SelectItem>
					) : organizations && organizations.length > 0 ? (
						organizations.map((org: Organization) => (
							<SelectItem key={org.id} value={org.id}>
								<div className="flex items-center gap-2">
									{org.is_provider ? (
										<Star className="h-4 w-4 text-amber-500 fill-amber-500" />
									) : (
										<Building2 className="h-4 w-4 text-muted-foreground" />
									)}
									<div className="flex flex-col">
										<span className="flex items-center gap-2">
											{org.name}
											{org.is_provider && (
												<span className="text-xs text-amber-600 font-medium">
													Provider
												</span>
											)}
										</span>
										{org.domain && (
											<span className="text-xs text-muted-foreground">
												@{org.domain}
											</span>
										)}
									</div>
								</div>
							</SelectItem>
						))
					) : (
						<SelectItem value="none" disabled>
							No organizations available
						</SelectItem>
					)}
				</SelectGroup>
			</SelectContent>
		</Select>
	);
}

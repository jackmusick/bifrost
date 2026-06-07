/**
 * Solution Detail Page (basic)
 *
 * Resolves the /solutions/:solutionId route end-to-end: fetches the install's
 * owned entities + config status and renders them as simple lists. Task 19
 * replaces the body with the polished tabbed view.
 */

import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
	ChevronLeft,
	Globe,
	Building2,
	GitBranch,
	HardDriveUpload,
	Workflow,
	AppWindow,
	FileCode,
	Bot,
	Database,
	CheckCircle2,
	Circle,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useOrganizations } from "@/hooks/useOrganizations";
import {
	getSolutionEntities,
	type SolutionEntities,
} from "@/services/solutions";

type EntitySummary = NonNullable<SolutionEntities["workflows"]>;

function EntityList({
	icon: Icon,
	title,
	items,
}: {
	icon: typeof Workflow;
	title: string;
	items: EntitySummary | undefined;
}) {
	return (
		<Card>
			<CardHeader className="pb-2">
				<CardTitle className="flex items-center gap-2 text-sm font-semibold">
					<Icon className="h-4 w-4 text-muted-foreground" />
					{title}
					<span className="text-muted-foreground">
						({items?.length ?? 0})
					</span>
				</CardTitle>
			</CardHeader>
			<CardContent>
				{items && items.length > 0 ? (
					<ul className="space-y-1 text-sm">
						{items.map((item) => (
							<li key={item.id} className="truncate">
								{item.name}
							</li>
						))}
					</ul>
				) : (
					<p className="text-sm italic text-muted-foreground/60">
						None
					</p>
				)}
			</CardContent>
		</Card>
	);
}

export function SolutionDetail() {
	const { solutionId } = useParams<{ solutionId: string }>();
	const { data: organizations } = useOrganizations();

	const { data, isLoading, error } = useQuery({
		queryKey: ["solutions", solutionId, "entities"],
		queryFn: () => getSolutionEntities(solutionId!),
		enabled: !!solutionId,
	});

	const sol = data?.solution;
	const orgName = sol?.organization_id
		? (organizations?.find((o) => o.id === sol.organization_id)?.name ??
			sol.organization_id)
		: "Global";

	return (
		<div className="h-full flex flex-col space-y-6 max-w-7xl mx-auto">
			<div>
				<Link
					to="/solutions"
					className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
				>
					<ChevronLeft className="h-4 w-4" />
					Solutions
				</Link>
			</div>

			{isLoading ? (
				<div className="space-y-4">
					<Skeleton className="h-10 w-64" />
					<div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
						{[...Array(3)].map((_, i) => (
							<Skeleton key={i} className="h-32 w-full" />
						))}
					</div>
				</div>
			) : error ? (
				<Card>
					<CardContent className="py-10 text-center text-sm text-destructive">
						{error instanceof Error
							? error.message
							: "Failed to load Solution"}
					</CardContent>
				</Card>
			) : data && sol ? (
				<>
					<div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
						<div>
							<h1 className="text-3xl font-extrabold tracking-tight">
								{sol.name}
							</h1>
							<p className="mt-1 text-sm text-muted-foreground">
								{sol.slug}
							</p>
						</div>
						<div className="flex flex-wrap items-center gap-2">
							<Badge
								variant={
									sol.organization_id ? "outline" : "default"
								}
								className="gap-1"
							>
								{sol.organization_id ? (
									<Building2 className="h-3 w-3" />
								) : (
									<Globe className="h-3 w-3" />
								)}
								{orgName}
							</Badge>
							<Badge variant="secondary" className="gap-1">
								{sol.git_connected ? (
									<GitBranch className="h-3 w-3" />
								) : (
									<HardDriveUpload className="h-3 w-3" />
								)}
								{sol.git_connected ? "Git" : "Manual"}
							</Badge>
						</div>
					</div>

					<div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
						<EntityList
							icon={Workflow}
							title="Workflows"
							items={data.workflows}
						/>
						<EntityList
							icon={AppWindow}
							title="Apps"
							items={data.apps}
						/>
						<EntityList
							icon={FileCode}
							title="Forms"
							items={data.forms}
						/>
						<EntityList
							icon={Bot}
							title="Agents"
							items={data.agents}
						/>
						<EntityList
							icon={Database}
							title="Tables"
							items={data.tables}
						/>
						<Card>
							<CardHeader className="pb-2">
								<CardTitle className="flex items-center gap-2 text-sm font-semibold">
									<Database className="h-4 w-4 text-muted-foreground" />
									Configs
									<span className="text-muted-foreground">
										({data.configs?.length ?? 0})
									</span>
								</CardTitle>
							</CardHeader>
							<CardContent>
								{data.configs && data.configs.length > 0 ? (
									<ul className="space-y-1 text-sm">
										{data.configs.map((cfg) => (
											<li
												key={cfg.id}
												className="flex items-center gap-2"
											>
												{cfg.value_set ? (
													<CheckCircle2 className="h-3.5 w-3.5 text-green-600" />
												) : (
													<Circle className="h-3.5 w-3.5 text-muted-foreground" />
												)}
												<span className="truncate font-mono text-xs">
													{cfg.key}
												</span>
												{cfg.required &&
													!cfg.value_set && (
														<span className="text-xs text-yellow-600">
															required
														</span>
													)}
											</li>
										))}
									</ul>
								) : (
									<p className="text-sm italic text-muted-foreground/60">
										None
									</p>
								)}
							</CardContent>
						</Card>
					</div>
				</>
			) : null}
		</div>
	);
}

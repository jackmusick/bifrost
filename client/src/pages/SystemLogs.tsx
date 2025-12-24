import { useState, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import { useSystemLogs } from "@/hooks/useSystemLogs";
import { getErrorMessage } from "@/lib/api-error";
import { LogDetailsDialog } from "@/components/logs/LogDetailsDialog";
import {
	DataTable,
	DataTableBody,
	DataTableCell,
	DataTableHead,
	DataTableHeader,
	DataTableRow,
} from "@/components/ui/data-table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import {
	Select,
	SelectContent,
	SelectItem,
	SelectTrigger,
	SelectValue,
} from "@/components/ui/select";
import {
	Card,
	CardContent,
	CardDescription,
	CardHeader,
	CardTitle,
} from "@/components/ui/card";
import {
	RefreshCw,
	ChevronLeft,
	ChevronRight,
	AlertCircle,
	Loader2,
} from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import type { SystemLog, GetSystemLogsParams } from "@/hooks/useSystemLogs";

const CATEGORIES = [
	"All",
	"discovery",
	"organization",
	"user",
	"role",
	"config",
	"secret",
	"form",
	"oauth",
	"system",
	"error",
];

const LEVELS = ["All", "error", "warning", "info", "critical"];

export default function SystemLogs() {
	const { isPlatformAdmin } = useAuth();
	const navigate = useNavigate();

	const [selectedLevel, setSelectedLevel] = useState("All");
	const [selectedCategory, setSelectedCategory] = useState("All");
	const [searchText, setSearchText] = useState("");
	const [startDate, setStartDate] = useState("");
	const [endDate, setEndDate] = useState("");
	const [selectedLog, setSelectedLog] = useState<SystemLog | null>(null);
	const [dialogOpen, setDialogOpen] = useState(false);
	const [continuationTokens, setContinuationTokens] = useState<string[]>([]);
	const [currentPage, setCurrentPage] = useState(0);

	// Build query params
	const queryParams = useMemo(() => {
		const params: GetSystemLogsParams = { limit: 50 };
		if (selectedCategory !== "All") params.category = selectedCategory;
		if (selectedLevel !== "All") params.level = selectedLevel.toLowerCase();
		if (startDate) params.startDate = startDate;
		if (endDate) params.endDate = endDate;
		if (continuationTokens[currentPage])
			params.continuationToken = continuationTokens[currentPage];
		return params;
	}, [
		selectedCategory,
		selectedLevel,
		startDate,
		endDate,
		currentPage,
		continuationTokens,
	]);

	const { data, isLoading, error, refetch } = useSystemLogs(queryParams);

	// Client-side filter for search text (must be declared before any conditional returns)
	const filteredLogs = useMemo(() => {
		if (!data?.logs) return [];
		if (!searchText) return data.logs;

		const search = searchText.toLowerCase();
		return data.logs.filter(
			(log: SystemLog) =>
				log.message.toLowerCase().includes(search) ||
				log.category.toLowerCase().includes(search) ||
				(log.executed_by &&
					log.executed_by.toLowerCase().includes(search)),
		);
	}, [data, searchText]);

	// Check admin access (after all hooks are called)
	if (!isPlatformAdmin) {
		return (
			<div className="container mx-auto py-8">
				<Alert variant="destructive">
					<AlertCircle className="h-4 w-4" />
					<AlertDescription>
						You do not have permission to view system logs. Platform
						administrator access is required.
					</AlertDescription>
				</Alert>
				<Button onClick={() => navigate("/")} className="mt-4">
					Return to Dashboard
				</Button>
			</div>
		);
	}

	const handleRowClick = (log: SystemLog) => {
		setSelectedLog(log);
		setDialogOpen(true);
	};

	const handleNextPage = () => {
		if (data?.continuation_token) {
			const newTokens = [...continuationTokens];
			newTokens[currentPage + 1] = data.continuation_token;
			setContinuationTokens(newTokens);
			setCurrentPage(currentPage + 1);
		}
	};

	const handlePreviousPage = () => {
		if (currentPage > 0) {
			setCurrentPage(currentPage - 1);
		}
	};

	const getLevelBadgeVariant = (level: string) => {
		switch (level.toLowerCase()) {
			case "error":
				return "destructive";
			case "warning":
				return "warning";
			case "critical":
				return "destructive";
			default:
				return "default";
		}
	};

	const truncateMessage = (message: string, maxLength: number = 100) => {
		if (message.length <= maxLength) return message;
		return message.substring(0, maxLength) + "...";
	};

	return (
		<div className="flex flex-col h-[calc(100vh-8rem)] space-y-6">
			{/* Header */}
			<div className="flex-shrink-0">
				<div className="flex items-center justify-between">
					<div>
						<h1 className="text-4xl font-extrabold tracking-tight">
							System Logs
						</h1>
						<p className="mt-2 text-muted-foreground">
							View and search system activity logs
						</p>
					</div>
				</div>
			</div>

			<Card className="flex-1 flex flex-col overflow-hidden">
				<CardHeader className="flex-shrink-0">
					<div className="flex items-center justify-between">
						<div>
							<CardTitle>All Logs</CardTitle>
							<CardDescription>
								{filteredLogs.length > 0 && (
									<span>
										Showing {filteredLogs.length} log
										{filteredLogs.length !== 1
											? "s"
											: ""}{" "}
										on this page
										{data?.continuation_token &&
											" (more available)"}
									</span>
								)}
								{filteredLogs.length === 0 &&
									"Recent system activity and audit logs"}
							</CardDescription>
						</div>
						<div className="flex items-center gap-2">
							<Button
								variant="outline"
								size="icon"
								onClick={() => refetch()}
								disabled={isLoading}
							>
								<RefreshCw
									className={`h-4 w-4 ${isLoading ? "animate-spin" : ""}`}
								/>
							</Button>
						</div>
					</div>
				</CardHeader>

				<CardContent className="flex-1 overflow-hidden flex flex-col">
					<Tabs
						defaultValue="All"
						value={selectedLevel}
						onValueChange={setSelectedLevel}
						className="flex flex-col flex-1 overflow-hidden"
					>
						<div className="flex-shrink-0 space-y-4 mb-4">
							<div className="flex items-center gap-4">
								{/* Category Select */}
								<Select
									value={selectedCategory}
									onValueChange={setSelectedCategory}
								>
									<SelectTrigger className="w-[180px]">
										<SelectValue placeholder="Category" />
									</SelectTrigger>
									<SelectContent>
										{CATEGORIES.map((category) => (
											<SelectItem
												key={category}
												value={category}
												className="capitalize"
											>
												{category}
											</SelectItem>
										))}
									</SelectContent>
								</Select>

								{/* Search Input */}
								<Input
									placeholder="Search messages..."
									value={searchText}
									onChange={(e) =>
										setSearchText(e.target.value)
									}
									className="flex-1 max-w-md"
								/>

								{/* Date Range */}
								<Input
									type="date"
									value={startDate}
									onChange={(e) =>
										setStartDate(e.target.value)
									}
									className="w-[160px]"
									placeholder="Start Date"
								/>
								<Input
									type="date"
									value={endDate}
									onChange={(e) => setEndDate(e.target.value)}
									className="w-[160px]"
									placeholder="End Date"
								/>
							</div>

							{/* Level Filter Tabs */}
							<TabsList>
								{LEVELS.map((level) => (
									<TabsTrigger
										key={level}
										value={level}
										className="capitalize"
									>
										{level}
									</TabsTrigger>
								))}
							</TabsList>
						</div>

						<TabsContent
							value={selectedLevel}
							className="mt-0 flex-1 overflow-auto"
						>
							{/* Error State */}
							{error && (
								<Alert variant="destructive" className="mb-4">
									<AlertCircle className="h-4 w-4" />
									<AlertDescription>
										Failed to load system logs:{" "}
										{getErrorMessage(
											error,
											"Unknown error",
										)}
									</AlertDescription>
								</Alert>
							)}

							{isLoading && !filteredLogs.length ? (
								<div className="flex items-center justify-center py-12">
									<Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
								</div>
							) : filteredLogs.length > 0 ? (
								<div className="border rounded-lg overflow-hidden h-full">
									<div className="h-full overflow-auto">
										<DataTable className="relative w-full caption-bottom text-sm">
											<DataTableHeader className="sticky top-0 bg-background/80 backdrop-blur-sm z-10">
												<DataTableRow>
													<DataTableHead>
														Timestamp
													</DataTableHead>
													<DataTableHead>
														Level
													</DataTableHead>
													<DataTableHead>
														Category
													</DataTableHead>
													<DataTableHead>
														Summary
													</DataTableHead>
													<DataTableHead>
														Executed By
													</DataTableHead>
												</DataTableRow>
											</DataTableHeader>
											<DataTableBody>
												{filteredLogs.map(
													(
														log: SystemLog,
														index: number,
													) => (
														<DataTableRow
															key={`${log.category}_${log.event_id}_${index}`}
															clickable
															onClick={() =>
																handleRowClick(
																	log,
																)
															}
														>
															<DataTableCell className="font-mono text-sm">
																{new Date(
																	log.timestamp,
																).toLocaleString()}
															</DataTableCell>
															<DataTableCell>
																<Badge
																	variant={getLevelBadgeVariant(
																		log.level,
																	)}
																	className="capitalize"
																>
																	{log.level}
																</Badge>
															</DataTableCell>
															<DataTableCell>
																<Badge
																	variant="secondary"
																	className="capitalize"
																>
																	{
																		log.category
																	}
																</Badge>
															</DataTableCell>
															<DataTableCell className="max-w-md">
																{truncateMessage(
																	log.message,
																)}
															</DataTableCell>
															<DataTableCell className="text-sm text-muted-foreground">
																{log.executed_by_name ||
																	log.executed_by ||
																	"-"}
															</DataTableCell>
														</DataTableRow>
													),
												)}
											</DataTableBody>
										</DataTable>
									</div>

									{/* Pagination */}
									<div className="border-t bg-background px-4 py-3 flex items-center justify-between">
										<div className="text-sm text-muted-foreground">
											{filteredLogs.length > 0 &&
												`${filteredLogs.length} log${filteredLogs.length !== 1 ? "s" : ""} on this page`}
										</div>
										<div className="flex gap-2">
											<Button
												variant="outline"
												size="sm"
												onClick={handlePreviousPage}
												disabled={currentPage === 0}
											>
												<ChevronLeft className="h-4 w-4 mr-2" />
												Previous
											</Button>
											<Button
												variant="outline"
												size="sm"
												onClick={handleNextPage}
												disabled={
													!data?.continuation_token
												}
											>
												Next
												<ChevronRight className="h-4 w-4 ml-2" />
											</Button>
										</div>
									</div>
								</div>
							) : (
								<div className="flex items-center justify-center py-12 text-center">
									<div>
										<h3 className="text-lg font-semibold">
											No logs found
										</h3>
										<p className="mt-2 text-sm text-muted-foreground">
											Try adjusting your filters or search
											criteria
										</p>
									</div>
								</div>
							)}
						</TabsContent>
					</Tabs>
				</CardContent>
			</Card>

			{/* Details Dialog */}
			<LogDetailsDialog
				log={selectedLog}
				open={dialogOpen}
				onOpenChange={setDialogOpen}
			/>
		</div>
	);
}

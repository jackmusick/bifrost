import { useEffect } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { BasicInfo } from "@/pages/user-settings/BasicInfo";
import { DeveloperSettings } from "@/pages/user-settings/Developer";

export function UserSettings() {
	const navigate = useNavigate();
	const location = useLocation();

	// Parse the current tab from the URL path
	const currentTab =
		location.pathname.split("/user-settings/")[1] || "basic-info";

	const handleTabChange = (value: string) => {
		navigate(`/user-settings/${value}`);
	};

	// Redirect /user-settings to /user-settings/basic-info
	useEffect(() => {
		if (location.pathname === "/user-settings") {
			navigate("/user-settings/basic-info", { replace: true });
		}
	}, [location.pathname, navigate]);

	return (
		<div className="max-w-3xl mx-auto space-y-6">
			<div>
				<h1 className="text-4xl font-extrabold tracking-tight">
					User Settings
				</h1>
				<p className="mt-2 text-muted-foreground">
					Manage your profile and developer settings
				</p>
			</div>

			<Tabs value={currentTab} onValueChange={handleTabChange}>
				<TabsList>
					<TabsTrigger value="basic-info">Basic Info</TabsTrigger>
					<TabsTrigger value="developer">Developer</TabsTrigger>
				</TabsList>

				<TabsContent value="basic-info" className="mt-6">
					<BasicInfo />
				</TabsContent>

				<TabsContent value="developer" className="mt-6">
					<DeveloperSettings />
				</TabsContent>
			</Tabs>
		</div>
	);
}

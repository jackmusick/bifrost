import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import "./index.css";

import { Layout } from "./Layout";
import { Index } from "./routes/Index";
import { Sidebar } from "./routes/Sidebar";
import { Header } from "./routes/Header";
import { ModelPicker } from "./routes/ModelPicker";
import { AdminSettings } from "./routes/AdminSettings";
import { Attachments } from "./routes/Attachments";
import { EditRetry } from "./routes/EditRetry";
import { Compaction } from "./routes/Compaction";
import { Delegation } from "./routes/Delegation";
import { WorkspaceSettings } from "./routes/WorkspaceSettings";
import { FullChat } from "./routes/FullChat";

ReactDOM.createRoot(document.getElementById("root")!).render(
	<React.StrictMode>
		<BrowserRouter>
			<Routes>
				<Route element={<Layout />}>
					<Route index element={<Index />} />
					<Route path="full" element={<FullChat />} />
					<Route path="sidebar" element={<Sidebar />} />
					<Route path="header" element={<Header />} />
					<Route path="picker" element={<ModelPicker />} />
					<Route path="workspace-settings" element={<WorkspaceSettings />} />
					<Route path="admin-settings" element={<AdminSettings />} />
					<Route path="attachments" element={<Attachments />} />
					<Route path="edit-retry" element={<EditRetry />} />
					<Route path="compaction" element={<Compaction />} />
					<Route path="delegation" element={<Delegation />} />
				</Route>
			</Routes>
		</BrowserRouter>
	</React.StrictMode>,
);

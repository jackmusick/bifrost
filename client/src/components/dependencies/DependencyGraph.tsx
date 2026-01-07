/**
 * DependencyGraph - React Flow visualization component
 *
 * Renders a directed graph of entity dependencies using React Flow
 * with automatic layout via dagre.
 */

import { useMemo, useEffect } from "react";
import {
	ReactFlow,
	Background,
	Controls,
	MiniMap,
	useNodesState,
	useEdgesState,
	type Edge,
	type Node,
	MarkerType,
	Panel,
} from "@xyflow/react";
import dagre from "dagre";
import "@xyflow/react/dist/style.css";
import "./dependency-graph.css";

import { EntityNode, type EntityNodeData, type EntityType } from "./EntityNode";
import type { GraphNode, GraphEdge } from "@/hooks/useDependencyGraph";
import { cn } from "@/lib/utils";

// Node types for React Flow
const nodeTypes = {
	entity: EntityNode,
};

// Layout configuration
const NODE_WIDTH = 200;
const NODE_HEIGHT = 100;

interface DependencyGraphProps {
	nodes: GraphNode[];
	edges: GraphEdge[];
	rootId: string;
	className?: string;
}

/**
 * Apply dagre layout to position nodes in a hierarchical structure
 */
function getLayoutedElements(
	nodes: Node[],
	edges: Edge[],
	direction: "TB" | "LR" = "TB",
): { nodes: Node[]; edges: Edge[] } {
	const dagreGraph = new dagre.graphlib.Graph();
	dagreGraph.setDefaultEdgeLabel(() => ({}));
	dagreGraph.setGraph({
		rankdir: direction,
		nodesep: 80,
		ranksep: 100,
		marginx: 50,
		marginy: 50,
	});

	// Add nodes to dagre
	nodes.forEach((node) => {
		dagreGraph.setNode(node.id, { width: NODE_WIDTH, height: NODE_HEIGHT });
	});

	// Add edges to dagre
	edges.forEach((edge) => {
		dagreGraph.setEdge(edge.source, edge.target);
	});

	// Run layout
	dagre.layout(dagreGraph);

	// Get positioned nodes
	const layoutedNodes = nodes.map((node) => {
		const nodeWithPosition = dagreGraph.node(node.id);
		return {
			...node,
			position: {
				x: nodeWithPosition.x - NODE_WIDTH / 2,
				y: nodeWithPosition.y - NODE_HEIGHT / 2,
			},
		};
	});

	return { nodes: layoutedNodes, edges };
}

/**
 * Convert API response to React Flow nodes and edges
 */
function convertToFlowElements(
	apiNodes: GraphNode[],
	apiEdges: GraphEdge[],
	rootId: string,
): { nodes: Node[]; edges: Edge[] } {
	// Convert API nodes to React Flow nodes
	const nodes: Node[] = apiNodes.map((node) => ({
		id: node.id,
		type: "entity",
		position: { x: 0, y: 0 }, // Will be set by layout
		data: {
			label: node.name,
			entityType: node.type as EntityType,
			orgId: node.org_id ?? null,
			isRoot: node.id === rootId,
		} satisfies EntityNodeData,
	}));

	// Convert API edges to React Flow edges
	const edges: Edge[] = apiEdges.map((edge, index) => ({
		id: `edge-${index}`,
		source: edge.source,
		target: edge.target,
		type: "smoothstep",
		animated: true, // Animated to make edges more visible
		style: {
			strokeWidth: 2,
			stroke: "#6b7280", // Gray color that's visible in both themes
		},
		markerEnd: {
			type: MarkerType.ArrowClosed,
			width: 20,
			height: 20,
			color: "#6b7280",
		},
		label: edge.relationship,
		labelStyle: {
			fontSize: 11,
			fontWeight: 500,
			fill: "#374151",
		},
		labelBgStyle: {
			fill: "#ffffff",
			fillOpacity: 0.9,
		},
		labelBgPadding: [4, 8] as [number, number],
		labelBgBorderRadius: 4,
	}));

	return { nodes, edges };
}

export function DependencyGraph({
	nodes: apiNodes,
	edges: apiEdges,
	rootId,
	className,
}: DependencyGraphProps) {
	// Convert and layout the graph
	const { nodes: initialNodes, edges: initialEdges } = useMemo(() => {
		const { nodes, edges } = convertToFlowElements(apiNodes, apiEdges, rootId);
		return getLayoutedElements(nodes, edges, "TB");
	}, [apiNodes, apiEdges, rootId]);

	const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
	const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

	// Sync state when initial data changes (e.g., different entity selected)
	useEffect(() => {
		setNodes(initialNodes);
		setEdges(initialEdges);
	}, [initialNodes, initialEdges, setNodes, setEdges]);

	return (
		<div className={cn("w-full h-full", className)}>
			<ReactFlow
				nodes={nodes}
				edges={edges}
				onNodesChange={onNodesChange}
				onEdgesChange={onEdgesChange}
				nodeTypes={nodeTypes}
				fitView
				fitViewOptions={{
					padding: 0.2,
					maxZoom: 1.5,
				}}
				minZoom={0.1}
				maxZoom={2}
				proOptions={{ hideAttribution: true }}
				nodesDraggable={false}
				nodesConnectable={false}
				elementsSelectable={true}
				panOnScroll={true}
				zoomOnScroll={true}
			>
				<Background gap={16} size={1} />
				<Controls showInteractive={false} />
				<MiniMap
					nodeStrokeWidth={3}
					maskColor="rgba(128, 128, 128, 0.3)"
					nodeColor={(node) => {
						const data = node.data as EntityNodeData;
						switch (data.entityType) {
							case "workflow":
								return "#3b82f6";
							case "form":
								return "#22c55e";
							case "app":
								return "#a855f7";
							case "agent":
								return "#f97316";
							default:
								return "#6b7280";
						}
					}}
				/>
				<Panel position="top-right">
					<div className="bg-background/80 backdrop-blur-sm rounded-lg border p-3 shadow-sm">
						<div className="text-xs font-medium mb-2 text-muted-foreground">
							Legend
						</div>
						<div className="flex flex-col gap-1.5">
							<div className="flex items-center gap-2 text-xs">
								<div className="w-3 h-3 rounded bg-blue-500" />
								<span>Workflow</span>
							</div>
							<div className="flex items-center gap-2 text-xs">
								<div className="w-3 h-3 rounded bg-green-500" />
								<span>Form</span>
							</div>
							<div className="flex items-center gap-2 text-xs">
								<div className="w-3 h-3 rounded bg-purple-500" />
								<span>App</span>
							</div>
							<div className="flex items-center gap-2 text-xs">
								<div className="w-3 h-3 rounded bg-orange-500" />
								<span>Agent</span>
							</div>
						</div>
					</div>
				</Panel>
			</ReactFlow>
		</div>
	);
}

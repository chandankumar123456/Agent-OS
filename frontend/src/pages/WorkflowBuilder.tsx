import { useState, useCallback, useRef, useEffect } from 'react';
import {
 ReactFlow,
 Background,
 Controls,
 MiniMap,
 useNodesState,
 useEdgesState,
 addEdge,
 useReactFlow,
 ReactFlowProvider,
} from '@xyflow/react';
import type { Edge, Node } from '@xyflow/react';
import '@xyflow/react/dist/style.css';

// @xyflow/react v12 removed the Connection export; define locally
interface Connection {
 source: string | null;
 target: string | null;
 sourceHandle?: string | null;
 targetHandle?: string | null;
}

import {
 Save,
 Play,
 Download,
 Upload,
 Trash2,
 GitBranch,
 Bot,
 Wrench,
 ShieldAlert,
} from 'lucide-react';
import { apiClient } from '../api/client';

const nodeTypes = {
 agent: AgentNode,
 tool: ToolNode,
 decision: DecisionNode,
 wait: WaitNode,
};

function AgentNode({ data, selected }: { data: any; selected?: boolean }) {
 return (
 <div className={`px-4 py-4 border-4 bg-white ${selected ? 'border-primary shadow-pixel' : 'border-outline shadow-pixel'} min-w-[180px]`}>
 <div className="flex items-center gap-2 mb-2 border-b-4 border-outline/5 pb-1">
 <Bot className="w-4 h-4 text-primary" />
 <span className="text-[10px] font-pixel uppercase tracking-tighter text-primary">Agent_Core</span>
 </div>
 <div className="text-lg font-retro uppercase text-primaryText truncate">{data.label || 'Agent'}</div>
 {data.agent_type && <div className="text-[8px] font-pixel text-secondaryText mt-1 uppercase opacity-50">{data.agent_type}</div>}
 </div>
 );
}

function ToolNode({ data, selected }: { data: any; selected?: boolean }) {
 return (
 <div className={`px-4 py-4 border-4 bg-white ${selected ? 'border-accent-mint shadow-pixel' : 'border-outline shadow-pixel'} min-w-[180px]`}>
 <div className="flex items-center gap-2 mb-2 border-b-4 border-outline/5 pb-1">
 <Wrench className="w-4 h-4 text-accent-mint" />
 <span className="text-[10px] font-pixel uppercase tracking-tighter text-accent-mint">Tool_Module</span>
 </div>
 <div className="text-lg font-retro uppercase text-primaryText truncate">{data.label || 'Tool'}</div>
 </div>
 );
}

function DecisionNode({ data, selected }: { data: any; selected?: boolean }) {
 return (
 <div className={`px-4 py-4 border-4 bg-white ${selected ? 'border-accent-yellow shadow-pixel' : 'border-outline shadow-pixel'} min-w-[180px]`}>
 <div className="flex items-center gap-2 mb-2 border-b-4 border-outline/5 pb-1">
 <GitBranch className="w-4 h-4 text-accent-yellow" />
 <span className="text-[10px] font-pixel uppercase tracking-tighter text-accent-yellow">Logic_Gate</span>
 </div>
 <div className="text-lg font-retro uppercase text-primaryText truncate">{data.label || 'Decision'}</div>
 {data.condition && <div className="text-[8px] font-pixel text-secondaryText mt-1 truncate uppercase opacity-50">{data.condition}</div>}
 </div>
 );
}

function WaitNode({ data, selected }: { data: any; selected?: boolean }) {
 return (
 <div className={`px-4 py-4 border-4 bg-white ${selected ? 'border-primary shadow-pixel' : 'border-outline shadow-pixel'} min-w-[180px]`}>
 <div className="flex items-center gap-2 mb-2 border-b-4 border-outline/5 pb-1">
 <ShieldAlert className="w-4 h-4 text-primary" />
 <span className="text-[10px] font-pixel uppercase tracking-tighter text-primary">Approval_Req</span>
 </div>
 <div className="text-lg font-retro uppercase text-primaryText truncate">{data.label || 'Wait'}</div>
 </div>
 );
}

function FlowCanvas() {
 const { screenToFlowPosition } = useReactFlow();
 const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
 const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
 const [selectedNode, setSelectedNode] = useState<Node | null>(null);
 const [workflowName, setWorkflowName] = useState('New Workflow');
 const [saveStatus, setSaveStatus] = useState('');
 const [executeStatus, setExecuteStatus] = useState('');
 const [tools, setTools] = useState<Array<{name: string; description: string; type: string; status: string}>>([]);
 const [templates, setTemplates] = useState<Array<{id: string; name: string; definition: any}>>([]);
 const reactFlowWrapper = useRef<HTMLDivElement>(null);

 useEffect(() => {
 apiClient.getTools().then(setTools).catch(() => {});
 apiClient.getWorkflowTemplates().then(setTemplates).catch(() => {});
 }, []);

 const onConnect = useCallback(
 (params: Connection) => {
 if (!params.source || !params.target) return;
 setEdges((eds) => addEdge({
 id: `edge_${Date.now()}_${Math.random().toString(36).slice(2)}`,
 source: params.source!,
 target: params.target!,
 sourceHandle: params.sourceHandle || undefined,
 targetHandle: params.targetHandle || undefined,
 animated: true,
 style: { stroke: '#5A7D9A' },
 }, eds));
 },
 [setEdges]
 );

 const onDragOver = useCallback((event: React.DragEvent) => {
 event.preventDefault();
 event.dataTransfer.dropEffect = 'move';
 }, []);

 const onDrop = useCallback(
 (event: React.DragEvent) => {
 event.preventDefault();
 const type = event.dataTransfer.getData('application/reactflow');
 if (!type || !reactFlowWrapper.current) return;

 const bounds = reactFlowWrapper.current.getBoundingClientRect();
 const position = screenToFlowPosition({
 x: event.clientX - bounds.left,
 y: event.clientY - bounds.top,
 });

 const newNode: Node = {
 id: `${type}_${Date.now()}`,
 type,
 position,
 data: { label: `${type.charAt(0).toUpperCase() + type.slice(1)} Node`, agent_type: 'executor', condition: '', tools: [] },
 };
 setNodes((nds) => nds.concat(newNode));
 },
 [screenToFlowPosition, setNodes]
 );

 const onNodeClick = useCallback((_event: React.MouseEvent, node: Node) => {
 setSelectedNode(node);
 }, []);

 const updateSelectedNode = (updates: Partial<any>) => {
 if (!selectedNode) return;
 setNodes((nds) =>
 nds.map((n) =>
 n.id === selectedNode.id ? { ...n, data: { ...n.data, ...updates } } : n
 )
 );
 setSelectedNode((prev) => (prev ? { ...prev, data: { ...prev.data, ...updates } } : prev));
 };

 const deleteSelectedNode = () => {
 if (!selectedNode) return;
 setNodes((nds) => nds.filter((n) => n.id !== selectedNode.id));
 setEdges((eds) => eds.filter((e) => e.source !== selectedNode.id && e.target !== selectedNode.id));
 setSelectedNode(null);
 };

 const toDefinition = () => {
 const nodeMap = new Map<string, string>();
 nodes.forEach((n, idx) => nodeMap.set(n.id, String(idx + 1)));

 const definitionNodes = nodes.map((n, idx) => ({
 id: String(idx + 1),
 step: n.data.label || n.type,
 agent_type: n.data.agent_type || 'executor',
 node_type: n.type,
 depends_on: edges
 .filter((e) => e.target === n.id)
 .map((e) => nodeMap.get(e.source))
 .filter(Boolean) as string[],
 condition: n.data.condition || undefined,
 approval_config: n.data.approval_config || undefined,
 step_number: idx + 1,
 }));

 const definitionEdges = edges.map((e) => ({
 from: nodeMap.get(e.source),
 to: nodeMap.get(e.target),
 }));

 return { nodes: definitionNodes, edges: definitionEdges };
 };

 const validateWorkflow = (): string[] => {
 const errors: string[] = [];
 if (nodes.length === 0) {
 errors.push('Workflow must have at least one node');
 return errors;
 }
 const nodeIds = new Set(nodes.map(n => n.id));
 for (const edge of edges) {
 if (!nodeIds.has(edge.source)) errors.push(`Edge references missing source: ${edge.source}`);
 if (!nodeIds.has(edge.target)) errors.push(`Edge references missing target: ${edge.target}`);
 }
 const adj = new Map<string, string[]>();
 nodes.forEach(n => adj.set(n.id, []));
 edges.forEach(e => {
 if (adj.has(e.source)) adj.get(e.source)!.push(e.target);
 });
 const visiting = new Set<string>();
 const visited = new Set<string>();
 const visit = (nodeId: string) => {
 if (visiting.has(nodeId)) throw new Error('Cycle');
 if (visited.has(nodeId)) return;
 visiting.add(nodeId);
 for (const neighbor of adj.get(nodeId) || []) visit(neighbor);
 visiting.delete(nodeId);
 visited.add(nodeId);
 };
 try {
 for (const node of nodes) {
 if (!visited.has(node.id)) visit(node.id);
 }
 } catch {
 errors.push('Workflow contains a cycle');
 }
 return errors;
 };

 const loadTemplate = (definition: any) => {
 if (!definition.nodes) return;
 const importedNodes: Node[] = definition.nodes.map((n: any, idx: number) => ({
 id: String(n.id),
 type: n.node_type || 'agent',
 position: { x: 100 + (idx % 3) * 250, y: 100 + Math.floor(idx / 3) * 150 },
 data: {
 label: n.step,
 agent_type: n.agent_type,
 condition: n.condition,
 approval_config: n.approval_config,
 tools: n.tools || [],
 },
 }));
 const nodeIdMap = new Map<string, string>();
 importedNodes.forEach((n, i) => nodeIdMap.set(String(definition.nodes[i].id), n.id));
 const importedEdges: Edge[] = (definition.edges || []).map((e: any, idx: number) => ({
 id: `edge_${idx}_${Date.now()}`,
 source: nodeIdMap.get(String(e.from)) || '',
 target: nodeIdMap.get(String(e.to)) || '',
 animated: true,
 style: { stroke: '#5A7D9A' },
 })).filter((e: Edge) => e.source && e.target);
 setNodes(importedNodes);
 setEdges(importedEdges);
 setSelectedNode(null);
 };

 const saveWorkflow = async () => {
 try {
 const errors = validateWorkflow();
 if (errors.length > 0) {
 setSaveStatus(`Validation failed: ${errors.join(', ')}`);
 return;
 }
 setSaveStatus('Saving...');
 await apiClient.saveWorkflow({ name: workflowName, definition: toDefinition() });
 setSaveStatus('Saved!');
 setTimeout(() => setSaveStatus(''), 2000);
 } catch (err) {
 setSaveStatus(err instanceof Error ? err.message : 'Save failed');
 }
 };

 const executeWorkflow = async () => {
 try {
 const errors = validateWorkflow();
 if (errors.length > 0) {
 setExecuteStatus(`Validation failed: ${errors.join(', ')}`);
 return;
 }
 setExecuteStatus('Saving...');
 const saved = await apiClient.saveWorkflow({ name: workflowName, definition: toDefinition() });
 setExecuteStatus('Starting...');
 const result = await apiClient.createTask({
 query: workflowName,
 mode: 'workflow',
 config: { max_steps: 50, timeout: 300, workflow_id: saved.id },
 });
 setExecuteStatus(`Started: ${result.task_id}`);
 setTimeout(() => setExecuteStatus(''), 3000);
 } catch (err) {
 setExecuteStatus(err instanceof Error ? err.message : 'Execution failed');
 }
 };

 const exportJson = () => {
 const blob = new Blob([JSON.stringify(toDefinition(), null, 2)], { type: 'application/json' });
 const url = URL.createObjectURL(blob);
 const a = document.createElement('a');
 a.href = url;
 a.download = `${workflowName.replace(/\s+/g, '_')}.json`;
 a.click();
 URL.revokeObjectURL(url);
 };

 const importJson = (file: File) => {
 const reader = new FileReader();
 reader.onload = (e) => {
 try {
 const def = JSON.parse(e.target?.result as string);
 if (!def.nodes) return;
 const importedNodes: Node[] = def.nodes.map((n: any, idx: number) => ({
 id: `node_${idx}`,
 type: n.node_type || 'agent',
 position: { x: 100 + (idx % 3) * 250, y: 100 + Math.floor(idx / 3) * 150 },
 data: {
 label: n.step,
 agent_type: n.agent_type,
 condition: n.condition,
 approval_config: n.approval_config,
 tools: n.tools || [],
 },
 }));
 const importedEdges: Edge[] = (def.edges || []).map((e: any, idx: number) => ({
 id: `edge_${idx}`,
 source: importedNodes[Number(e.from) - 1]?.id,
 target: importedNodes[Number(e.to) - 1]?.id,
 animated: true,
 style: { stroke: '#5A7D9A' },
 })).filter((e: Edge) => e.source && e.target);
 setNodes(importedNodes);
 setEdges(importedEdges);
 } catch {
 alert('Invalid workflow file');
 }
 };
 reader.readAsText(file);
 };

 return (
 <div className="flex flex-col h-[calc(100vh-4rem)] -m-8">
 {/* Toolbar */}
 <div className="flex items-center justify-between px-6 py-4 border-b-4 border-outline bg-white shrink-0 shadow-pixel">
 <div className="flex items-center gap-4">
 <input
 className="pixel-input text-[10px] font-pixel uppercase w-80"
 value={workflowName}
 onChange={(e) => setWorkflowName(e.target.value)}
 />
 {saveStatus && <span className="font-pixel text-[8px] uppercase text-secondaryText animate-pulse">{saveStatus}</span>}
 </div>
 <div className="flex items-center gap-3">
 <label className="btn-secondary flex items-center gap-2 text-[10px] font-pixel uppercase cursor-pointer">
 <Upload className="w-4 h-4" /> Load
 <input type="file" accept=".json" className="hidden" onChange={(e) => e.target.files?.[0] && importJson(e.target.files[0])} />
 </label>
 <button onClick={exportJson} className="btn-secondary flex items-center gap-2 text-[10px] font-pixel uppercase">
 <Download className="w-4 h-4" /> Export
 </button>
 <button onClick={saveWorkflow} className="btn-primary flex items-center gap-2 text-[10px] font-pixel uppercase">
 <Save className="w-4 h-4" /> Save
 </button>
 <button onClick={executeWorkflow} className="btn-primary flex items-center gap-2 text-[10px] font-pixel uppercase bg-secondary">
 <Play className="w-4 h-4 fill-current" /> Execute
 </button>
 {executeStatus && <span className="font-pixel text-[8px] uppercase text-secondaryText ml-2">{executeStatus}</span>}
 </div>
 </div>

 <div className="flex flex-1 overflow-hidden">
 {/* Left Sidebar */}
 <div className="w-64 border-r-4 border-outline bg-surface-high p-6 flex flex-col gap-6 overflow-y-auto">
 <div>
 <h3 className="text-[10px] font-pixel uppercase tracking-tighter text-secondaryText mb-4">Templates</h3>
 <div className="flex flex-col gap-2">
 {templates.map((t) => (
 <button
 key={t.id}
 onClick={() => loadTemplate(t.definition)}
 className="text-left px-4 py-4 border-4 border-outline bg-white hover:bg-primary hover:text-white font-retro text-lg uppercase"
 >
 {t.name}
 </button>
 ))}
 </div>
 </div>

 <div className="border-t-4 border-outline/5 pt-6">
 <h3 className="text-[10px] font-pixel uppercase tracking-tighter text-secondaryText mb-4">Node Palette</h3>
 <div className="flex flex-col gap-3">
 <PaletteItem type="agent" label="Agent Node" icon={<Bot className="w-5 h-5 text-primary" />} color="border-primary" />
 <PaletteItem type="tool" label="Tool Node" icon={<Wrench className="w-5 h-5 text-accent-mint" />} color="border-accent-mint" />
 <PaletteItem type="decision" label="Decision Node" icon={<GitBranch className="w-5 h-5 text-accent-yellow" />} color="border-accent-yellow" />
 <PaletteItem type="wait" label="Approval Node" icon={<ShieldAlert className="w-5 h-5 text-primary" />} color="border-primary" />
 </div>
 </div>
 </div>

 {/* Canvas */}
 <div className="flex-1 relative bg-surface-lowest" ref={reactFlowWrapper}>
 <ReactFlow
 nodes={nodes}
 edges={edges}
 onNodesChange={onNodesChange}
 onEdgesChange={onEdgesChange}
 onConnect={onConnect}
 onDrop={onDrop}
 onDragOver={onDragOver}
 onNodeClick={onNodeClick}
 nodeTypes={nodeTypes}
 fitView
 deleteKeyCode={['Backspace', 'Delete']}
 >
 <Background color="#1A1A2E" gap={40} size={2} className="opacity-10" />
 <Controls className="!bg-white !border-4 !border-outline !shadow-pixel !rounded-none" />
 <MiniMap 
 className="!bg-white !border-4 !border-outline !shadow-pixel !rounded-none" 
 maskColor="rgba(245, 240, 232, 0.5)" 
 nodeColor={(n) => {
 if (n.type === 'agent') return '#FF6B35';
 if (n.type === 'tool') return '#4ECDC4';
 if (n.type === 'decision') return '#FFD93D';
 if (n.type === 'wait') return '#FF6B35';
 return '#1A1A2E';
 }} />
 </ReactFlow>
 </div>

 {/* Right Properties Panel */}
 <div className="w-72 border-l-4 border-outline bg-surface-high p-6 overflow-y-auto">
 <h3 className="text-[10px] font-pixel uppercase tracking-tighter text-secondaryText mb-6">Properties</h3>
 {selectedNode ? (
 <div className="flex flex-col gap-6">
 {(() => {
 const data = selectedNode.data as Record<string, any>;
 return (
 <>
 <div>
 <label className="text-[8px] font-pixel uppercase text-secondaryText block mb-2">Node Label</label>
 <input
 className="pixel-input text-lg font-retro uppercase w-full"
 value={data.label || ''}
 onChange={(e) => updateSelectedNode({ label: e.target.value })}
 />
 </div>
 {selectedNode.type === 'agent' && (
 <>
 <div>
 <label className="text-[8px] font-pixel uppercase text-secondaryText block mb-2">Agent Config</label>
 <select
 className="pixel-input text-lg font-retro uppercase w-full"
 value={data.agent_type || 'executor'}
 onChange={(e) => updateSelectedNode({ agent_type: e.target.value })}
 >
 <option value="executor">executor</option>
 <option value="planner">planner</option>
 <option value="verifier">verifier</option>
 </select>
 </div>
 <div>
 <label className="text-[8px] font-pixel uppercase text-secondaryText block mb-2">Tools Link</label>
 <select
 multiple
 className="pixel-input text-lg font-retro uppercase w-full h-40"
 value={data.tools || []}
 onChange={(e) => {
 const options = Array.from(e.target.selectedOptions).map(o => o.value);
 updateSelectedNode({ tools: options });
 }}
 >
 {tools.map((tool) => (
 <option key={tool.name} value={tool.name}>{tool.name}</option>
 ))}
 </select>
 </div>
 </>
 )}
 {selectedNode.type === 'decision' && (
 <div>
 <label className="text-[8px] font-pixel uppercase text-secondaryText block mb-2">Logic Script</label>
 <input
 className="pixel-input text-lg font-retro w-full"
 placeholder="context.get('result') == 'good'"
 value={data.condition || ''}
 onChange={(e) => updateSelectedNode({ condition: e.target.value })}
 />
 </div>
 )}
 {selectedNode.type === 'wait' && (
 <div>
 <label className="text-[8px] font-pixel uppercase text-secondaryText block mb-2">Approval JSON</label>
 <textarea
 className="pixel-input text-sm font-retro w-full h-32"
 placeholder='{"required_role": "admin"}'
 value={data.approval_config ? JSON.stringify(data.approval_config) : ''}
 onChange={(e) => {
 try {
 const val = e.target.value ? JSON.parse(e.target.value) : undefined;
 updateSelectedNode({ approval_config: val });
 } catch {}
 }}
 />
 </div>
 )}
 </>
 );
 })()}
 <button onClick={deleteSelectedNode} className="btn-danger flex items-center justify-center gap-2 py-4 mt-4">
 <Trash2 className="w-4 h-4" /> [ DELETE NODE ]
 </button>
 </div>
 ) : (
 <p className="font-retro text-lg text-secondaryText uppercase opacity-50">Select unit to modify parameters.</p>
 )}
 </div>
 </div>
 </div>
 );
}

function PaletteItem({ type, label, icon, color }: { type: string; label: string; icon: React.ReactNode; color: string }) {
 const onDragStart = (event: React.DragEvent) => {
 event.dataTransfer.setData('application/reactflow', type);
 event.dataTransfer.effectAllowed = 'move';
 };

 return (
 <div
 draggable
 onDragStart={onDragStart}
 className={`flex items-center gap-4 px-4 py-4 border-4 ${color} bg-white cursor-grab active:cursor-grabbing hover:bg-surface-high shadow-pixel`}
 >
 <div className="shrink-0">{icon}</div>
 <span className="font-retro text-lg uppercase text-primaryText">{label}</span>
 </div>
 );
}

export default function WorkflowBuilder() {
 return (
 <ReactFlowProvider>
 <FlowCanvas />
 </ReactFlowProvider>
 );
}

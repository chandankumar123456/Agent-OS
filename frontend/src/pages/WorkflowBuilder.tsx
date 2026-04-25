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
    <div className={`px-4 py-3 rounded-xl border bg-surface-low border-primary/30 shadow-sm min-w-[160px] ${selected ? 'ring-2 ring-primary' : ''}`}>
      <div className="flex items-center gap-2 mb-1">
        <Bot className="w-4 h-4 text-primary" />
        <span className="text-xs font-bold uppercase tracking-wider text-primary">Agent</span>
      </div>
      <div className="text-sm font-semibold text-primaryText truncate">{data.label || 'Agent'}</div>
      {data.agent_type && <div className="text-xs text-secondaryText mt-1">{data.agent_type}</div>}
    </div>
  );
}

function ToolNode({ data, selected }: { data: any; selected?: boolean }) {
  return (
    <div className={`px-4 py-3 rounded-xl border bg-surface-low border-[#00FF88]/30 shadow-sm min-w-[160px] ${selected ? 'ring-2 ring-[#00FF88]' : ''}`}>
      <div className="flex items-center gap-2 mb-1">
        <Wrench className="w-4 h-4 text-[#00FF88]" />
        <span className="text-xs font-bold uppercase tracking-wider text-[#00FF88]">Tool</span>
      </div>
      <div className="text-sm font-semibold text-primaryText truncate">{data.label || 'Tool'}</div>
    </div>
  );
}

function DecisionNode({ data, selected }: { data: any; selected?: boolean }) {
  return (
    <div className={`px-4 py-3 rounded-xl border bg-surface-low border-amber-400/30 shadow-sm min-w-[160px] ${selected ? 'ring-2 ring-amber-400' : ''}`}>
      <div className="flex items-center gap-2 mb-1">
        <GitBranch className="w-4 h-4 text-amber-400" />
        <span className="text-xs font-bold uppercase tracking-wider text-amber-400">Decision</span>
      </div>
      <div className="text-sm font-semibold text-primaryText truncate">{data.label || 'Decision'}</div>
      {data.condition && <div className="text-xs text-secondaryText mt-1 truncate">{data.condition}</div>}
    </div>
  );
}

function WaitNode({ data, selected }: { data: any; selected?: boolean }) {
  return (
    <div className={`px-4 py-3 rounded-xl border bg-surface-low border-purple-400/30 shadow-sm min-w-[160px] ${selected ? 'ring-2 ring-purple-400' : ''}`}>
      <div className="flex items-center gap-2 mb-1">
        <ShieldAlert className="w-4 h-4 text-purple-400" />
        <span className="text-xs font-bold uppercase tracking-wider text-purple-400">Approval</span>
      </div>
      <div className="text-sm font-semibold text-primaryText truncate">{data.label || 'Wait'}</div>
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
      <div className="flex items-center justify-between px-6 py-3 border-b border-outline/10 bg-surface-low">
        <div className="flex items-center gap-3">
          <input
            className="obsidian-input text-sm font-semibold w-64"
            value={workflowName}
            onChange={(e) => setWorkflowName(e.target.value)}
          />
          {saveStatus && <span className="text-xs text-secondaryText">{saveStatus}</span>}
        </div>
        <div className="flex items-center gap-2">
          <label className="btn-secondary flex items-center gap-2 text-sm cursor-pointer">
            <Upload className="w-4 h-4" /> Load
            <input type="file" accept=".json" className="hidden" onChange={(e) => e.target.files?.[0] && importJson(e.target.files[0])} />
          </label>
          <button onClick={exportJson} className="btn-secondary flex items-center gap-2 text-sm">
            <Download className="w-4 h-4" /> Export
          </button>
          <button onClick={saveWorkflow} className="btn-primary flex items-center gap-2 text-sm">
            <Save className="w-4 h-4" /> Save
          </button>
          <button onClick={executeWorkflow} className="btn-primary flex items-center gap-2 text-sm bg-emerald-600 hover:bg-emerald-500">
            <Play className="w-4 h-4" /> Execute
          </button>
          {executeStatus && <span className="text-xs text-secondaryText ml-2">{executeStatus}</span>}
        </div>
      </div>

      <div className="flex flex-1 overflow-hidden">
        {/* Left Sidebar */}
        <div className="w-56 border-r border-outline/10 bg-surface-low p-4 flex flex-col gap-3 overflow-y-auto">
          <h3 className="text-xs font-bold uppercase tracking-widest text-secondaryText mb-1">Templates</h3>
          {templates.map((t) => (
            <button
              key={t.id}
              onClick={() => loadTemplate(t.definition)}
              className="text-left px-3 py-2 rounded-lg border border-outline/10 bg-surface-low hover:bg-surface-highest transition-colors text-sm text-primaryText"
            >
              {t.name}
            </button>
          ))}
          <div className="border-t border-outline/10 my-1" />
          <h3 className="text-xs font-bold uppercase tracking-widest text-secondaryText mb-1">Node Palette</h3>
          <PaletteItem type="agent" label="Agent Node" icon={<Bot className="w-4 h-4 text-primary" />} color="border-primary/30" />
          <PaletteItem type="tool" label="Tool Node" icon={<Wrench className="w-4 h-4 text-[#00FF88]" />} color="border-[#00FF88]/30" />
          <PaletteItem type="decision" label="Decision Node" icon={<GitBranch className="w-4 h-4 text-amber-400" />} color="border-amber-400/30" />
          <PaletteItem type="wait" label="Approval Node" icon={<ShieldAlert className="w-4 h-4 text-purple-400" />} color="border-purple-400/30" />
        </div>

        {/* Canvas */}
        <div className="flex-1 relative" ref={reactFlowWrapper}>
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
            <Background color="#5A7D9A" gap={20} size={1} />
            <Controls />
            <MiniMap className="bg-surface-low" maskColor="rgba(10,10,11,0.7)" nodeColor={(n) => {
              if (n.type === 'agent') return '#5A7D9A';
              if (n.type === 'tool') return '#00FF88';
              if (n.type === 'decision') return '#fbbf24';
              if (n.type === 'wait') return '#c084fc';
              return '#5A7D9A';
            }} />
          </ReactFlow>
        </div>

        {/* Right Properties Panel */}
        <div className="w-64 border-l border-outline/10 bg-surface-low p-4 overflow-y-auto">
          <h3 className="text-xs font-bold uppercase tracking-widest text-secondaryText mb-3">Properties</h3>
          {selectedNode ? (
            <div className="flex flex-col gap-3">
              {(() => {
                const data = selectedNode.data as Record<string, any>;
                return (
                  <>
                    <div>
                      <label className="text-xs text-secondaryText block mb-1">Label</label>
                      <input
                        className="obsidian-input text-sm w-full"
                        value={data.label || ''}
                        onChange={(e) => updateSelectedNode({ label: e.target.value })}
                      />
                    </div>
                    {selectedNode.type === 'agent' && (
                      <>
                        <div>
                          <label className="text-xs text-secondaryText block mb-1">Agent Type</label>
                          <select
                            className="obsidian-input text-sm w-full"
                            value={data.agent_type || 'executor'}
                            onChange={(e) => updateSelectedNode({ agent_type: e.target.value })}
                          >
                            <option value="executor">executor</option>
                            <option value="planner">planner</option>
                            <option value="verifier">verifier</option>
                          </select>
                        </div>
                        <div>
                          <label className="text-xs text-secondaryText block mb-1">Tools</label>
                          <select
                            multiple
                            className="obsidian-input text-sm w-full h-24"
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
                        <label className="text-xs text-secondaryText block mb-1">Condition</label>
                        <input
                          className="obsidian-input text-sm w-full"
                          placeholder="context.get('result') == 'good'"
                          value={data.condition || ''}
                          onChange={(e) => updateSelectedNode({ condition: e.target.value })}
                        />
                      </div>
                    )}
                    {selectedNode.type === 'wait' && (
                      <div>
                        <label className="text-xs text-secondaryText block mb-1">Approval Config (JSON)</label>
                        <textarea
                          className="obsidian-input text-sm w-full h-20"
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
              <button onClick={deleteSelectedNode} className="btn-danger flex items-center gap-2 text-sm mt-2">
                <Trash2 className="w-4 h-4" /> Delete Node
              </button>
            </div>
          ) : (
            <p className="text-sm text-secondaryText">Select a node to edit its properties.</p>
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
      className={`flex items-center gap-3 px-3 py-2.5 rounded-lg border ${color} bg-surface-low cursor-grab active:cursor-grabbing hover:bg-surface-highest transition-colors`}
    >
      {icon}
      <span className="text-sm font-medium text-primaryText">{label}</span>
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

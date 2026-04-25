import { useState, useCallback, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { ReactFlow, Background, Controls, MiniMap, useNodesState, useEdgesState, addEdge, useReactFlow, ReactFlowProvider } from '@xyflow/react';
import type { Edge, Node } from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { Save, Play, Download, Upload, Trash2, GitBranch, Bot, Wrench, ShieldAlert, CheckCircle, AlertCircle, X, Activity, FlaskConical, ChevronUp, ChevronDown, Link2 } from 'lucide-react';
import { apiClient } from '../api/client';
import { Skeleton } from '../components/ui/Skeleton';

interface Conn { source: string | null; target: string | null; sourceHandle?: string | null; targetHandle?: string | null; }

interface ExecutionLog {
  timestamp: string;
  type: string;
  nodeName: string;
  message: string;
}

interface Binding {
  sourceOutput: string;
  targetInput: string;
  transform?: string;
}

const BUILT_IN_TEMPLATES = [
  { id: 'sequential_review', name: 'Sequential Review', definition: { nodes: [
    { id: 'plan', step: 'Plan review', agent_type: 'planner', node_type: 'agent' },
    { id: 'exec', step: 'Execute tasks', agent_type: 'executor', node_type: 'agent', depends_on: ['plan'] },
    { id: 'verify', step: 'Verify output', agent_type: 'verifier', node_type: 'agent', depends_on: ['exec'] },
    { id: 'wait', step: 'Wait for approval', agent_type: 'executor', node_type: 'wait', depends_on: ['verify'], approval_config: { required_role: 'admin' } },
  ]}},
  { id: 'parallel_research', name: 'Parallel Research', definition: { nodes: [
    { id: 'plan', step: 'Plan research', agent_type: 'planner', node_type: 'agent' },
    { id: 'research_a', step: 'Research topic A', agent_type: 'executor', node_type: 'agent', depends_on: ['plan'] },
    { id: 'research_b', step: 'Research topic B', agent_type: 'executor', node_type: 'agent', depends_on: ['plan'] },
    { id: 'synthesize', step: 'Synthesize findings', agent_type: 'verifier', node_type: 'agent', depends_on: ['research_a', 'research_b'] },
  ]}},
  { id: 'error_recovery', name: 'Error Recovery', definition: { nodes: [
    { id: 'plan', step: 'Plan task', agent_type: 'planner', node_type: 'agent' },
    { id: 'exec', step: 'Execute', agent_type: 'executor', node_type: 'agent', depends_on: ['plan'] },
    { id: 'decide', step: 'Check success?', agent_type: 'verifier', node_type: 'decision', depends_on: ['exec'], condition: "context.get('status') == 'success'" },
    { id: 'retry', step: 'Retry on failure', agent_type: 'executor', node_type: 'agent', depends_on: ['decide'] },
    { id: 'notify', step: 'Notify admin', agent_type: 'executor', node_type: 'wait', depends_on: ['retry'], approval_config: { required_role: 'admin' } },
  ]}},
];

function generateUUID() {
  if (typeof crypto !== 'undefined' && (crypto as any).randomUUID) {
    return (crypto as any).randomUUID();
  }
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
    const r = Math.random() * 16 | 0, v = c === 'x' ? r : (r & 0x3 | 0x8);
    return v.toString(16);
  });
}

function NodeWrap({ data, selected, icon, label, color }: { data: any; selected?: boolean; icon: React.ReactNode; label: string; color: string }) {
  const status = data.executionStatus;
  const statusBorder = status === 'running' ? 'border-cyan-400 shadow-[0_0_12px_rgba(34,211,238,0.5)] animate-pulse' :
    status === 'completed' ? 'border-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.4)]' :
    status === 'failed' ? 'border-red-500 shadow-[0_0_8px_rgba(239,68,68,0.4)]' :
    status === 'waiting' ? 'border-yellow-400 shadow-[0_0_8px_rgba(250,204,21,0.4)]' : color;

  return (
    <motion.div
      animate={selected ? { scale: 1.02 } : { scale: 1 }}
      whileHover={{ y: -2 }}
      className={`px-4 py-3 rounded-xl border bg-surface-low ${statusBorder} shadow-sm min-w-[160px] ${selected ? 'ring-2 ring-primary/50' : ''} transition-all duration-300 cursor-pointer`}
    >
      <div className="flex items-center gap-2 mb-1">
        {icon}
        <span className="text-xs font-bold uppercase tracking-wider">{label}</span>
        {status === 'completed' && <CheckCircle className="w-3 h-3 text-emerald-400 ml-auto" />}
        {status === 'failed' && <X className="w-3 h-3 text-red-400 ml-auto" />}
        {status === 'waiting' && <ShieldAlert className="w-3 h-3 text-yellow-400 ml-auto" />}
        {status === 'running' && <Activity className="w-3 h-3 text-cyan-400 ml-auto animate-spin" />}
      </div>
      <div className="text-sm font-semibold text-primaryText truncate">{data.label || label}</div>
    </motion.div>
  );
}

const nodeTypes = {
  agent: ({ data, selected }: any) => <NodeWrap data={data} selected={selected} icon={<Bot className="w-4 h-4 text-primary" />} label="Agent" color="border-primary/30" />,
  tool: ({ data, selected }: any) => <NodeWrap data={data} selected={selected} icon={<Wrench className="w-4 h-4 text-[#00FF88]" />} label="Tool" color="border-[#00FF88]/30" />,
  decision: ({ data, selected }: any) => <NodeWrap data={data} selected={selected} icon={<GitBranch className="w-4 h-4 text-amber-400" />} label="Decision" color="border-amber-400/30" />,
  wait: ({ data, selected }: any) => <NodeWrap data={data} selected={selected} icon={<ShieldAlert className="w-4 h-4 text-purple-400" />} label="Approval" color="border-purple-400/30" />,
};

function FlowCanvas() {
  const { screenToFlowPosition } = useReactFlow();
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [selectedNode, setSelectedNode] = useState<Node | null>(null);
  const [workflowName, setWorkflowName] = useState('New Workflow');
  const [statusMsg, setStatusMsg] = useState('');
  const [tools, setTools] = useState<Array<{ name: string; description: string; type: string; status: string }>>([]);
  const [templates, setTemplates] = useState<Array<{ id: string; name: string; definition: any }>>([]);
  const wrapper = useRef<HTMLDivElement>(null);

  // Execution state
  const [isExecuting, setIsExecuting] = useState(false);
  const [executionProgress, setExecutionProgress] = useState(0);
  const [executionLogs, setExecutionLogs] = useState<ExecutionLog[]>([]);
  const [logsOpen, setLogsOpen] = useState(true);
  const [completedCount, setCompletedCount] = useState(0);
  const [failedCount, setFailedCount] = useState(0);
  const executionTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Simulate state
  const [simulateOpen, setSimulateOpen] = useState(false);
  const [simulateResult, setSimulateResult] = useState<any>(null);
  const [isSimulating, setIsSimulating] = useState(false);

  // Binding state
  const [bindingModalOpen, setBindingModalOpen] = useState(false);
  const [selectedEdge, setSelectedEdge] = useState<Edge | null>(null);
  const [bindings, setBindings] = useState<Record<string, Binding[]>>({});
  const [tempBinding, setTempBinding] = useState<Binding>({ sourceOutput: '', targetInput: '', transform: '' });

  useEffect(() => {
    apiClient.getTools().then(setTools).catch(() => {});
    apiClient.getWorkflowTemplatesV2().then((t) => setTemplates(t.length ? t : BUILT_IN_TEMPLATES)).catch(() => setTemplates(BUILT_IN_TEMPLATES));
  }, []);

  const clearExecutionState = useCallback(() => {
    setIsExecuting(false);
    setExecutionProgress(0);
    setCompletedCount(0);
    setFailedCount(0);
    if (executionTimerRef.current) clearTimeout(executionTimerRef.current);
  }, []);

  const resetNodeStatus = useCallback(() => {
    setNodes((nds) => nds.map((n) => ({ ...n, data: { ...n.data, executionStatus: undefined } })));
    setEdges((eds) => eds.map((e) => ({ ...e, animated: false, style: { stroke: '#5A7D9A' } })));
  }, [setNodes, setEdges]);

  const startExecutionVisuals = useCallback(() => {
    setExecutionLogs([]);
    setExecutionProgress(0);
    setCompletedCount(0);
    setFailedCount(0);
    setIsExecuting(true);
    resetNodeStatus();
  }, [resetNodeStatus]);

  const finishExecutionVisuals = useCallback((successCount: number, failCount: number) => {
    setIsExecuting(false);
    setStatusMsg(`Execution complete: ${successCount} succeeded, ${failCount} failed`);
    executionTimerRef.current = setTimeout(() => {
      resetNodeStatus();
      setStatusMsg('');
    }, 10000);
  }, [resetNodeStatus]);

  const connectToExecutionEvents = useCallback((workflowId: string) => {
    const sse = new EventSource(`${(import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1').replace('/api/v1', '')}/api/v1/workflows/v2/${workflowId}/events`, {
      withCredentials: true,
    });

    sse.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        const type = msg.type;
        const payload = msg.payload || {};

        if (type === 'node.started') {
          const nodeId = payload.node_id;
          setNodes((nds) => nds.map((n) => n.id === nodeId ? { ...n, data: { ...n.data, executionStatus: 'running' } } : n));
          const node = nodes.find((n) => n.id === nodeId);
          setExecutionLogs((logs) => [...logs, { timestamp: new Date().toLocaleTimeString(), type: 'START', nodeName: node?.data?.label || nodeId, message: 'Node started' }]);
          // Animate incoming edges
          setEdges((eds) => eds.map((e) => e.target === nodeId ? { ...e, animated: true, style: { stroke: '#22d3ee', strokeWidth: 2 } } : e));
        } else if (type === 'node.completed') {
          const nodeId = payload.node_id;
          setNodes((nds) => nds.map((n) => n.id === nodeId ? { ...n, data: { ...n.data, executionStatus: 'completed' } } : n));
          const node = nodes.find((n) => n.id === nodeId);
          setExecutionLogs((logs) => [...logs, { timestamp: new Date().toLocaleTimeString(), type: 'DONE', nodeName: node?.data?.label || nodeId, message: 'Node completed' }]);
          setCompletedCount((c) => c + 1);
          setExecutionProgress((p) => Math.min(p + (100 / Math.max(nodes.length, 1)), 100));
          // Animate outgoing edges
          setEdges((eds) => eds.map((e) => e.source === nodeId ? { ...e, animated: true, style: { stroke: '#22d3ee', strokeWidth: 2 } } : e));
        } else if (type === 'node.failed') {
          const nodeId = payload.node_id;
          setNodes((nds) => nds.map((n) => n.id === nodeId ? { ...n, data: { ...n.data, executionStatus: 'failed' } } : n));
          const node = nodes.find((n) => n.id === nodeId);
          setExecutionLogs((logs) => [...logs, { timestamp: new Date().toLocaleTimeString(), type: 'FAIL', nodeName: node?.data?.label || nodeId, message: payload.error || 'Node failed' }]);
          setFailedCount((c) => c + 1);
        } else if (type === 'workflow.completed') {
          const completedNodes = payload.completed || [];
          const failedNodes = payload.failed || [];
          finishExecutionVisuals(completedNodes.length, failedNodes.length);
          sse.close();
        }
      } catch {
        // ignore parse errors
      }
    };

    sse.onerror = () => {
      sse.close();
    };

    return sse;
  }, [nodes, setNodes, setEdges, finishExecutionVisuals]);

  const onConnect = useCallback((params: Conn) => {
    if (!params.source || !params.target) return;
    const edgeId = `edge_${Date.now()}`;
    setEdges((eds) => addEdge({ id: edgeId, source: params.source!, target: params.target!, animated: false, style: { stroke: '#5A7D9A' }, data: { bindings: [] } }, eds));
  }, [setEdges]);

  const onEdgeDoubleClick = useCallback((_event: React.MouseEvent, edge: Edge) => {
    setSelectedEdge(edge);
    setTempBinding({ sourceOutput: '', targetInput: '', transform: '' });
    setBindingModalOpen(true);
  }, []);

  const onDragOver = useCallback((e: React.DragEvent) => { e.preventDefault(); e.dataTransfer.dropEffect = 'move'; }, []);

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    const type = e.dataTransfer.getData('application/reactflow');
    if (!type || !wrapper.current) return;
    const bounds = wrapper.current.getBoundingClientRect();
    const pos = screenToFlowPosition({ x: e.clientX - bounds.left, y: e.clientY - bounds.top });
    setNodes((nds) => nds.concat({ id: `${type}_${Date.now()}`, type, position: pos, data: { label: `${type.charAt(0).toUpperCase() + type.slice(1)} Node`, agent_type: 'executor', condition: '', tools: [] } }));
  }, [screenToFlowPosition, setNodes]);

  const onNodeClick = useCallback((_e: React.MouseEvent, node: Node) => setSelectedNode(node), []);

  const updateNode = (updates: Partial<any>) => {
    if (!selectedNode) return;
    setNodes((nds) => nds.map((n) => n.id === selectedNode.id ? { ...n, data: { ...n.data, ...updates } } : n));
    setSelectedNode((prev) => prev ? { ...prev, data: { ...prev.data, ...updates } } : prev);
  };

  const deleteNode = () => {
    if (!selectedNode) return;
    setNodes((nds) => nds.filter((n) => n.id !== selectedNode.id));
    setEdges((eds) => eds.filter((e) => e.source !== selectedNode.id && e.target !== selectedNode.id));
    setSelectedNode(null);
  };

  const toDef = () => {
    const map = new Map<string, string>();
    nodes.forEach((n, i) => map.set(n.id, String(i + 1)));
    return {
      nodes: nodes.map((n, i) => ({
        id: String(i + 1), step: n.data.label || n.type, agent_type: n.data.agent_type || 'executor', node_type: n.type,
        depends_on: edges.filter((e) => e.target === n.id).map((e) => map.get(e.source)).filter(Boolean) as string[],
        condition: n.data.condition || undefined, approval_config: n.data.approval_config || undefined, step_number: i + 1,
      })),
      edges: edges.map((e) => ({ from: map.get(e.source), to: map.get(e.target) })),
    };
  };

  const toDefV2 = () => {
    return {
      workflow_id: generateUUID(),
      name: workflowName,
      nodes: nodes.map((n) => {
        const data = n.data as Record<string, any>;
        return {
          node_id: n.id,
          name: data.label || n.type || 'Node',
          type: n.type || 'agent',
          config: {
            agent_type: data.agent_type || 'executor',
            condition: data.condition,
            approval_config: data.approval_config,
            tools: data.tools || [],
            tool_id: data.tool_id,
          },
          agent_id: n.type === 'agent' ? (data.agent_type || 'executor') : (data.tool_id || undefined),
          tool_bindings: (data.tools || []).map((t: string) => ({ tool_name: t })),
          condition: data.condition || undefined,
        };
      }),
      edges: edges.map((e) => ({
        from_node: e.source,
        to_node: e.target,
        condition: e.data?.condition || undefined,
        label: e.data?.label || undefined,
      })),
    };
  };

  const localValidate = (): string[] => {
    const errors: string[] = [];
    if (!nodes.length) { errors.push('Workflow must have at least one node'); return errors; }
    const ids = new Set(nodes.map((n) => n.id));
    edges.forEach((e) => { if (!ids.has(e.source)) errors.push(`Missing source: ${e.source}`); if (!ids.has(e.target)) errors.push(`Missing target: ${e.target}`); });
    const adj = new Map<string, string[]>(); nodes.forEach((n) => adj.set(n.id, [])); edges.forEach((e) => adj.get(e.source)?.push(e.target));
    const visiting = new Set<string>(), visited = new Set<string>();
    const visit = (id: string) => { if (visiting.has(id)) throw new Error('Cycle'); if (visited.has(id)) return; visiting.add(id); (adj.get(id) || []).forEach(visit); visiting.delete(id); visited.add(id); };
    try { nodes.forEach((n) => { if (!visited.has(n.id)) visit(n.id); }); } catch { errors.push('Workflow contains a cycle'); }
    return errors;
  };

  const showStatus = (msg: string) => { setStatusMsg(msg); setTimeout(() => setStatusMsg(''), 3000); };

  const loadTemplate = (def: any) => {
    if (!def.nodes) return;
    const imported: Node[] = def.nodes.map((n: any, i: number) => ({ id: String(n.id), type: n.node_type || 'agent', position: { x: 100 + (i % 3) * 250, y: 100 + Math.floor(i / 3) * 150 }, data: { label: n.step, agent_type: n.agent_type, condition: n.condition, approval_config: n.approval_config, tools: n.tools || [] } }));
    const idMap = new Map<string, string>(); imported.forEach((n, i) => idMap.set(String(def.nodes[i].id), n.id));
    const importedEdges: Edge[] = (def.edges || []).map((e: any, i: number) => ({ id: `edge_${i}`, source: idMap.get(String(e.from)) || '', target: idMap.get(String(e.to)) || '', animated: false, style: { stroke: '#5A7D9A' }, data: { bindings: [] } })).filter((e: Edge) => e.source && e.target);
    setNodes(imported); setEdges(importedEdges); setSelectedNode(null);
  };

  const handleValidate = async () => {
    const errs = localValidate();
    if (errs.length) { showStatus(`Validation failed: ${errs.join(', ')}`); return; }
    try { const r = await apiClient.validateWorkflowV2(toDefV2()); showStatus(r.valid ? 'Workflow is valid' : `Validation failed: ${r.errors.join(', ')}`); } catch (err) { showStatus(err instanceof Error ? err.message : 'Validation request failed'); }
  };

  const handleExecute = async () => {
    const errs = localValidate();
    if (errs.length) { showStatus(`Validation failed: ${errs.join(', ')}`); return; }
    try {
      startExecutionVisuals();
      const def = toDefV2();
      const sse = connectToExecutionEvents(def.workflow_id);
      const r = await apiClient.executeWorkflowV2(def);
      showStatus(`Executed: ${r?.workflow_id || 'OK'}`);
      // SSE will handle completion
      return () => sse.close();
    } catch (err) {
      clearExecutionState();
      showStatus(err instanceof Error ? err.message : 'Execution failed');
    }
  };

  const handleSimulate = async () => {
    const errs = localValidate();
    if (errs.length) { showStatus(`Validation failed: ${errs.join(', ')}`); return; }
    setIsSimulating(true);
    setSimulateOpen(true);
    try {
      const r = await apiClient.simulateWorkflowV2(toDefV2());
      setSimulateResult(r);
      // Highlight path
      setNodes((nds) => nds.map((n) => ({ ...n, data: { ...n.data, executionStatus: r.path?.includes(n.id) ? 'completed' : undefined } })));
      setEdges((eds) => eds.map((e) => {
        const inPath = r.path?.includes(e.source) && r.path?.includes(e.target);
        return { ...e, animated: !!inPath, style: { stroke: inPath ? '#22d3ee' : '#5A7D9A', strokeWidth: inPath ? 2 : 1 } };
      }));
    } catch (err) {
      setSimulateResult({ error: err instanceof Error ? err.message : 'Simulation failed' });
    } finally {
      setIsSimulating(false);
    }
  };

  const saveWorkflow = async () => {
    const errs = localValidate();
    if (errs.length) { showStatus(`Validation failed: ${errs.join(', ')}`); return; }
    try { showStatus('Saving...'); await apiClient.saveWorkflow({ name: workflowName, definition: toDef() }); showStatus('Saved!'); } catch (err) { showStatus(err instanceof Error ? err.message : 'Save failed'); }
  };

  const exportJson = () => { const blob = new Blob([JSON.stringify(toDef(), null, 2)], { type: 'application/json' }); const url = URL.createObjectURL(blob); const a = document.createElement('a'); a.href = url; a.download = `${workflowName.replace(/\s+/g, '_')}.json`; a.click(); URL.revokeObjectURL(url); };

  const importJson = (file: File) => {
    const reader = new FileReader();
    reader.onload = (e) => {
      try {
        const def = JSON.parse(e.target?.result as string);
        if (!def.nodes) return;
        const imported: Node[] = def.nodes.map((n: any, i: number) => ({ id: `node_${i}`, type: n.node_type || 'agent', position: { x: 100 + (i % 3) * 250, y: 100 + Math.floor(i / 3) * 150 }, data: { label: n.step, agent_type: n.agent_type, condition: n.condition, approval_config: n.approval_config, tools: n.tools || [] } }));
        const importedEdges: Edge[] = (def.edges || []).map((e: any, i: number) => ({ id: `edge_${i}`, source: imported[Number(e.from) - 1]?.id, target: imported[Number(e.to) - 1]?.id, animated: false, style: { stroke: '#5A7D9A' }, data: { bindings: [] } })).filter((e: Edge) => e.source && e.target);
        setNodes(imported); setEdges(importedEdges);
      } catch { alert('Invalid workflow file'); }
    };
    reader.readAsText(file);
  };

  const addBinding = () => {
    if (!selectedEdge || !tempBinding.sourceOutput || !tempBinding.targetInput) return;
    const edgeId = selectedEdge.id;
    const current = bindings[edgeId] || [];
    const updated = [...current, { ...tempBinding }];
    setBindings((prev) => ({ ...prev, [edgeId]: updated }));
    setEdges((eds) => eds.map((e) => e.id === edgeId ? { ...e, data: { ...e.data, bindings: updated, label: `${updated.length} binding${updated.length !== 1 ? 's' : ''}` } } : e));
    setTempBinding({ sourceOutput: '', targetInput: '', transform: '' });
  };

  const removeBinding = (edgeId: string, idx: number) => {
    const current = bindings[edgeId] || [];
    const updated = current.filter((_, i) => i !== idx);
    setBindings((prev) => ({ ...prev, [edgeId]: updated }));
    setEdges((eds) => eds.map((e) => e.id === edgeId ? { ...e, data: { ...e.data, bindings: updated, label: updated.length > 0 ? `${updated.length} binding${updated.length !== 1 ? 's' : ''}` : undefined } } : e));
  };

  const getSourceOutputs = (nodeType?: string) => {
    if (nodeType === 'decision') return ['result', 'output', 'status', 'decision_result'];
    return ['result', 'output', 'status'];
  };

  const getTargetInputs = (_nodeType?: string) => {
    return ['input', 'context', 'params'];
  };

  const PaletteItem = ({ type, label, icon, color }: { type: string; label: string; icon: React.ReactNode; color: string }) => (
    <motion.div
      draggable
      onDragStart={(e: any) => { e.dataTransfer.setData('application/reactflow', type); e.dataTransfer.effectAllowed = 'move'; }}
      className={`flex items-center gap-3 px-3 py-2.5 rounded-lg border ${color} bg-surface-low cursor-grab active:cursor-grabbing hover:bg-surface-highest transition-colors`}
      whileHover={{ y: -2, x: 2, boxShadow: '0 4px 20px rgba(0,229,255,0.06)' }}
      whileTap={{ scale: 0.98 }}
    >
      {icon}<span className="text-sm font-medium text-primaryText">{label}</span>
    </motion.div>
  );

  const data = selectedNode?.data as Record<string, any>;
  const isError = statusMsg.includes('failed') || statusMsg.includes('Error');

  const sourceNode = selectedEdge ? nodes.find((n) => n.id === selectedEdge.source) : null;
  const targetNode = selectedEdge ? nodes.find((n) => n.id === selectedEdge.target) : null;

  return (
    <div className="flex flex-col h-[calc(100vh-4rem)] -m-8">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-3 border-b border-outline/10 bg-surface-low">
        <div className="flex items-center gap-3 flex-1">
          <input className="obsidian-input text-sm font-semibold w-64" value={workflowName} onChange={(e) => setWorkflowName(e.target.value)} />
          <AnimatePresence>
            {statusMsg && (
              <motion.span
                initial={{ opacity: 0, y: -5 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -5 }}
                className={`text-xs flex items-center gap-1 ${isError ? 'text-red-400' : 'text-emerald-400'}`}
              >
                {isError ? <AlertCircle className="w-3 h-3" /> : <CheckCircle className="w-3 h-3" />}{statusMsg}
              </motion.span>
            )}
          </AnimatePresence>
          {isExecuting && (
            <div className="flex-1 mx-4">
              <div className="h-1.5 bg-surface-high rounded-full overflow-hidden">
                <div className="h-full bg-cyan-400 transition-all duration-500" style={{ width: `${executionProgress}%` }} />
              </div>
            </div>
          )}
        </div>
        <div className="flex items-center gap-2">
          <label className="btn-secondary flex items-center gap-2 text-sm cursor-pointer"><Upload className="w-4 h-4" /> Load<input type="file" accept=".json" className="hidden" onChange={(e) => e.target.files?.[0] && importJson(e.target.files[0])} /></label>
          <motion.button onClick={exportJson} className="btn-secondary flex items-center gap-2 text-sm" whileTap={{ scale: 0.96 }}><Download className="w-4 h-4" /> Export</motion.button>
          <motion.button onClick={handleValidate} className="btn-secondary flex items-center gap-2 text-sm" whileTap={{ scale: 0.96 }}><CheckCircle className="w-4 h-4" /> Validate</motion.button>
          <motion.button onClick={saveWorkflow} className="btn-primary flex items-center gap-2 text-sm" whileTap={{ scale: 0.96 }} whileHover={{ scale: 1.02 }}><Save className="w-4 h-4" /> Save</motion.button>
          <motion.button onClick={handleSimulate} className="btn-secondary flex items-center gap-2 text-sm text-amber-300" whileTap={{ scale: 0.96 }}><FlaskConical className="w-4 h-4" /> Simulate</motion.button>
          <motion.button onClick={handleExecute} className="btn-primary flex items-center gap-2 text-sm bg-emerald-600 hover:bg-emerald-500" whileTap={{ scale: 0.96 }} whileHover={{ scale: 1.02 }}><Play className="w-4 h-4" /> Execute</motion.button>
        </div>
      </div>

      {/* Main */}
      <div className="flex flex-1 overflow-hidden">
        {/* Palette */}
        <div className="w-56 border-r border-outline/10 bg-surface-low p-4 flex flex-col gap-3 overflow-y-auto">
          <h3 className="text-xs font-bold uppercase tracking-widest text-secondaryText mb-1">Templates</h3>
          {templates.map((t) => (
            <motion.button
              key={t.id}
              onClick={() => loadTemplate(t.definition)}
              className="text-left px-3 py-2 rounded-lg border border-outline/10 bg-surface-low hover:bg-surface-highest transition-colors text-sm text-primaryText w-full"
              whileHover={{ y: -2, x: 2, boxShadow: '0 4px 20px rgba(0,229,255,0.06)' }}
              whileTap={{ scale: 0.98 }}
            >
              {t.name}
            </motion.button>
          ))}
          <div className="border-t border-outline/10 my-1" />
          <h3 className="text-xs font-bold uppercase tracking-widest text-secondaryText mb-1">Node Palette</h3>
          <PaletteItem type="agent" label="Agent Node" icon={<Bot className="w-4 h-4 text-primary" />} color="border-primary/30" />
          <PaletteItem type="tool" label="Tool Node" icon={<Wrench className="w-4 h-4 text-[#00FF88]" />} color="border-[#00FF88]/30" />
          <PaletteItem type="decision" label="Decision Node" icon={<GitBranch className="w-4 h-4 text-amber-400" />} color="border-amber-400/30" />
          <PaletteItem type="wait" label="Approval Node" icon={<ShieldAlert className="w-4 h-4 text-purple-400" />} color="border-purple-400/30" />
        </div>

        {/* Canvas */}
        <div className="flex-1 relative flex flex-col">
          <div className="flex-1 relative" ref={wrapper}>
            <ReactFlow
              nodes={nodes}
              edges={edges}
              onNodesChange={onNodesChange}
              onEdgesChange={onEdgesChange}
              onConnect={onConnect}
              onEdgeDoubleClick={onEdgeDoubleClick}
              onDrop={onDrop}
              onDragOver={onDragOver}
              onNodeClick={onNodeClick}
              nodeTypes={nodeTypes}
              fitView
              deleteKeyCode={['Backspace', 'Delete']}
            >
              <Background color="#5A7D9A" gap={20} size={1} />
              <Controls />
              <MiniMap className="bg-surface-low" maskColor="rgba(10,10,11,0.7)" nodeColor={(n) => ({ agent: '#5A7D9A', tool: '#00FF88', decision: '#fbbf24', wait: '#c084fc' }[n.type || ''] || '#5A7D9A')} />
            </ReactFlow>
          </div>

          {/* Mini Log Panel */}
          {isExecuting && (
            <div className={`border-t border-outline/10 bg-surface-low transition-all duration-300 ${logsOpen ? 'h-48' : 'h-10'}`}>
              <motion.button onClick={() => setLogsOpen(!logsOpen)} className="flex items-center gap-2 px-4 py-2 w-full text-left text-xs font-bold uppercase tracking-widest text-secondaryText hover:text-primaryText" whileTap={{ scale: 0.98 }}>
                {logsOpen ? <ChevronDown className="w-4 h-4" /> : <ChevronUp className="w-4 h-4" />}
                Execution Logs ({executionLogs.length}) — {completedCount} done, {failedCount} failed
              </motion.button>
              {logsOpen && (
                <div className="px-4 pb-2 overflow-y-auto h-[calc(100%-2rem)]">
                  <table className="w-full text-xs">
                    <thead className="text-secondaryText sticky top-0 bg-surface-low">
                      <tr><th className="text-left py-1">Time</th><th className="text-left py-1">Type</th><th className="text-left py-1">Node</th><th className="text-left py-1">Message</th></tr>
                    </thead>
                    <tbody>
                      {executionLogs.map((log, i) => (
                        <motion.tr
                          key={i}
                          initial={{ opacity: 0, x: -10 }}
                          animate={{ opacity: 1, x: 0 }}
                          transition={{ delay: i * 0.02 }}
                          className="border-t border-outline/5"
                        >
                          <td className="py-1 text-secondaryText">{log.timestamp}</td>
                          <td className="py-1">
                            <span className={`px-1.5 rounded text-[10px] font-bold ${log.type === 'FAIL' ? 'bg-red-500/20 text-red-400' : log.type === 'DONE' ? 'bg-emerald-500/20 text-emerald-400' : 'bg-cyan-500/20 text-cyan-400'}`}>{log.type}</span>
                          </td>
                          <td className="py-1 text-primaryText">{log.nodeName}</td>
                          <td className="py-1 text-secondaryText">{log.message}</td>
                        </motion.tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Properties */}
        <div className="w-64 border-l border-outline/10 bg-surface-low p-4 overflow-y-auto">
          <h3 className="text-xs font-bold uppercase tracking-widest text-secondaryText mb-3">Properties</h3>
          {selectedNode ? (
            <div className="flex flex-col gap-3">
              <div><label className="text-xs text-secondaryText block mb-1">Label</label><input className="obsidian-input text-sm w-full" value={data.label || ''} onChange={(e) => updateNode({ label: e.target.value })} /></div>
              {selectedNode.type === 'agent' && <>
                <div><label className="text-xs text-secondaryText block mb-1">Agent Type</label><select className="obsidian-input text-sm w-full" value={data.agent_type || 'executor'} onChange={(e) => updateNode({ agent_type: e.target.value })}><option value="executor">executor</option><option value="planner">planner</option><option value="verifier">verifier</option></select></div>
                <div><label className="text-xs text-secondaryText block mb-1">Tools</label><select multiple className="obsidian-input text-sm w-full h-24" value={data.tools || []} onChange={(e) => updateNode({ tools: Array.from(e.target.selectedOptions).map((o) => o.value) })}>{tools.map((t) => <option key={t.name} value={t.name}>{t.name}</option>)}</select></div>
              </>}
              {selectedNode.type === 'tool' && <div><label className="text-xs text-secondaryText block mb-1">Tool ID</label><select className="obsidian-input text-sm w-full" value={data.tool_id || ''} onChange={(e) => updateNode({ tool_id: e.target.value })}><option value="">Select tool...</option>{tools.map((t) => <option key={t.name} value={t.name}>{t.name}</option>)}</select></div>}
              {selectedNode.type === 'decision' && <div><label className="text-xs text-secondaryText block mb-1">Condition</label><input className="obsidian-input text-sm w-full" placeholder="context.get('result') == 'good'" value={data.condition || ''} onChange={(e) => updateNode({ condition: e.target.value })} /></div>}
              {selectedNode.type === 'wait' && <div><label className="text-xs text-secondaryText block mb-1">Approval Config (JSON)</label><textarea className="obsidian-input text-sm w-full h-20" placeholder='{"required_role": "admin"}' value={data.approval_config ? JSON.stringify(data.approval_config) : ''} onChange={(e) => { try { updateNode({ approval_config: e.target.value ? JSON.parse(e.target.value) : undefined }); } catch {} }} /></div>}
              <motion.button onClick={deleteNode} className="btn-danger flex items-center gap-2 text-sm mt-2" whileTap={{ scale: 0.96 }} whileHover={{ scale: 1.02 }}><Trash2 className="w-4 h-4" /> Delete Node</motion.button>
            </div>
          ) : <p className="text-sm text-secondaryText">Select a node to edit its properties.</p>}
        </div>
      </div>

      {/* Simulate Modal */}
      <AnimatePresence>
        {simulateOpen && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
            onClick={() => { setSimulateOpen(false); resetNodeStatus(); }}
          >
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 20 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 20 }}
              transition={{ type: 'spring', stiffness: 300, damping: 25 }}
              onClick={(e) => e.stopPropagation()}
              className="bg-surface-low border border-outline/20 rounded-xl p-6 w-[600px] max-h-[80vh] overflow-y-auto shadow-2xl"
            >
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-semibold text-primaryText flex items-center gap-2"><FlaskConical className="w-5 h-5 text-amber-400" /> Dry Run Results</h3>
                <motion.button
                  onClick={() => { setSimulateOpen(false); resetNodeStatus(); }}
                  className="text-secondaryText hover:text-primaryText"
                  whileTap={{ scale: 0.85 }}
                  whileHover={{ scale: 1.1, rotate: 90 }}
                >
                  <X className="w-5 h-5" />
                </motion.button>
              </div>
            {isSimulating ? (
              <div className="flex flex-col items-center justify-center py-12 gap-3">
                <Skeleton className="h-4 w-48" />
                <Skeleton className="h-3 w-32" />
              </div>
            ) : simulateResult?.error ? (
              <div className="text-red-400 py-4">{simulateResult.error}</div>
            ) : (
              <div className="space-y-4">
                <motion.div className="grid grid-cols-3 gap-3" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
                  <motion.div className="bg-surface-high rounded-lg p-3 text-center" whileHover={{ y: -2, boxShadow: '0 8px 30px rgba(0,229,255,0.06)' }}>
                    <div className="text-2xl font-bold text-cyan-400">{simulateResult?.estimated_tokens || 0}</div>
                    <div className="text-xs text-secondaryText mt-1">Est. Tokens</div>
                  </motion.div>
                  <motion.div className="bg-surface-high rounded-lg p-3 text-center" whileHover={{ y: -2, boxShadow: '0 8px 30px rgba(0,229,255,0.06)' }}>
                    <div className="text-2xl font-bold text-emerald-400">{simulateResult?.completed?.length || 0}</div>
                    <div className="text-xs text-secondaryText mt-1">Nodes Run</div>
                  </motion.div>
                  <motion.div className="bg-surface-high rounded-lg p-3 text-center" whileHover={{ y: -2, boxShadow: '0 8px 30px rgba(0,229,255,0.06)' }}>
                    <div className="text-2xl font-bold text-amber-400">{simulateResult?.decisions?.length || 0}</div>
                    <div className="text-xs text-secondaryText mt-1">Decisions</div>
                  </motion.div>
                </motion.div>
                <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}>
                  <h4 className="text-sm font-semibold text-primaryText mb-2">Path Taken</h4>
                  <div className="flex flex-wrap gap-2">
                    {(simulateResult?.path || []).map((nodeId: string, i: number) => {
                      const node = nodes.find((n) => n.id === nodeId);
                      const label = (node?.data as any)?.label;
                      return (
                        <motion.span
                          key={i}
                          initial={{ opacity: 0, scale: 0.9 }}
                          animate={{ opacity: 1, scale: 1 }}
                          transition={{ delay: i * 0.03 }}
                          className="px-2 py-1 rounded bg-primary/10 text-primary text-xs flex items-center gap-1"
                        >
                          {i > 0 && <span className="text-secondaryText mr-1">&rarr;</span>}
                          {label || nodeId}
                        </motion.span>
                      );
                    })}
                  </div>
                </motion.div>
                {simulateResult?.decisions?.length > 0 && (
                  <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}>
                    <h4 className="text-sm font-semibold text-primaryText mb-2">Decision Branches</h4>
                    <div className="space-y-2">
                      {simulateResult.decisions.map((d: any, i: number) => (
                        <motion.div
                          key={i}
                          initial={{ opacity: 0, x: -10 }}
                          animate={{ opacity: 1, x: 0 }}
                          transition={{ delay: i * 0.05 }}
                          className="flex items-center gap-3 bg-surface-high rounded-lg p-3"
                        >
                          <div className={`w-2 h-2 rounded-full ${d.result ? 'bg-emerald-400' : 'bg-red-400'}`} />
                          <div className="flex-1">
                            <div className="text-xs text-secondaryText">{(nodes.find((n) => n.id === d.node_id)?.data as any)?.label || d.node_id}</div>
                            <div className="text-sm text-primaryText font-mono">{d.condition || 'true'}</div>
                          </div>
                          <div className="text-xs font-bold text-emerald-400">{d.result ? 'TRUE' : 'FALSE'}</div>
                        </motion.div>
                      ))}
                    </div>
                  </motion.div>
                )}
              </div>
            )}
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Parameter Binding Modal */}
      <AnimatePresence>
        {bindingModalOpen && selectedEdge && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
            onClick={() => setBindingModalOpen(false)}
          >
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 20 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 20 }}
              transition={{ type: 'spring', stiffness: 300, damping: 25 }}
              onClick={(e) => e.stopPropagation()}
              className="bg-surface-low border border-outline/20 rounded-xl p-6 w-[500px] max-h-[80vh] overflow-y-auto shadow-2xl"
            >
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-semibold text-primaryText flex items-center gap-2"><Link2 className="w-5 h-5 text-primary" /> Parameter Binding</h3>
                <motion.button
                  onClick={() => setBindingModalOpen(false)}
                  className="text-secondaryText hover:text-primaryText"
                  whileTap={{ scale: 0.85 }}
                  whileHover={{ scale: 1.1, rotate: 90 }}
                >
                  <X className="w-5 h-5" />
                </motion.button>
              </div>
            <div className="text-xs text-secondaryText mb-4">
              Edge: {(sourceNode?.data as any)?.label || selectedEdge.source} &rarr; {(targetNode?.data as any)?.label || selectedEdge.target}
            </div>

            <div className="space-y-3 mb-4">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs text-secondaryText block mb-1">Source Output</label>
                  <select className="obsidian-input text-sm w-full" value={tempBinding.sourceOutput} onChange={(e) => setTempBinding((p) => ({ ...p, sourceOutput: e.target.value }))}>
                    <option value="">Select...</option>
                    {getSourceOutputs(sourceNode?.type as string).map((o) => <option key={o} value={o}>{o}</option>)}
                  </select>
                </div>
                <div>
                  <label className="text-xs text-secondaryText block mb-1">Target Input</label>
                  <select className="obsidian-input text-sm w-full" value={tempBinding.targetInput} onChange={(e) => setTempBinding((p) => ({ ...p, targetInput: e.target.value }))}>
                    <option value="">Select...</option>
                    {getTargetInputs(targetNode?.type as string).map((i) => <option key={i} value={i}>{i}</option>)}
                  </select>
                </div>
              </div>
              <div>
                <label className="text-xs text-secondaryText block mb-1">Transform (optional)</label>
                <input className="obsidian-input text-sm w-full" placeholder="{{output | upper}}" value={tempBinding.transform} onChange={(e) => setTempBinding((p) => ({ ...p, transform: e.target.value }))} />
              </div>
              <motion.button onClick={addBinding} className="btn-primary text-sm w-full" whileTap={{ scale: 0.96 }} whileHover={{ scale: 1.01 }}>Add Binding</motion.button>
            </div>

            <div className="space-y-2">
              <h4 className="text-xs font-bold uppercase tracking-widest text-secondaryText">Current Bindings</h4>
              {(bindings[selectedEdge.id] || []).length === 0 && <p className="text-sm text-secondaryText">No bindings configured.</p>}
              {(bindings[selectedEdge.id] || []).map((b, i) => (
                <motion.div
                  key={i}
                  initial={{ opacity: 0, y: 4 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: i * 0.03 }}
                  className="flex items-center gap-2 bg-surface-high rounded-lg p-2 text-sm"
                >
                  <span className="text-primary font-mono">{b.sourceOutput}</span>
                  <span className="text-secondaryText">&rarr;</span>
                  <span className="text-emerald-400 font-mono">{b.targetInput}</span>
                  {b.transform && <span className="text-xs text-amber-400 bg-amber-400/10 px-1 rounded">{b.transform}</span>}
                  <motion.button onClick={() => removeBinding(selectedEdge.id, i)} className="ml-auto text-red-400 hover:text-red-300" whileTap={{ scale: 0.85 }} whileHover={{ scale: 1.1 }}><X className="w-4 h-4" /></motion.button>
                </motion.div>
              ))}
            </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

export default function WorkflowBuilderV2() {
  return (
    <ReactFlowProvider>
      <FlowCanvas />
    </ReactFlowProvider>
  );
}

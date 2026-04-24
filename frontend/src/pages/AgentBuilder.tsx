import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { Bot, Save, Wrench, Database, Loader2, Trash2, Edit2, Check, X } from 'lucide-react';
import { apiClient } from '../api/client';
import type { AgentInfo } from '../api/client';

const AgentBuilder = () => {
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [tools, setTools] = useState<Array<{name: string; description: string}>>([]);
  const [loading, setLoading] = useState(true);
  const [actionError, setActionError] = useState('');

  // Form state
  const [name, setName] = useState('');
  const [prompt, setPrompt] = useState('');
  const [model, setModel] = useState('gpt-4o');
  const [temperature, setTemperature] = useState(0.7);
  const [maxTokens, setMaxTokens] = useState(2048);
  const [assignedTools, setAssignedTools] = useState<string[]>([]);
  const [editingAgentId, setEditingAgentId] = useState<string | null>(null);

  const refresh = async () => {
    setActionError('');
    try {
      const [agentData, toolData] = await Promise.all([apiClient.listAgents(), apiClient.getTools()]);
      setAgents(agentData);
      setTools(toolData.map((tool) => ({ name: tool.name, description: tool.description })));
    } catch (error) {
      setActionError(error instanceof Error ? error.message : 'Failed to load agents');
    }
  };

  const resetForm = () => {
    setName('');
    setPrompt('');
    setModel('gpt-4o');
    setTemperature(0.7);
    setMaxTokens(2048);
    setAssignedTools([]);
    setEditingAgentId(null);
  };

  const createAgent = async () => {
    if (!name.trim()) return;
    setActionError('');
    try {
      await apiClient.createAgent({
        name: name.trim(),
        role: 'custom',
        system_prompt: prompt.trim() || undefined,
        model,
        temperature,
        max_tokens: maxTokens,
        tools: assignedTools,
      });
      resetForm();
      await refresh();
    } catch (error) {
      setActionError(error instanceof Error ? error.message : 'Failed to create agent');
    }
  };

  const updateAgent = async () => {
    if (!editingAgentId || !name.trim()) return;
    setActionError('');
    try {
      await apiClient.updateAgent(editingAgentId, {
        name: name.trim(),
        role: 'custom',
        system_prompt: prompt.trim() || undefined,
        model,
        temperature,
        max_tokens: maxTokens,
        tools: assignedTools,
      });
      resetForm();
      await refresh();
    } catch (error) {
      setActionError(error instanceof Error ? error.message : 'Failed to update agent');
    }
  };

  const deleteAgent = async (agentId: string) => {
    if (!confirm('Are you sure you want to delete this agent?')) return;
    setActionError('');
    try {
      await apiClient.deleteAgent(agentId);
      await refresh();
    } catch (error) {
      setActionError(error instanceof Error ? error.message : 'Failed to delete agent');
    }
  };

  const startEdit = (agent: AgentInfo) => {
    setEditingAgentId(agent.agent_id);
    setName(agent.name);
    setPrompt(agent.system_prompt || '');
    setModel(agent.model || 'gpt-4o');
    setTemperature(agent.temperature || 0.7);
    setMaxTokens(agent.max_tokens || 2048);
    setAssignedTools(agent.tools || []);
  };

  const toggleTool = (toolName: string) => {
    setAssignedTools(prev =>
      prev.includes(toolName) ? prev.filter(t => t !== toolName) : [...prev, toolName]
    );
  };

  useEffect(() => {
    refresh().finally(() => setLoading(false));
  }, []);

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex flex-col gap-8 h-full pb-10">
      {actionError && (
        <div className="p-4 rounded-lg border border-[#FF4B4B]/20 bg-[#FF4B4B]/10 text-sm text-[#FF4B4B]">
          {actionError}
        </div>
      )}

      <div className="flex justify-between items-end">
        <div>
          <h1 className="text-3xl font-bold tracking-tight mb-1 cursor-default">Agent Builder</h1>
          <p className="text-secondaryText text-sm">Configure agent capabilities and tools.</p>
        </div>
        <div className="flex gap-2">
          {editingAgentId && (
            <button className="btn-secondary flex items-center gap-2" onClick={resetForm}>
              <X className="w-4 h-4" /> Cancel
            </button>
          )}
          <button
            className="btn-primary flex items-center gap-2 shadow-glow-cyan"
            onClick={editingAgentId ? updateAgent : createAgent}
          >
            {editingAgentId ? <Check className="w-4 h-4" /> : <Save className="w-4 h-4" />}
            {editingAgentId ? 'Update Agent' : 'Save Configuration'}
          </button>
        </div>
      </div>

      {loading ? (
        <div className="flex items-center gap-2 text-secondaryText py-8"><Loader2 className="w-4 h-4 animate-spin" /> Loading...</div>
      ) : (
        <div className="flex flex-col lg:flex-row gap-6 h-full min-h-[600px]">
          <div className="flex-1 flex flex-col gap-6">
            <div className="obsidian-panel border border-outline/10 p-6">
              <h2 className="text-lg font-semibold tracking-tight mb-6 flex items-center gap-2"><Bot className="w-5 h-5 text-primary" /> Core Identity</h2>
              <div className="space-y-5">
                <div>
                  <label className="block text-xs font-semibold tracking-widest uppercase text-secondaryText mb-2">Agent Name</label>
                  <input type="text" className="w-full obsidian-input" placeholder="e.g. Data Researcher" value={name} onChange={(e) => setName(e.target.value)} />
                </div>
                <div>
                  <label className="block text-xs font-semibold tracking-widest uppercase text-secondaryText mb-2">System Prompt / Instructions</label>
                  <textarea className="w-full obsidian-input min-h-[120px] resize-none" placeholder="Define the agent's behavior..." value={prompt} onChange={(e) => setPrompt(e.target.value)} />
                </div>
                <div className="grid grid-cols-3 gap-4">
                  <div>
                    <label className="block text-xs font-semibold tracking-widest uppercase text-secondaryText mb-2">Model</label>
                    <input type="text" className="w-full obsidian-input" value={model} onChange={(e) => setModel(e.target.value)} />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold tracking-widest uppercase text-secondaryText mb-2">Temperature</label>
                    <input type="number" step="0.1" min="0" max="2" className="w-full obsidian-input" value={temperature} onChange={(e) => setTemperature(parseFloat(e.target.value))} />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold tracking-widest uppercase text-secondaryText mb-2">Max Tokens</label>
                    <input type="number" step="256" min="256" max="8192" className="w-full obsidian-input" value={maxTokens} onChange={(e) => setMaxTokens(parseInt(e.target.value))} />
                  </div>
                </div>
              </div>
            </div>

            <div className="obsidian-panel border border-outline/10 p-6 flex-1">
              <h2 className="text-lg font-semibold tracking-tight mb-6 flex items-center gap-2"><Wrench className="w-5 h-5 text-primary" /> Capabilities</h2>
              <div className="space-y-4 mb-6">
                <label className="block text-xs font-semibold tracking-widest uppercase text-secondaryText">Assigned Tools</label>
                {tools.map((tool, idx) => (
                  <div key={idx} className="flex justify-between items-center p-3 rounded-lg bg-surface-highest border border-outline/5">
                    <div className="flex items-center gap-3">
                      <Database className="w-4 h-4 text-primary" />
                      <span className="font-medium text-sm">{tool.name}</span>
                    </div>
                    <input
                      type="checkbox"
                      checked={assignedTools.includes(tool.name)}
                      onChange={() => toggleTool(tool.name)}
                      className="w-4 h-4 rounded border-outline/20 bg-surface-highest text-primary focus:ring-primary"
                    />
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="w-full lg:w-1/3 obsidian-panel border border-outline/10 p-0 flex flex-col overflow-hidden hidden lg:flex">
            <div className="p-4 border-b border-outline/10 bg-surface-lowest">
              <h2 className="text-sm font-semibold tracking-tight">Saved Agents</h2>
            </div>
            <div className="flex-1 p-4 flex flex-col gap-3 bg-background/50 overflow-y-auto">
              {agents.map((agent) => (
                <div key={agent.agent_id} className="p-3 rounded-lg bg-surface-highest border border-outline/5">
                  <div className="flex justify-between items-start">
                    <div>
                      <span className="font-medium text-sm">{agent.name}</span>
                      <span className="text-xs text-secondaryText uppercase ml-2">{agent.role}</span>
                    </div>
                    <div className="flex gap-1">
                      <button onClick={() => startEdit(agent)} className="p-1 rounded hover:bg-primary/10 text-primary">
                        <Edit2 className="w-3 h-3" />
                      </button>
                      <button onClick={() => deleteAgent(agent.agent_id)} className="p-1 rounded hover:bg-[#FF4B4B]/10 text-[#FF4B4B]">
                        <Trash2 className="w-3 h-3" />
                      </button>
                    </div>
                  </div>
                  <p className="text-xs text-secondaryText mt-2 line-clamp-3">{agent.system_prompt}</p>
                  {agent.tools && agent.tools.length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-2">
                      {agent.tools.map(t => (
                        <span key={t} className="text-[10px] px-1.5 py-0.5 rounded bg-primary/10 text-primary">{t}</span>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </motion.div>
  );
};

export default AgentBuilder;

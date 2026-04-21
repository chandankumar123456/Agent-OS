import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { Bot, Save, Plus, Trash2, Wrench, Database, Loader2 } from 'lucide-react';
import { apiClient } from '../api/client';

const AgentBuilder = () => {
  const [agents, setAgents] = useState<Array<{agent_id: string; name: string; role: string; status: string; tools?: string[]; system_prompt?: string}>>([]);
  const [tools, setTools] = useState<Array<{name: string; description: string}>>([]);
  const [loading, setLoading] = useState(true);
  const [name, setName] = useState('');
  const [prompt, setPrompt] = useState('');

  const refresh = async () => {
    const [agentData, toolData] = await Promise.all([apiClient.listAgents(), apiClient.getTools()]);
    setAgents(agentData);
    setTools(toolData.map((tool) => ({ name: tool.name, description: tool.description })));
  };

  const createAgent = async () => {
    if (!name.trim()) return;
    await apiClient.createAgent({ name: name.trim(), role: 'custom', system_prompt: prompt.trim() || undefined, tools: [] });
    setName('');
    setPrompt('');
    await refresh();
  };

  const deleteAgent = async (agentId: string) => {
    await apiClient.deleteAgent(agentId);
    await refresh();
  };

  useEffect(() => {
    refresh().finally(() => setLoading(false));
  }, []);

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex flex-col gap-8 h-full pb-10">
      <div className="flex justify-between items-end">
        <div>
          <h1 className="text-3xl font-bold tracking-tight mb-1 cursor-default">Agent Builder</h1>
          <p className="text-secondaryText text-sm">Configure agent capabilities and tools.</p>
        </div>
        <button className="btn-primary flex items-center gap-2 shadow-glow-cyan" onClick={createAgent}>
          <Save className="w-4 h-4" /> Save Configuration
        </button>
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
                    <button className="text-secondaryText hover:text-[#FF4B4B] transition-colors" onClick={() => deleteAgent(agents[0]?.agent_id || '')}><Trash2 className="w-4 h-4" /></button>
                  </div>
                ))}
              </div>
              <button className="w-full btn-secondary flex items-center justify-center gap-2 border border-dashed border-outline/20 bg-transparent hover:bg-surface-highest hover:border-primary">
                <Plus className="w-4 h-4" /> Attach New Tool
              </button>
            </div>
          </div>

          <div className="w-full lg:w-1/3 obsidian-panel border border-outline/10 p-0 flex flex-col overflow-hidden hidden lg:flex">
            <div className="p-4 border-b border-outline/10 bg-surface-lowest">
              <h2 className="text-sm font-semibold tracking-tight">Saved Agents</h2>
            </div>
            <div className="flex-1 p-4 flex flex-col gap-3 bg-background/50 overflow-y-auto">
              {agents.map((agent) => (
                <div key={agent.agent_id} className="p-3 rounded-lg bg-surface-highest border border-outline/5">
                  <div className="flex justify-between items-center">
                    <span className="font-medium text-sm">{agent.name}</span>
                    <span className="text-xs text-secondaryText uppercase">{agent.role}</span>
                  </div>
                  <p className="text-xs text-secondaryText mt-2 line-clamp-3">{agent.system_prompt}</p>
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

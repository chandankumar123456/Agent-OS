import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { Search, Database, Globe, Wrench, Settings2, Plus, Play, Loader2 } from 'lucide-react';
import { apiClient } from '../api/client';

const iconMap: Record<string, any> = {
  web_search: Search,
  calculator: Database,
  text_processor: Globe,
};

const Tools = () => {
  const [registry, setRegistry] = useState<Array<{ name: string; description: string; type: string; status: string; parameters?: Record<string, any> }>>([]);
  const [form, setForm] = useState({ name: '', description: '', type: 'custom' });
  const [loading, setLoading] = useState(true);
  const [executingTool, setExecutingTool] = useState<string | null>(null);
  const [executionResult, setExecutionResult] = useState<Record<string, any> | null>(null);
  const [paramValues, setParamValues] = useState<Record<string, string>>({});

  const refresh = async () => {
    const tools = await apiClient.getTools();
    setRegistry(tools);
  };

  useEffect(() => {
    refresh().finally(() => setLoading(false));
  }, []);

  const createTool = async () => {
    if (!form.name || !form.description) return;
    await apiClient.createTool({ name: form.name, description: form.description, type: form.type });
    setForm({ name: '', description: '', type: 'custom' });
    await refresh();
  };

  const executeTool = async (toolName: string) => {
    setExecutingTool(toolName);
    setExecutionResult(null);
    try {
      const params: Record<string, any> = {};
      Object.entries(paramValues).forEach(([key, value]) => {
        try {
          params[key] = JSON.parse(value);
        } catch {
          params[key] = value;
        }
      });
      const result = await apiClient.executeTool(toolName, params);
      setExecutionResult(result);
    } catch (error) {
      setExecutionResult({ error: error instanceof Error ? error.message : 'Execution failed' });
    } finally {
      setExecutingTool(null);
    }
  };

  const getParamFields = (tool: any) => {
    const params = tool.parameters || {};
    if (typeof params === 'object' && params.properties) {
      return Object.entries(params.properties as Record<string, any>).map(([key, schema]) => ({
        key,
        type: schema.type || 'string',
        description: schema.description || key,
      }));
    }
    return [];
  };

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex flex-col gap-6">
      <div className="flex justify-between items-end mb-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight mb-1 cursor-default">Tool Registry</h1>
          <p className="text-secondaryText text-sm">Registered backend tools available to agents.</p>
        </div>
        <button className="btn-primary flex items-center gap-2" onClick={createTool}>
          <Plus className="w-4 h-4" /> Register Tool
        </button>
      </div>

      <div className="obsidian-panel border border-outline/10 p-4 grid grid-cols-1 md:grid-cols-3 gap-3">
        <input className="obsidian-input" placeholder="Tool name" value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} />
        <input className="obsidian-input" placeholder="Description" value={form.description} onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))} />
        <input className="obsidian-input" placeholder="Type" value={form.type} onChange={(e) => setForm((f) => ({ ...f, type: e.target.value }))} />
      </div>

      {executionResult && (
        <div className="obsidian-panel border border-outline/10 p-4">
          <h3 className="text-sm font-semibold mb-2">Execution Result</h3>
          <pre className="text-xs text-secondaryText overflow-x-auto whitespace-pre-wrap max-h-64">
            {JSON.stringify(executionResult, null, 2)}
          </pre>
          <button onClick={() => setExecutionResult(null)} className="mt-2 text-xs text-primary hover:underline">Clear</button>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 w-full">
        {loading ? (
          <div className="col-span-2 text-center py-12 text-secondaryText">Loading tools...</div>
        ) : registry.map((tool, idx) => {
          const Icon = iconMap[tool.name] || Wrench;
          const paramFields = getParamFields(tool);
          return (
            <motion.div
              key={idx}
              whileHover={{ scale: 1.01 }}
              className="obsidian-panel border border-outline/10 p-6 flex flex-col group transition-colors hover:border-outline/30"
            >
              <div className="flex justify-between items-start mb-4">
                <div className="flex items-center gap-4">
                  <div className="w-12 h-12 rounded-xl bg-surface-highest flex items-center justify-center group-hover:bg-primary/5 transition-colors border border-outline/5">
                    <Icon className="w-6 h-6 text-primary" />
                  </div>
                  <div>
                    <h3 className="text-lg font-semibold">{tool.name}</h3>
                    <p className="text-xs font-semibold tracking-widest uppercase text-secondaryText">{tool.type}</p>
                  </div>
                </div>
                <span className={`text-xs font-bold uppercase tracking-widest px-2 py-1 rounded bg-background ${tool.status === 'active' ? 'text-[#00FF88]' : 'text-secondaryText'}`}>
                  {tool.status}
                </span>
              </div>

              <p className="text-sm text-secondaryText mb-4">{tool.description}</p>

              {paramFields.length > 0 && (
                <div className="space-y-2 mb-4">
                  <p className="text-xs font-semibold uppercase tracking-widest text-secondaryText">Parameters</p>
                  {paramFields.map((field) => (
                    <div key={field.key} className="flex gap-2">
                      <input
                        className="flex-1 obsidian-input text-xs py-2"
                        placeholder={`${field.description} (${field.type})`}
                        value={paramValues[`${tool.name}.${field.key}`] || ''}
                        onChange={(e) => setParamValues(prev => ({ ...prev, [`${tool.name}.${field.key}`]: e.target.value }))}
                      />
                    </div>
                  ))}
                </div>
              )}

              <div className="mt-auto flex gap-2 border-t border-outline/10 pt-4">
                <button
                  onClick={() => executeTool(tool.name)}
                  disabled={executingTool === tool.name}
                  className="btn-primary flex items-center gap-2 text-sm disabled:opacity-50"
                >
                  {executingTool === tool.name ? <Loader2 className="w-3 h-3 animate-spin" /> : <Play className="w-3 h-3" />}
                  Execute
                </button>
                <div className="flex items-center gap-2 text-primary text-sm ml-auto">
                  <Settings2 className="w-4 h-4" /> Configuration
                </div>
              </div>
            </motion.div>
          );
        })}
      </div>
    </motion.div>
  );
};

export default Tools;

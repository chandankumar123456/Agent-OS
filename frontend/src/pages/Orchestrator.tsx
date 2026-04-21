import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { CheckCircle2, Play, GitMerge, Loader2 } from 'lucide-react';
import { apiClient } from '../api/client';

const Orchestrator = () => {
  const [agents, setAgents] = useState<Array<{agent_id: string; name: string; role: string; status: string}>>([]);
  const [loading, setLoading] = useState(true);
  const [taskId, setTaskId] = useState('');
  const [taskStatus, setTaskStatus] = useState<string>('idle');

  useEffect(() => {
    apiClient.listAgents()
      .then(setAgents)
      .finally(() => setLoading(false));
  }, []);

  const executeDemo = async () => {
    setTaskStatus('running');
    const task = await apiClient.createTask({ query: 'Run orchestrator demo', config: { max_steps: 10, timeout: 300 } });
    setTaskId(task.task_id);
    await apiClient.pollTaskStatus(task.task_id, (update) => setTaskStatus(update.status), 1500, 40);
    setTaskStatus('completed');
  };

  const refreshAgents = async () => {
    setLoading(true);
    try {
      setAgents(await apiClient.listAgents());
    } finally {
      setLoading(false);
    }
  };

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex flex-col gap-8 h-full">
      <div className="flex justify-between items-end">
        <div>
          <h1 className="text-3xl font-bold tracking-tight mb-1 cursor-default">Workflow Orchestrator</h1>
          <p className="text-secondaryText text-sm">Multi-agent pipeline status.</p>
        </div>
        <div className="flex gap-3">
          <button className="btn-secondary flex items-center gap-2" onClick={refreshAgents}>
            <GitMerge className="w-4 h-4" /> Add Branch
          </button>
          <button className="btn-primary flex items-center gap-2 shadow-glow-cyan" onClick={executeDemo}>
            <Play className="w-4 h-4" /> Execute Flow
          </button>
        </div>
      </div>

      <div className="obsidian-panel border border-outline/10 p-4 text-sm text-secondaryText">
        Current task: <span className="text-primaryText">{taskId || 'none'}</span> | Status: <span className="text-primaryText">{taskStatus}</span>
      </div>

      <div className="flex-1 flex justify-center py-12 obsidian-panel border border-outline/10 relative overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center gap-2 text-secondaryText">
            <Loader2 className="w-5 h-5 animate-spin" /> Loading agents...
          </div>
        ) : (
          <div className="w-full max-w-2xl relative">
            <div className="absolute left-8 top-8 bottom-8 w-px border-l-2 border-dashed border-outline/20"></div>
            <div className="flex flex-col gap-8">
              {agents.map((agent, idx) => (
                <motion.div key={agent.agent_id} initial={{ opacity: 0, x: -20 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: idx * 0.15 }} className="flex items-start gap-8 z-10 relative">
                  <div className="w-16 h-16 rounded-2xl flex items-center justify-center border-2 bg-background relative border-[#00FF88] text-[#00FF88]">
                    <CheckCircle2 className="w-6 h-6" />
                  </div>
                  <div className="flex-1 p-6 rounded-xl border bg-surface-low border-outline/10">
                    <div className="flex justify-between items-start mb-2">
                      <h3 className="text-lg font-semibold">{agent.name}</h3>
                      <span className="text-xs font-bold uppercase tracking-widest px-2 py-1 rounded bg-background text-[#00FF88]">{agent.status}</span>
                    </div>
                    <p className="text-secondaryText text-sm">{agent.role}</p>
                  </div>
                </motion.div>
              ))}
            </div>
          </div>
        )}
      </div>
    </motion.div>
  );
};

export default Orchestrator;

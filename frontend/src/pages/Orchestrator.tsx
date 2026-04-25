import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { CheckCircle2, RefreshCw } from 'lucide-react';
import { apiClient } from '../api/client';
import { Skeleton } from '../components/ui/Skeleton';
import { StatusBadge } from '../components/ui/StatusBadge';

const Orchestrator = () => {
  const [agents, setAgents] = useState<Array<{agent_id: string; name: string; role: string; status: string}>>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    apiClient.listAgents()
      .then(setAgents)
      .finally(() => setLoading(false));
  }, []);

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
        <motion.button
          className="btn-secondary flex items-center gap-2"
          onClick={refreshAgents}
          whileTap={{ scale: 0.96 }}
          whileHover={{ scale: 1.02 }}
        >
          <RefreshCw className="w-4 h-4" /> Refresh Agents
        </motion.button>
      </div>

      <div className="flex-1 flex justify-center py-12 obsidian-panel border border-outline/10 relative overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <div className="flex flex-col items-center gap-3">
              <Skeleton className="h-12 w-12 rounded-full" />
              <Skeleton className="h-4 w-32" />
            </div>
          </div>
        ) : (
          <div className="w-full max-w-2xl relative">
            <motion.div
              className="absolute left-8 top-8 bottom-8 w-px border-l-2 border-dashed border-outline/20"
              initial={{ scaleY: 0 }}
              animate={{ scaleY: 1 }}
              transition={{ duration: 0.8, ease: 'easeOut' }}
              style={{ originY: 0 }}
            />
            <div className="flex flex-col gap-8">
              {agents.map((agent, idx) => (
                <motion.div
                  key={agent.agent_id}
                  initial={{ opacity: 0, x: -20 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: idx * 0.15, type: 'spring', stiffness: 300 }}
                  whileHover={{ x: 4, boxShadow: '0 8px 30px rgba(0,229,255,0.06)' }}
                  className="flex items-start gap-8 z-10 relative"
                >
                  <motion.div
                    className="w-16 h-16 rounded-2xl flex items-center justify-center border-2 bg-background relative border-[#00FF88] text-[#00FF88]"
                    whileHover={{ scale: 1.05, rotate: 5 }}
                    transition={{ type: 'spring', stiffness: 400 }}
                  >
                    <CheckCircle2 className="w-6 h-6" />
                  </motion.div>
                  <div className="flex-1 p-6 rounded-xl border bg-surface-low border-outline/10">
                    <div className="flex justify-between items-start mb-2">
                      <h3 className="text-lg font-semibold">{agent.name}</h3>
                      <StatusBadge status={agent.status || 'idle'} />
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

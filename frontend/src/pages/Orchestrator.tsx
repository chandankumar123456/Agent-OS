import { motion } from 'framer-motion';
import { Waypoints, CheckCircle2, Play, GitMerge } from 'lucide-react';

const Orchestrator = () => {
  const steps = [
    { id: 1, agent: 'Planner Agent', desc: 'Decomposes task into sub-goals', status: 'completed' },
    { id: 2, agent: 'Data Researcher', desc: 'Searches internal DBs for metrics', status: 'completed' },
    { id: 3, agent: 'Logic Executor', desc: 'Synthesizes findings into report structure', status: 'running' },
    { id: 4, agent: 'Verifier Agent', desc: 'Ensures schema and logical coherence', status: 'pending' },
  ];

  return (
    <motion.div 
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="flex flex-col gap-8 h-full"
    >
      <div className="flex justify-between items-end">
        <div>
          <h1 className="text-3xl font-bold tracking-tight mb-1 cursor-default">Workflow Orchestrator</h1>
          <p className="text-secondaryText text-sm">Static pipeline preview. Live workflow editing is not connected yet.</p>
        </div>
        <div className="flex gap-3">
          <button className="btn-secondary flex items-center gap-2 opacity-60 cursor-not-allowed" disabled>
            <GitMerge className="w-4 h-4" /> Add Branch
          </button>
          <button className="btn-primary flex items-center gap-2 shadow-glow-cyan opacity-60 cursor-not-allowed" disabled>
            <Play className="w-4 h-4" /> Execute Flow
          </button>
        </div>
      </div>

      <div className="flex-1 flex justify-center py-12 obsidian-panel border border-outline/10 relative overflow-hidden">
        {/* Background Decorative */}
        <div className="absolute top-0 right-0 w-96 h-96 bg-primary/5 rounded-full blur-[100px] pointer-events-none"></div>

        <div className="w-full max-w-2xl relative">
          {/* Connecting Vertical Line */}
          <div className="absolute left-8 top-8 bottom-8 w-px border-l-2 border-dashed border-outline/20"></div>

          <div className="flex flex-col gap-8">
            {steps.map((step, idx) => (
              <motion.div 
                key={step.id} 
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: idx * 0.15 }}
                className="flex items-start gap-8 z-10 relative"
              >
                {/* Node Milestone */}
                <div className={`w-16 h-16 rounded-2xl flex items-center justify-center border-2 bg-background relative ${
                    step.status === 'completed' ? 'border-[#00FF88] text-[#00FF88]' :
                    step.status === 'running' ? 'border-primary text-primary shadow-[0_0_20px_rgba(0,229,255,0.2)]' :
                    'border-outline/30 text-secondaryText'
                }`}>
                  {step.status === 'completed' && <CheckCircle2 className="w-6 h-6" />}
                  {step.status === 'running' && <Waypoints className="w-6 h-6 animate-pulse" />}
                  {step.status === 'pending' && <span className="text-lg font-bold">{step.id}</span>}
                </div>

                {/* Content Card */}
                <div className={`flex-1 p-6 rounded-xl border transition-colors ${
                  step.status === 'running' ? 'bg-surface-highest border-primary/30 shadow-glow-cyan' : 
                  'bg-surface-low border-outline/10 hover:border-outline/30'
                }`}>
                  <div className="flex justify-between items-start mb-2">
                    <h3 className="text-lg font-semibold">{step.agent}</h3>
                    <span className={`text-xs font-bold uppercase tracking-widest px-2 py-1 rounded bg-background ${
                      step.status === 'completed' ? 'text-[#00FF88]' :
                      step.status === 'running' ? 'text-primary' : 'text-secondaryText'
                    }`}>{step.status}</span>
                  </div>
                  <p className="text-secondaryText text-sm">{step.desc}</p>
                </div>
              </motion.div>
            ))}
          </div>
          
          <button className="mt-12 ml-6 text-primary hover:text-primary-container text-sm font-medium flex items-center gap-2 transition-colors opacity-60 cursor-not-allowed" disabled>
            <span className="w-4 h-4 rounded-full border border-primary flex items-center justify-center">+</span> 
            Append Next Node
          </button>
        </div>
      </div>
    </motion.div>
  );
};

export default Orchestrator;

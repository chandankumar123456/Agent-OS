import { useState } from 'react';
import { motion } from 'framer-motion';
import { Bot, Save, Plus, Trash2, Wrench, Database } from 'lucide-react';

const AgentBuilder = () => {
  const [tools] = useState(['SearchAPI', 'PostgreSQL_Connector']);

  return (
    <motion.div 
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="flex flex-col gap-8 h-full pb-10"
    >
      <div className="flex justify-between items-end">
        <div>
          <h1 className="text-3xl font-bold tracking-tight mb-1 cursor-default">Agent Builder</h1>
          <p className="text-secondaryText text-sm">Preview-only UI for agent configuration. Persistence is not connected yet.</p>
        </div>
        <button className="btn-primary flex items-center gap-2 shadow-glow-cyan opacity-60 cursor-not-allowed" disabled>
          <Save className="w-4 h-4" /> Save Configuration
        </button>
      </div>

      <div className="flex flex-col lg:flex-row gap-6 h-full min-h-[600px]">
        {/* Configuration Panel */}
        <div className="flex-1 flex flex-col gap-6">
          <div className="obsidian-panel border border-outline/10 p-6">
            <h2 className="text-lg font-semibold tracking-tight mb-6 flex items-center gap-2">
              <Bot className="w-5 h-5 text-primary" /> Core Identity
            </h2>
            <div className="space-y-5">
              <div>
                <label className="block text-xs font-semibold tracking-widest uppercase text-secondaryText mb-2">Agent Name</label>
                <input type="text" className="w-full obsidian-input" placeholder="e.g. Data Researcher" defaultValue="Data Researcher" readOnly />
              </div>
              <div>
                <label className="block text-xs font-semibold tracking-widest uppercase text-secondaryText mb-2">System Prompt / Instructions</label>
                <textarea className="w-full obsidian-input min-h-[120px] resize-none" placeholder="Define the agent's behavior..." defaultValue="You are a highly analytical research agent. Extract key data points from provided URLs." readOnly />
              </div>
            </div>
          </div>

          <div className="obsidian-panel border border-outline/10 p-6 flex-1">
            <h2 className="text-lg font-semibold tracking-tight mb-6 flex items-center gap-2">
              <Wrench className="w-5 h-5 text-primary" /> Capabilities
            </h2>
            
            <div className="space-y-4 mb-6">
              <label className="block text-xs font-semibold tracking-widest uppercase text-secondaryText">Assigned Tools</label>
              {tools.map((tool, idx) => (
                <div key={idx} className="flex justify-between items-center p-3 rounded-lg bg-surface-highest border border-outline/5 hover:border-outline/20 transition-colors">
                  <div className="flex items-center gap-3">
                    <Database className="w-4 h-4 text-primary" />
                    <span className="font-medium text-sm">{tool}</span>
                  </div>
                    <button className="text-secondaryText hover:text-[#FF4B4B] transition-colors opacity-60 cursor-not-allowed" disabled>
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                ))}
              </div>
              
              <button className="w-full btn-secondary flex items-center justify-center gap-2 border border-dashed border-outline/20 bg-transparent hover:bg-surface-highest hover:border-primary opacity-60 cursor-not-allowed" disabled>
                <Plus className="w-4 h-4" /> Attach New Tool
              </button>
            </div>
        </div>

        {/* Live Test Panel */}
        <div className="w-full lg:w-1/3 obsidian-panel border border-outline/10 p-0 flex flex-col overflow-hidden hidden lg:flex">
          <div className="p-4 border-b border-outline/10 bg-surface-lowest">
            <h2 className="text-sm font-semibold tracking-tight">Test Sandbox</h2>
          </div>
          <div className="flex-1 p-4 flex flex-col gap-4 bg-background/50 overflow-y-auto">
            <div className="self-end bg-surface-highest text-primaryText p-3 rounded-xl max-w-[85%] text-sm border border-outline/5">
              Analyze the quarterly revenue metrics from the link.
            </div>
            <div className="self-start relative">
              <div className="flex items-center gap-2 mb-1">
                <Bot className="w-3 h-3 text-primary" /> <span className="text-xs text-secondaryText font-medium">Data Researcher</span>
              </div>
              <div className="bg-surface-low border border-primary/20 text-primaryText p-3 rounded-xl max-w-[95%] text-sm shadow-[0_0_15px_rgba(0,229,255,0.05)]">
                <span className="text-secondaryText italic text-xs block mb-2">Calling SearchAPI...</span>
                The quarterly revenue grew by 14% year-over-year. Key drivers were the enterprise division and new APAC expansions.
              </div>
            </div>
          </div>
          <div className="p-4 border-t border-outline/10 bg-surface-lowest flex items-center gap-2">
            <input type="text" className="flex-1 obsidian-input rounded-md py-2 border-none" placeholder="Send test command..." disabled />
            <button className="btn-primary px-3 py-2 rounded shadow-glow-cyan text-sm opacity-60 cursor-not-allowed" disabled><ArrowRight className="w-4 h-4" /></button>
          </div>
        </div>
      </div>
    </motion.div>
  );
};

// Local Arrow helper
const ArrowRight = ({className}: {className?: string}) => (
  <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}><path d="M5 12h14"/><path d="m12 5 7 7-7 7"/></svg>
)

export default AgentBuilder;

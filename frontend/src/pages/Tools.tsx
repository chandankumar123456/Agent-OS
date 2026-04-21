
import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { Search, Database, Globe, Wrench, Settings2 } from 'lucide-react';
import { apiClient } from '../api/client';

const Tools = () => {
  const [registry, setRegistry] = useState<Array<{ name: string; type: string; icon: any; status: string; desc: string }>>([]);

  useEffect(() => {
    apiClient.getMetrics().finally(() => {
      setRegistry([
        { name: 'web_search', type: 'Data Source', icon: Search, status: 'Active', desc: 'Backend registered web search tool.' },
        { name: 'calculator', type: 'Utility', icon: Database, status: 'Active', desc: 'Backend registered calculator tool.' },
        { name: 'text_processor', type: 'Utility', icon: Globe, status: 'Active', desc: 'Backend registered text processor tool.' },
      ]);
    });
  }, []);

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex flex-col gap-6">
      <div className="flex justify-between items-end mb-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight mb-1 cursor-default">Tool Registry</h1>
          <p className="text-secondaryText text-sm">Registered backend tools available to agents.</p>
        </div>
        <button className="btn-primary flex items-center gap-2" disabled>
          <Wrench className="w-4 h-4" /> Register Tool
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 w-full">
        {registry.map((tool, idx) => (
          <motion.div 
            key={idx}
            whileHover={{ scale: 1.01 }}
            className="obsidian-panel border border-outline/10 p-6 flex flex-col group transition-colors hover:border-outline/30 cursor-pointer"
          >
            <div className="flex justify-between items-start mb-4">
              <div className="flex items-center gap-4">
                <div className="w-12 h-12 rounded-xl bg-surface-highest flex items-center justify-center group-hover:bg-primary/5 transition-colors border border-outline/5">
                  <tool.icon className="w-6 h-6 text-primary" />
                </div>
                <div>
                  <h3 className="text-lg font-semibold">{tool.name}</h3>
                  <p className="text-xs font-semibold tracking-widest uppercase text-secondaryText">{tool.type}</p>
                </div>
              </div>
              <span className={`text-xs font-bold uppercase tracking-widest px-2 py-1 rounded bg-background ${
                    tool.status === 'Active' ? 'text-[#00FF88]' : 'text-secondaryText'
              }`}>{tool.status}</span>
            </div>
            
            <p className="text-sm text-secondaryText mb-6">{tool.desc}</p>
            
            <div className="mt-auto border-t border-outline/10 pt-4 cursor-pointer text-primary text-sm flex items-center gap-2 hover:text-primary-container">
              <Settings2 className="w-4 h-4"/> Configuration
            </div>
          </motion.div>
        ))}
      </div>
    </motion.div>
  );
};

export default Tools;

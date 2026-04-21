
import { motion } from 'framer-motion';
import { Save } from 'lucide-react';

const Settings = () => {
  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex flex-col gap-6 max-w-4xl mx-auto">
      <div className="flex justify-between items-end mb-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight mb-1 cursor-default">System Configuration</h1>
          <p className="text-secondaryText text-sm">Read-only configuration preview. Persistence is not wired yet.</p>
        </div>
        <button className="btn-primary flex items-center gap-2 opacity-60 cursor-not-allowed" disabled>
          <Save className="w-4 h-4" /> Save Default
        </button>
      </div>

      <div className="obsidian-panel border border-outline/10 p-8 flex flex-col gap-8">
        <div>
          <h2 className="text-lg font-semibold mb-4 pb-2 border-b border-outline/10">Base LLM Configurations</h2>
          <div className="grid grid-cols-2 gap-6">
            <div>
              <label className="block text-xs font-semibold tracking-widest uppercase text-secondaryText mb-2">Default Model</label>
                <select className="w-full obsidian-input" disabled>
                  <option>GPT-4o (OpenAI)</option>
                  <option>Claude 3.5 Sonnet (Anthropic)</option>
                  <option>Llama 3 70B (Groq)</option>
                </select>
            </div>
            <div>
              <label className="block text-xs font-semibold tracking-widest uppercase text-secondaryText mb-2">API Key</label>
                <input type="password" placeholder="sk-..." className="w-full obsidian-input" defaultValue="**********" readOnly />
            </div>
          </div>
        </div>

        <div>
          <h2 className="text-lg font-semibold mb-4 pb-2 border-b border-outline/10">Orchestrator Limits</h2>
          <div className="grid grid-cols-2 gap-6">
            <div>
              <label className="block text-xs font-semibold tracking-widest uppercase text-secondaryText mb-2">Max Retry Count</label>
              <input type="number" className="w-full obsidian-input" defaultValue={3} readOnly />
            </div>
            <div>
              <label className="block text-xs font-semibold tracking-widest uppercase text-secondaryText mb-2">Global Timeout (Seconds)</label>
              <input type="number" className="w-full obsidian-input" defaultValue={120} readOnly />
            </div>
          </div>
        </div>

        <div>
          <h2 className="text-lg font-semibold mb-4 pb-2 border-b border-outline/10">Memory Persistence</h2>
          <div className="grid grid-cols-1 gap-6">
            <div>
              <label className="block text-xs font-semibold tracking-widest uppercase text-secondaryText mb-2">PostgreSQL URI</label>
              <input type="text" className="w-full obsidian-input" defaultValue="postgresql://user:pass@localhost:5432/agentos" readOnly />
            </div>
          </div>
        </div>
      </div>
    </motion.div>
  );
};

export default Settings;

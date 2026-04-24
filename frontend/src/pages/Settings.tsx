import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { RotateCcw } from 'lucide-react';
import { apiClient } from '../api/client';

const Settings = () => {
  const [config, setConfig] = useState<Record<string, any>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [model, setModel] = useState('gpt-4o');
  const [actionError, setActionError] = useState('');

  const load = async () => {
    setActionError('');
    try {
      const data = await apiClient.getConfig();
      setConfig(data);
      setModel(data.OPENAI_MODEL);
    } catch (error) {
      setActionError(error instanceof Error ? error.message : 'Failed to load config');
    }
  };

  useEffect(() => {
    load().finally(() => setLoading(false));
  }, []);

  const saveModel = async (value: string) => {
    setSaving(true);
    setActionError('');
    try {
      await apiClient.updateConfig('OPENAI_MODEL', value);
      await load();
    } catch (error) {
      setActionError(error instanceof Error ? error.message : 'Failed to save config');
    } finally {
      setSaving(false);
    }
  };

  const reset = async () => {
    setSaving(true);
    setActionError('');
    try {
      await apiClient.resetConfig();
      await load();
    } catch (error) {
      setActionError(error instanceof Error ? error.message : 'Failed to reset config');
    } finally {
      setSaving(false);
    }
  };

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex flex-col gap-6 max-w-4xl mx-auto">
      <div className="flex justify-between items-end mb-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight mb-1 cursor-default">System Configuration</h1>
          <p className="text-secondaryText text-sm">Persistent runtime configuration.</p>
        </div>
        <button onClick={reset} className="btn-secondary flex items-center gap-2" disabled={saving}>
          <RotateCcw className="w-4 h-4" /> Reset
        </button>
      </div>

      {actionError && (
        <div className="p-4 rounded-lg border border-[#FF4B4B]/20 bg-[#FF4B4B]/10 text-sm text-[#FF4B4B]">
          {actionError}
        </div>
      )}

      {loading ? (
        <div className="text-center py-12 text-secondaryText">Loading config...</div>
      ) : (
        <div className="obsidian-panel border border-outline/10 p-8 flex flex-col gap-8">
          <div>
            <h2 className="text-lg font-semibold mb-4 pb-2 border-b border-outline/10">Base LLM Configurations</h2>
            <div className="grid grid-cols-2 gap-6">
              <div>
                <label className="block text-xs font-semibold tracking-widest uppercase text-secondaryText mb-2">Default Model</label>
                <select
                  className="w-full obsidian-input"
                  value={model}
                  onChange={(e) => setModel(e.target.value)}
                  onBlur={(e) => saveModel(e.target.value)}
                  disabled={saving}
                >
                  <option value="gpt-4o">gpt-4o</option>
                  <option value="claude-3-5-sonnet">claude-3-5-sonnet</option>
                  <option value="llama-3-70b">llama-3-70b</option>
                </select>
              </div>
              <div>
                <label className="block text-xs font-semibold tracking-widest uppercase text-secondaryText mb-2">Max Steps</label>
                <input type="number" className="w-full obsidian-input" value={config.MAX_STEPS_DEFAULT || 10} readOnly />
              </div>
            </div>
          </div>

          <div>
            <h2 className="text-lg font-semibold mb-4 pb-2 border-b border-outline/10">Orchestrator Limits</h2>
            <div className="grid grid-cols-2 gap-6">
              <div>
                <label className="block text-xs font-semibold tracking-widest uppercase text-secondaryText mb-2">Max Retry Count</label>
                <input type="number" className="w-full obsidian-input" value={config.MAX_RETRIES || 3} readOnly />
              </div>
              <div>
                <label className="block text-xs font-semibold tracking-widest uppercase text-secondaryText mb-2">Global Timeout (Seconds)</label>
                <input type="number" className="w-full obsidian-input" value={config.TIMEOUT_DEFAULT || 300} readOnly />
              </div>
            </div>
          </div>

          <div>
            <h2 className="text-lg font-semibold mb-4 pb-2 border-b border-outline/10">Execution Mode</h2>
            <div className="grid grid-cols-1 gap-6">
              <div>
                <label className="block text-xs font-semibold tracking-widest uppercase text-secondaryText mb-2">Use Celery</label>
                <input type="text" className="w-full obsidian-input" value={String(config.USE_CELERY)} readOnly />
              </div>
            </div>
          </div>
        </div>
      )}
    </motion.div>
  );
};

export default Settings;

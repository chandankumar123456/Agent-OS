import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { apiClient } from '../api/client';
import { Skeleton } from '../components/ui/Skeleton';
import { Check, X, Zap, Save, Key, Link2 } from 'lucide-react';

interface ProviderUI {
  name: string;
  label: string;
  apiKey: string;
  baseUrl: string;
  defaultModel: string;
  enabled: boolean;
  testing: boolean;
  testResult: { success?: boolean; message?: string } | null;
}

const Providers = () => {
  const [providers, setProviders] = useState<ProviderUI[]>([
    { name: 'openai', label: 'OpenAI', apiKey: '', baseUrl: '', defaultModel: 'gpt-4o', enabled: true, testing: false, testResult: null },
    { name: 'anthropic', label: 'Anthropic', apiKey: '', baseUrl: '', defaultModel: 'claude-3-5-sonnet-20241022', enabled: false, testing: false, testResult: null },
    { name: 'google', label: 'Google', apiKey: '', baseUrl: '', defaultModel: 'gemini-1.5-flash', enabled: false, testing: false, testResult: null },
    { name: 'ollama', label: 'Ollama', apiKey: '', baseUrl: 'http://localhost:11434', defaultModel: 'llama3', enabled: false, testing: false, testResult: null },
  ]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    apiClient
      .getProviders()
      .then((data) => {
        const mapped = providers.map((p) => {
          const found = data.find((d: any) => d.name === p.name);
          return found
            ? {
                ...p,
                apiKey: found.api_key ? '••••••••' : '',
                baseUrl: found.base_url || p.baseUrl,
                defaultModel: found.default_model || p.defaultModel,
                enabled: found.enabled,
              }
            : p;
        });
        setProviders(mapped);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const updateProvider = (name: string, patch: Partial<ProviderUI>) => {
    setProviders((prev) => prev.map((p) => (p.name === name ? { ...p, ...patch } : p)));
  };

  const testProvider = async (p: ProviderUI) => {
    updateProvider(p.name, { testing: true, testResult: null });
    try {
      const result = await apiClient.testProvider({
        name: p.name,
        api_key: p.apiKey === '••••••••' ? undefined : p.apiKey,
        base_url: p.baseUrl || undefined,
        default_model: p.defaultModel,
      });
      updateProvider(p.name, {
        testing: false,
        testResult: {
          success: result.success,
          message: result.response || result.error || 'Test completed',
        },
      });
    } catch (e: any) {
      updateProvider(p.name, { testing: false, testResult: { success: false, message: e.message } });
    }
  };

  const saveProvider = async (p: ProviderUI) => {
    try {
      if (p.name === 'openai') {
        if (p.apiKey !== '••••••••') await apiClient.updateConfig('OPENAI_API_KEY', p.apiKey);
        if (p.defaultModel) await apiClient.updateConfig('OPENAI_MODEL', p.defaultModel);
      } else if (p.name === 'anthropic') {
        if (p.apiKey !== '••••••••') await apiClient.updateConfig('ANTHROPIC_API_KEY', p.apiKey);
      } else if (p.name === 'google') {
        if (p.apiKey !== '••••••••') await apiClient.updateConfig('GOOGLE_API_KEY', p.apiKey);
      } else if (p.name === 'ollama') {
        if (p.baseUrl) await apiClient.updateConfig('OLLAMA_BASE_URL', p.baseUrl);
      }
      updateProvider(p.name, { testResult: { success: true, message: 'Saved (config updated)' } });
    } catch (e: any) {
      updateProvider(p.name, { testResult: { success: false, message: e.message } });
    }
  };

  if (loading) return <div className="text-center py-12"><Skeleton className="h-4 w-32 mx-auto" /></div>;

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex flex-col gap-6 max-w-5xl mx-auto">
      <div className="mb-4">
        <h1 className="text-3xl font-bold tracking-tight mb-1">LLM Providers</h1>
        <p className="text-secondaryText text-sm">Configure and test model provider connections.</p>
      </div>

      {error && (
        <div className="p-4 rounded-lg border border-[#FF4B4B]/20 bg-[#FF4B4B]/10 text-sm text-[#FF4B4B]">
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {providers.map((p) => (
          <motion.div key={p.name} className="bg-surface-low border border-outline/20 rounded-xl p-6 flex flex-col gap-4" whileHover={{ y: -3, boxShadow: '0 8px 30px rgba(0,229,255,0.06)' }} whileTap={{ scale: 0.99 }}>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Zap className="w-5 h-5 text-primary" />
                <h2 className="text-lg font-semibold">{p.label}</h2>
              </div>
              <label className="inline-flex items-center cursor-pointer">
                <input
                  type="checkbox"
                  className="sr-only peer"
                  checked={p.enabled}
                  onChange={(e) => updateProvider(p.name, { enabled: e.target.checked })}
                />
                <div className="relative w-11 h-6 bg-surface-high peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-primary transition-all duration-300" />
              </label>
            </div>

            <div className="flex flex-col gap-3">
              {p.name !== 'ollama' && (
                <div>
                  <label className="block text-xs font-semibold tracking-widest uppercase text-secondaryText mb-1">API Key</label>
                  <div className="relative">
                    <Key className="absolute left-3 top-2.5 w-4 h-4 text-secondaryText" />
                    <input
                      type="password"
                      className="w-full bg-surface-high border border-outline/10 rounded-lg py-2 pl-9 pr-3 text-sm focus:outline-none focus:border-primary transition-colors transition-transform duration-200 focus:scale-[1.01]"
                      placeholder="sk-..."
                      value={p.apiKey}
                      onChange={(e) => updateProvider(p.name, { apiKey: e.target.value })}
                    />
                  </div>
                </div>
              )}

              <div>
                <label className="block text-xs font-semibold tracking-widest uppercase text-secondaryText mb-1">Base URL / Endpoint</label>
                <div className="relative">
                  <Link2 className="absolute left-3 top-2.5 w-4 h-4 text-secondaryText" />
                  <input
                    type="text"
                    className="w-full bg-surface-high border border-outline/10 rounded-lg py-2 pl-9 pr-3 text-sm focus:outline-none focus:border-primary transition-colors transition-transform duration-200 focus:scale-[1.01]"
                    placeholder="https://api..."
                    value={p.baseUrl}
                    onChange={(e) => updateProvider(p.name, { baseUrl: e.target.value })}
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold tracking-widest uppercase text-secondaryText mb-1">Default Model</label>
                <input
                  type="text"
                  className="w-full bg-surface-high border border-outline/10 rounded-lg py-2 px-3 text-sm focus:outline-none focus:border-primary transition-colors transition-transform duration-200 focus:scale-[1.01]"
                  value={p.defaultModel}
                  onChange={(e) => updateProvider(p.name, { defaultModel: e.target.value })}
                />
              </div>
            </div>

            {p.testResult && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: 'auto' }}
                className={`p-3 rounded-lg text-sm flex items-start gap-2 ${
                  p.testResult.success
                    ? 'bg-emerald-500/10 border border-emerald-500/20 text-emerald-400'
                    : 'bg-[#FF4B4B]/10 border border-[#FF4B4B]/20 text-[#FF4B4B]'
                }`}
              >
                {p.testResult.success ? <Check className="w-4 h-4 mt-0.5 shrink-0" /> : <X className="w-4 h-4 mt-0.5 shrink-0" />}
                {p.testResult.message}
              </motion.div>
            )}

            <div className="flex gap-3 mt-auto">
              <motion.button
                onClick={() => testProvider(p)}
                disabled={p.testing}
                className="flex-1 bg-surface-high hover:bg-surface-highest border border-outline/10 text-primaryText py-2 rounded-lg text-sm font-medium transition-colors disabled:opacity-50"
                whileTap={{ scale: 0.96 }}
              >
                {p.testing ? 'Testing...' : 'Test Connection'}
              </motion.button>
              <motion.button
                onClick={() => saveProvider(p)}
                className="flex-1 bg-primary hover:bg-primary/90 text-white py-2 rounded-lg text-sm font-medium transition-colors flex items-center justify-center gap-2"
                whileTap={{ scale: 0.96 }}
                whileHover={{ scale: 1.02 }}
              >
                <Save className="w-4 h-4" /> Save
              </motion.button>
            </div>
          </motion.div>
        ))}
      </div>
    </motion.div>
  );
};

export default Providers;

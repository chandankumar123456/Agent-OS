import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { apiClient } from '../api/client';
import { Skeleton } from '../components/ui/Skeleton';
import { Check, X, Zap, Save, Key, Link2 } from 'lucide-react';
import { buttonTap } from '../lib/animations';

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

 if (loading) return <div className="text-center py-8"><Skeleton className="h-4 w-32 mx-auto" /></div>;

 return (
 <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex flex-col gap-10 max-w-6xl mx-auto">
 <div>
 <h1 className="text-4xl font-pixel uppercase tracking-tight mb-2">Neural Providers</h1>
 <p className="text-xl font-retro uppercase text-secondaryText opacity-60">Configuration for large language model compute gateways.</p>
 </div>

 {error && (
 <div className="p-4 border-4 border-[#FF4B4B]/20 bg-[#FF4B4B]/10 font-retro text-lg text-[#FF4B4B] uppercase">
 !! ERROR_DETECTED: {error}
 </div>
 )}

 <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
 {providers.map((p) => (
 <motion.div key={p.name} className="pixel-card p-8 flex flex-col gap-6 bg-white">
 <div className="flex items-center justify-between">
 <div className="flex items-center gap-3">
 <div className="w-10 h-10 border-4 border-outline bg-surface-high flex items-center justify-center shadow-pixel">
 <Zap className="w-5 h-5 text-primary" />
 </div>
 <h2 className="text-xs font-pixel uppercase tracking-tight">{p.label}</h2>
 </div>
 <button
 onClick={() => updateProvider(p.name, { enabled: !p.enabled })}
 className={`w-14 h-8 border-4 border-outline p-1 ${p.enabled ? 'bg-secondary' : 'bg-surface-high'}`}
 >
 <div className={`w-5 h-full border-4 border-outline bg-white ${p.enabled ? 'translate-x-6' : 'translate-x-0'}`} />
 </button>
 </div>

 <div className="flex flex-col gap-5">
 {p.name !== 'ollama' && (
 <div>
 <label className="block text-[10px] font-pixel uppercase text-secondaryText mb-2">Credential_Token</label>
 <div className="relative">
 <Key className="absolute left-3 top-3 w-4 h-4 text-secondaryText" />
 <input
 type="password"
 className="w-full pixel-input py-2 pl-8 text-lg font-retro uppercase"
 placeholder="SK-..."
 value={p.apiKey}
 onChange={(e) => updateProvider(p.name, { apiKey: e.target.value })}
 />
 </div>
 </div>
 )}

 <div>
 <label className="block text-[10px] font-pixel uppercase text-secondaryText mb-2">Endpoint_Address</label>
 <div className="relative">
 <Link2 className="absolute left-3 top-3 w-4 h-4 text-secondaryText" />
 <input
 type="text"
 className="w-full pixel-input py-2 pl-8 text-lg font-retro uppercase"
 placeholder="HTTPS://API..."
 value={p.baseUrl}
 onChange={(e) => updateProvider(p.name, { baseUrl: e.target.value })}
 />
 </div>
 </div>

 <div>
 <label className="block text-[10px] font-pixel uppercase text-secondaryText mb-2">Core_Model_UID</label>
 <input
 type="text"
 className="w-full pixel-input py-2 text-lg font-retro uppercase"
 value={p.defaultModel}
 onChange={(e) => updateProvider(p.name, { defaultModel: e.target.value })}
 />
 </div>
 </div>

 {p.testResult && (
 <motion.div
 initial={{ opacity: 0, scale: 0.95 }}
 animate={{ opacity: 1, scale: 1 }}
 className={`p-4 border-4 font-retro text-lg uppercase flex items-start gap-3 ${
 p.testResult.success
 ? 'bg-secondary/10 border-secondary text-secondary'
 : 'bg-[#FF4B4B]/10 border-[#FF4B4B] text-[#FF4B4B]'
 }`}
 >
 {p.testResult.success ? <Check className="w-5 h-5 mt-1 shrink-0" /> : <X className="w-5 h-5 mt-1 shrink-0" />}
 {p.testResult.message}
 </motion.div>
 )}

 <div className="flex gap-4 mt-4">
 <motion.button
 onClick={() => testProvider(p)}
 disabled={p.testing}
 className="btn-secondary flex-1 py-4 text-[10px] font-pixel uppercase"
 {...buttonTap}
 >
 {p.testing ? '[ TESTING... ]' : '[ RUN_DIAGNOSTIC ]'}
 </motion.button>
 <motion.button
 onClick={() => saveProvider(p)}
 className="btn-primary flex-1 py-4 text-[10px] font-pixel uppercase flex items-center justify-center gap-2"
 {...buttonTap}
 >
 <Save className="w-5 h-5" /> [ PERSIST ]
 </motion.button>
 </div>
 </motion.div>
 ))}
 </div>
 </motion.div>
 );
};

export default Providers;

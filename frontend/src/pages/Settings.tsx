import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { RotateCcw, Users, Key, Settings as SettingsIcon, Cpu } from 'lucide-react';
import { useLocation, useNavigate } from 'react-router-dom';
import { apiClient } from '../api/client';
import { buttonTap } from '../lib/animations';
import { Skeleton } from '../components/ui/Skeleton';
import Providers from './Providers';

const Settings = () => {
 const location = useLocation();
 const navigate = useNavigate();
 const isProviders = location.pathname === '/settings/providers';
 const isTeam = location.pathname === '/settings/team';
 const isGeneral = !isProviders && !isTeam;
 const [config, setConfig] = useState<Record<string, any>>({});
 const [loading, setLoading] = useState(true);
 const [saving, setSaving] = useState(false);
 const [model, setModel] = useState('gpt-4o');
 const [actionError, setActionError] = useState('');
 const [theme, setTheme] = useState<'dark' | 'light'>('dark');
 const [language, setLanguage] = useState('en');

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

 const tabs = [
 { id: 'general', label: 'General', path: '/settings', icon: SettingsIcon },
 { id: 'providers', label: 'LLM Providers', path: '/settings/providers', icon: Cpu },
 { id: 'api-keys', label: 'API Keys', path: '/settings/api-keys', icon: Key },
 { id: 'team', label: 'Team', path: '/settings/team', icon: Users },
 ];

 return (
 <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex flex-col gap-10 max-w-6xl mx-auto">
 <div className="flex justify-between items-end">
 <div>
 <h1 className="text-4xl font-pixel uppercase tracking-tight mb-2">System Control</h1>
 <p className="text-xl font-retro uppercase text-secondaryText opacity-60">Master configuration registry for Agent_OS core.</p>
 </div>
 {isGeneral && (
 <motion.button onClick={reset} className="btn-secondary flex items-center gap-3 py-4 px-6 text-[10px] font-pixel uppercase" disabled={saving} {...buttonTap}>
 <RotateCcw className="w-5 h-5" /> [ SYSTEM_RESET ]
 </motion.button>
 )}
 </div>

 {actionError && (
 <div className="p-4 border-4 border-[#FF4B4B]/20 bg-[#FF4B4B]/10 font-retro text-lg text-[#FF4B4B] uppercase">
 !! KERNEL_ERROR: {actionError}
 </div>
 )}

 <div className="flex gap-8">
 <aside className="w-64 flex flex-col gap-3 shrink-0">
 {tabs.map((tab) => {
 const isActive = location.pathname === tab.path;
 return (
 <button
 key={tab.id}
 onClick={() => navigate(tab.path)}
 className={`relative flex items-center gap-4 px-6 py-4 border-4 text-left uppercase ${
 isActive
 ? 'bg-primary border-outline text-white shadow-pixel'
 : 'bg-white border-transparent text-secondaryText hover:border-outline/30 hover:bg-surface-high'
 }`}
 >
 <tab.icon className={`w-5 h-5 ${isActive ? 'text-white' : 'text-primary'}`} />
 <span className="text-[10px] font-pixel tracking-tighter">{tab.label}</span>
 {isActive && (
 <div className="absolute -right-3 top-1/2 -translate-y-1/2 w-3 h-6 bg-primary border-4 border-outline border-l-0" />
 )}
 </button>
 );
 })}
 </aside>

 <div className="flex-1 min-w-0">
 {loading && isGeneral ? (
 <div className="text-center py-8"><Skeleton className="h-4 w-32 mx-auto" /></div>
 ) : isProviders ? (
 <Providers />
 ) : isTeam ? (
 <div className="pixel-panel p-8 flex flex-col gap-8 bg-white">
 <div>
 <h2 className="text-xs font-pixel uppercase tracking-tight mb-6 flex items-center gap-3">
 <div className="w-2 h-2 bg-primary" /> Workspace_Registry
 </h2>
 <div className="flex flex-col gap-5">
 <div className="flex items-center justify-between p-6 border-4 border-outline bg-surface-high shadow-pixel">
 <div className="flex items-center gap-4">
 <div className="w-12 h-12 border-4 border-outline bg-primary flex items-center justify-center text-white text-xl font-retro font-bold">A</div>
 <div>
 <p className="text-lg font-retro uppercase text-primaryText">ADMIN@AGENTOS.LOCAL</p>
 <p className="text-[10px] font-pixel uppercase text-secondaryText">ROOT_ACCESS_GRANTED</p>
 </div>
 </div>
 <span className="text-[10px] font-pixel px-4 py-1 border-4 border-outline bg-primary/10 text-primary uppercase">ADMIN</span>
 </div>
 <motion.button className="btn-primary w-fit flex items-center gap-3 py-4 px-8 text-[10px] font-pixel uppercase" {...buttonTap}>
 <Users className="w-5 h-5" /> [ INVITE_MEMBER ]
 </motion.button>
 <p className="text-[10px] font-pixel uppercase text-secondaryText opacity-50 mt-4">
 NOTE: TEAM MANAGEMENT HANDOFF PROTOCOLS ARE CURRENTLY IN DEVELOPMENT.
 </p>
 </div>
 </div>
 </div>
 ) : (
 <div className="pixel-panel p-8 flex flex-col gap-10 bg-white">
 <div>
 <h2 className="text-xs font-pixel uppercase tracking-tight mb-6 flex items-center gap-3">
 <div className="w-2 h-2 bg-primary" /> Visual_Synthesis
 </h2>
 <div className="grid grid-cols-2 gap-8">
 <div>
 <label className="block text-[10px] font-pixel uppercase text-secondaryText mb-4">System_Theme</label>
 <select
 className="w-full pixel-input py-2 text-lg font-retro uppercase"
 value={theme}
 onChange={(e) => setTheme(e.target.value as 'dark' | 'light')}
 >
 <option value="dark">DARK_MODE</option>
 <option value="light">LIGHT_MODE</option>
 </select>
 </div>
 <div>
 <label className="block text-[10px] font-pixel uppercase text-secondaryText mb-4">Interface_Lang</label>
 <select
 className="w-full pixel-input py-2 text-lg font-retro uppercase"
 value={language}
 onChange={(e) => setLanguage(e.target.value)}
 >
 <option value="en">ENGLISH_US</option>
 <option value="es">ESPANOL</option>
 <option value="fr">FRANCAIS</option>
 <option value="de">DEUTSCH</option>
 </select>
 </div>
 </div>
 </div>

 <div>
 <h2 className="text-xs font-pixel uppercase tracking-tight mb-6 flex items-center gap-3">
 <div className="w-2 h-2 bg-primary" /> Compute_Defaults
 </h2>
 <div className="grid grid-cols-2 gap-8">
 <div>
 <label className="block text-[10px] font-pixel uppercase text-secondaryText mb-4">Base_Model_UID</label>
 <select
 className="w-full pixel-input py-2 text-lg font-retro uppercase"
 value={model}
 onChange={(e) => setModel(e.target.value)}
 onBlur={(e) => saveModel(e.target.value)}
 disabled={saving}
 >
 <option value="gpt-4o">GPT-4O</option>
 <option value="claude-3-5-sonnet">CLAUDE-3.5</option>
 <option value="llama-3-70b">LLAMA-3-70B</option>
 </select>
 </div>
 <div>
 <label className="block text-[10px] font-pixel uppercase text-secondaryText mb-4">Recursion_Limit</label>
 <input type="number" className="w-full pixel-input py-2 text-lg font-retro uppercase" value={config.MAX_STEPS_DEFAULT || 10} readOnly />
 </div>
 </div>
 </div>

 <div>
 <h2 className="text-xs font-pixel uppercase tracking-tight mb-6 flex items-center gap-3">
 <div className="w-2 h-2 bg-primary" /> Safety_Protocols
 </h2>
 <div className="grid grid-cols-2 gap-8">
 <div>
 <label className="block text-[10px] font-pixel uppercase text-secondaryText mb-4">Retry_Threshold</label>
 <input type="number" className="w-full pixel-input py-2 text-lg font-retro uppercase" value={config.MAX_RETRIES || 3} readOnly />
 </div>
 <div>
 <label className="block text-[10px] font-pixel uppercase text-secondaryText mb-4">IO_Timeout_SEC</label>
 <input type="number" className="w-full pixel-input py-2 text-lg font-retro uppercase" value={config.TIMEOUT_DEFAULT || 300} readOnly />
 </div>
 </div>
 </div>

 <div>
 <h2 className="text-xs font-pixel uppercase tracking-tight mb-6 flex items-center gap-3">
 <div className="w-2 h-2 bg-primary" /> Hardware_Abstraction
 </h2>
 <div className="grid grid-cols-1 gap-8">
 <div>
 <label className="block text-[10px] font-pixel uppercase text-secondaryText mb-4">Distributed_Task_Queue</label>
 <input type="text" className="w-full pixel-input py-2 text-lg font-retro uppercase" value={String(config.USE_CELERY)} readOnly />
 </div>
 </div>
 </div>
 </div>
 )}
 </div>
 </div>
 </motion.div>
 );
};

export default Settings;

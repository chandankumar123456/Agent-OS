import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { RotateCcw, Users, Key, Settings as SettingsIcon, Cpu } from 'lucide-react';
import { useLocation, useNavigate } from 'react-router-dom';
import { apiClient } from '../api/client';
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
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex flex-col gap-6 max-w-5xl mx-auto">
      <div className="flex justify-between items-end mb-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight mb-1 cursor-default">System Configuration</h1>
          <p className="text-secondaryText text-sm">Persistent runtime configuration.</p>
        </div>
        {isGeneral && (
          <motion.button onClick={reset} className="btn-secondary flex items-center gap-2" disabled={saving} whileTap={{ scale: 0.96 }}>
            <RotateCcw className="w-4 h-4" /> Reset
          </motion.button>
        )}
      </div>

      {actionError && (
        <div className="p-4 rounded-lg border border-[#FF4B4B]/20 bg-[#FF4B4B]/10 text-sm text-[#FF4B4B]">
          {actionError}
        </div>
      )}

      <div className="flex gap-6">
        <aside className="w-56 flex flex-col gap-1 shrink-0">
          {tabs.map((tab) => {
            const isActive = location.pathname === tab.path;
            return (
              <motion.button
                key={tab.id}
                onClick={() => navigate(tab.path)}
                whileTap={{ scale: 0.98 }}
                className={`relative flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium text-left transition-colors ${
                  isActive
                    ? 'text-primaryText'
                    : 'text-secondaryText hover:bg-surface-high hover:text-primaryText'
                }`}
              >
                {isActive && (
                  <motion.div layoutId="settingsTab" className="absolute inset-0 bg-surface-high rounded-lg -z-10" transition={{ type: 'spring', stiffness: 400, damping: 30 }} />
                )}
                <tab.icon className="w-4 h-4" />
                {tab.label}
              </motion.button>
            );
          })}
        </aside>

        <div className="flex-1 min-w-0">
          {loading && isGeneral ? (
            <div className="text-center py-12"><Skeleton className="h-4 w-32 mx-auto" /></div>
          ) : isProviders ? (
            <Providers />
          ) : isTeam ? (
            <div className="obsidian-panel border border-outline/10 p-8 flex flex-col gap-8">
              <div>
                <h2 className="text-lg font-semibold mb-4 pb-2 border-b border-outline/10">Workspace Members</h2>
                <div className="flex flex-col gap-4">
                  <div className="flex items-center justify-between p-4 bg-surface-highest rounded-lg border border-outline/10">
                    <div className="flex items-center gap-3">
                      <div className="w-8 h-8 rounded-full bg-primary/20 flex items-center justify-center text-primary text-sm font-bold">A</div>
                      <div>
                        <p className="text-sm font-medium text-primaryText">admin@agentos.local</p>
                        <p className="text-xs text-secondaryText">Owner</p>
                      </div>
                    </div>
                    <span className="text-xs px-2 py-1 rounded bg-primary/10 text-primary font-medium">Admin</span>
                  </div>
                  <motion.button className="btn-primary w-fit flex items-center gap-2" whileTap={{ scale: 0.96 }}>
                    <Users className="w-4 h-4" /> Invite Member
                  </motion.button>
                  <p className="text-xs text-secondaryText">Team management with workspace roles coming soon.</p>
                </div>
              </div>
            </div>
          ) : (
            <div className="obsidian-panel border border-outline/10 p-8 flex flex-col gap-8">
              <div>
                <h2 className="text-lg font-semibold mb-4 pb-2 border-b border-outline/10">Appearance</h2>
                <div className="grid grid-cols-2 gap-6">
                  <div>
                    <label className="block text-xs font-semibold tracking-widest uppercase text-secondaryText mb-2">Theme</label>
                    <select
                      className="w-full obsidian-input transition-transform duration-200 focus:scale-[1.01]"
                      value={theme}
                      onChange={(e) => setTheme(e.target.value as 'dark' | 'light')}
                    >
                      <option value="dark">Dark</option>
                      <option value="light">Light</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-xs font-semibold tracking-widest uppercase text-secondaryText mb-2">Language</label>
                    <select
                      className="w-full obsidian-input transition-transform duration-200 focus:scale-[1.01]"
                      value={language}
                      onChange={(e) => setLanguage(e.target.value)}
                    >
                      <option value="en">English</option>
                      <option value="es">Spanish</option>
                      <option value="fr">French</option>
                      <option value="de">German</option>
                    </select>
                  </div>
                </div>
              </div>

              <div>
                <h2 className="text-lg font-semibold mb-4 pb-2 border-b border-outline/10">Base LLM Configurations</h2>
                <div className="grid grid-cols-2 gap-6">
                  <div>
                    <label className="block text-xs font-semibold tracking-widest uppercase text-secondaryText mb-2">Default Model</label>
                    <select
                      className="w-full obsidian-input transition-transform duration-200 focus:scale-[1.01]"
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
                    <input type="number" className="w-full obsidian-input transition-transform duration-200 focus:scale-[1.01]" value={config.MAX_STEPS_DEFAULT || 10} readOnly />
                  </div>
                </div>
              </div>

              <div>
                <h2 className="text-lg font-semibold mb-4 pb-2 border-b border-outline/10">Orchestrator Limits</h2>
                <div className="grid grid-cols-2 gap-6">
                  <div>
                    <label className="block text-xs font-semibold tracking-widest uppercase text-secondaryText mb-2">Max Retry Count</label>
                    <input type="number" className="w-full obsidian-input transition-transform duration-200 focus:scale-[1.01]" value={config.MAX_RETRIES || 3} readOnly />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold tracking-widest uppercase text-secondaryText mb-2">Global Timeout (Seconds)</label>
                    <input type="number" className="w-full obsidian-input transition-transform duration-200 focus:scale-[1.01]" value={config.TIMEOUT_DEFAULT || 300} readOnly />
                  </div>
                </div>
              </div>

              <div>
                <h2 className="text-lg font-semibold mb-4 pb-2 border-b border-outline/10">Execution Mode</h2>
                <div className="grid grid-cols-1 gap-6">
                  <div>
                    <label className="block text-xs font-semibold tracking-widest uppercase text-secondaryText mb-2">Use Celery</label>
                    <input type="text" className="w-full obsidian-input transition-transform duration-200 focus:scale-[1.01]" value={String(config.USE_CELERY)} readOnly />
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

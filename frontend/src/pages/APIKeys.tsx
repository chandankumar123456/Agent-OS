import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { Key, Copy, Trash2, Plus, X, Check, Clock, Calendar } from 'lucide-react';
import { apiClient } from '../api/client';
import { Skeleton } from '../components/ui/Skeleton';
import { useToast } from '../components/ToastProvider';

interface APIKeyItem {
  id: string;
  name: string;
  permissions: string[];
  last_used_at: string | null;
  created_at: string;
}

const PERMISSION_OPTIONS = [
  { value: 'create_task', label: 'Create Tasks' },
  { value: 'create_agent', label: 'Create Agents' },
  { value: 'create_workflow', label: 'Create Workflows' },
  { value: 'delete_any', label: 'Delete Any' },
  { value: 'manage_users', label: 'Manage Users' },
  { value: 'view_analytics', label: 'View Analytics' },
];

const APIKeys = () => {
  const [keys, setKeys] = useState<APIKeyItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [newKeyName, setNewKeyName] = useState('');
  const [newKeyPermissions, setNewKeyPermissions] = useState<string[]>([]);
  const [createdKey, setCreatedKey] = useState<string | null>(null);
  const [revokingId, setRevokingId] = useState<string | null>(null);
  const { showToast } = useToast();

  const loadKeys = async () => {
    setLoading(true);
    try {
      const data = await apiClient.listAPIKeys();
      setKeys(data);
    } catch (error) {
      showToast(error instanceof Error ? error.message : 'Failed to load API keys', 'error');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadKeys();
  }, []);

  const handleCreate = async () => {
    if (!newKeyName.trim()) return;
    try {
      const result = await apiClient.createAPIKey({ name: newKeyName.trim(), permissions: newKeyPermissions });
      setCreatedKey(result.key);
      setNewKeyName('');
      setNewKeyPermissions([]);
      await loadKeys();
      showToast('API key created successfully', 'success');
    } catch (error) {
      showToast(error instanceof Error ? error.message : 'Failed to create API key', 'error');
    }
  };

  const handleRevoke = async (id: string) => {
    setRevokingId(id);
    try {
      await apiClient.revokeAPIKey(id);
      await loadKeys();
      showToast('API key revoked', 'success');
    } catch (error) {
      showToast(error instanceof Error ? error.message : 'Failed to revoke API key', 'error');
    } finally {
      setRevokingId(null);
    }
  };

  const copyToClipboard = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      showToast('Copied to clipboard', 'success');
    } catch {
      showToast('Failed to copy', 'error');
    }
  };

  const togglePermission = (value: string) => {
    setNewKeyPermissions((prev) =>
      prev.includes(value) ? prev.filter((p) => p !== value) : [...prev, value]
    );
  };

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex flex-col gap-6 max-w-5xl mx-auto">
      <div className="flex justify-between items-end">
        <div>
          <h1 className="text-3xl font-bold tracking-tight mb-1 cursor-default">API Keys</h1>
          <p className="text-secondaryText text-sm">Manage API keys for programmatic access.</p>
        </div>
        <motion.button onClick={() => { setShowCreate(true); setCreatedKey(null); }} className="btn-primary flex items-center gap-2" whileTap={{ scale: 0.96 }} whileHover={{ scale: 1.02 }}>
          <Plus className="w-4 h-4" /> Create Key
        </motion.button>
      </div>

      {showCreate && (
        <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} className="obsidian-panel border border-outline/10 p-6 flex flex-col gap-4">
          <div className="flex justify-between items-center">
            <h2 className="text-lg font-semibold">Create New API Key</h2>
            <motion.button onClick={() => { setShowCreate(false); setCreatedKey(null); }} className="text-secondaryText hover:text-primaryText" whileTap={{ scale: 0.85 }} whileHover={{ scale: 1.1, rotate: 90 }} transition={{ duration: 0.2 }}>
              <X className="w-5 h-5" />
            </motion.button>
          </div>

          {!createdKey ? (
            <>
              <div>
                <label className="block text-xs font-semibold tracking-widest uppercase text-secondaryText mb-2">Key Name</label>
                <input
                  className="w-full obsidian-input"
                  placeholder="e.g., Production CI/CD"
                  value={newKeyName}
                  onChange={(e) => setNewKeyName(e.target.value)}
                />
              </div>

              <div>
                <label className="block text-xs font-semibold tracking-widest uppercase text-secondaryText mb-2">Permissions</label>
                <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                  {PERMISSION_OPTIONS.map((opt) => (
                    <label key={opt.value} className="flex items-center gap-2 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={newKeyPermissions.includes(opt.value)}
                        onChange={() => togglePermission(opt.value)}
                        className="accent-primary w-4 h-4"
                      />
                      <span className="text-sm text-primaryText">{opt.label}</span>
                    </label>
                  ))}
                </div>
              </div>

              <div className="flex justify-end">
                <motion.button onClick={handleCreate} disabled={!newKeyName.trim()} className="btn-primary flex items-center gap-2 disabled:opacity-50" whileTap={{ scale: 0.96 }}>
                  <Key className="w-4 h-4" /> Generate Key
                </motion.button>
              </div>
            </>
          ) : (
            <div className="flex flex-col gap-3">
              <div className="p-4 bg-surface-highest border border-primary/30 rounded-lg">
                <div className="flex items-center justify-between gap-3">
                  <code className="text-sm text-primary break-all">{createdKey}</code>
                  <motion.button onClick={() => copyToClipboard(createdKey)} className="shrink-0 text-primary hover:text-primary/80" whileTap={{ scale: 0.85 }} whileHover={{ scale: 1.1 }}>
                    <Copy className="w-4 h-4" />
                  </motion.button>
                </div>
              </div>
              <p className="text-xs text-secondaryText">
                This key will only be shown once. Copy it now and store it securely.
              </p>
              <div className="flex justify-end">
                <motion.button onClick={() => { setShowCreate(false); setCreatedKey(null); }} className="btn-secondary" whileTap={{ scale: 0.96 }}>
                  Done
                </motion.button>
              </div>
            </div>
          )}
        </motion.div>
      )}

      <div className="obsidian-panel border border-outline/10 overflow-hidden">
        <table className="w-full text-left">
          <thead className="bg-surface-highest text-xs uppercase tracking-widest text-secondaryText">
            <tr>
              <th className="px-6 py-3">Name</th>
              <th className="px-6 py-3">Permissions</th>
              <th className="px-6 py-3">Last Used</th>
              <th className="px-6 py-3">Created</th>
              <th className="px-6 py-3 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-outline/10">
            {loading ? (
              <tr>
                <td colSpan={5} className="px-6 py-8 text-center"><Skeleton className="h-4 w-32 mx-auto" /></td>
              </tr>
            ) : keys.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-6 py-8 text-center text-secondaryText text-sm">
                  No API keys yet. Create one to get started.
                </td>
              </tr>
            ) : (
              keys.map((key) => (
                <tr key={key.id} className="hover:bg-surface-high/50 transition-colors duration-150">
                  <td className="px-6 py-4">
                    <div className="flex items-center gap-2">
                      <Key className="w-4 h-4 text-primary" />
                      <span className="text-sm font-medium text-primaryText">{key.name}</span>
                    </div>
                  </td>
                  <td className="px-6 py-4">
                    <div className="flex flex-wrap gap-1">
                      {key.permissions.length === 0 ? (
                        <span className="text-xs text-secondaryText">No permissions</span>
                      ) : (
                        key.permissions.map((p) => (
                          <span key={p} className="text-[10px] px-2 py-0.5 rounded bg-surface-highest border border-outline/10 text-secondaryText">
                            {p}
                          </span>
                        ))
                      )}
                    </div>
                  </td>
                  <td className="px-6 py-4">
                    <div className="flex items-center gap-1 text-xs text-secondaryText">
                      <Clock className="w-3 h-3" />
                      {key.last_used_at ? new Date(key.last_used_at).toLocaleDateString() : 'Never'}
                    </div>
                  </td>
                  <td className="px-6 py-4">
                    <div className="flex items-center gap-1 text-xs text-secondaryText">
                      <Calendar className="w-3 h-3" />
                      {key.created_at ? new Date(key.created_at).toLocaleDateString() : '-'}
                    </div>
                  </td>
                  <td className="px-6 py-4 text-right">
                    <motion.button
                      onClick={() => handleRevoke(key.id)}
                      disabled={revokingId === key.id}
                      className="text-secondaryText hover:text-[#FF4B4B] transition-colors disabled:opacity-50"
                      title="Revoke key"
                      whileTap={{ scale: 0.85 }}
                      whileHover={{ scale: 1.1, color: '#FF4B4B' }}
                    >
                      {revokingId === key.id ? <Check className="w-4 h-4" /> : <Trash2 className="w-4 h-4" />}
                    </motion.button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </motion.div>
  );
};

export default APIKeys;

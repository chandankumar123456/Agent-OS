import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { Key, Copy, Trash2, Plus, X, Check, Clock, Calendar } from 'lucide-react';
import { apiClient } from '../api/client';
import { buttonTap } from '../lib/animations';
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
 <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex flex-col gap-10 max-w-6xl mx-auto">
 <div className="flex justify-between items-end">
 <div>
 <h1 className="text-4xl font-pixel uppercase tracking-tight mb-2">Access Credentials</h1>
 <p className="text-xl font-retro uppercase text-secondaryText opacity-60">Manage neural network interface keys.</p>
 </div>
 <motion.button onClick={() => { setShowCreate(true); setCreatedKey(null); }} className="btn-primary flex items-center gap-3 py-4 px-6 text-[10px] font-pixel uppercase" {...buttonTap}>
 <Plus className="w-5 h-5" /> [ GENERATE_SECRET ]
 </motion.button>
 </div>

 {showCreate && (
 <motion.div initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} className="pixel-panel p-8 flex flex-col gap-8 bg-white">
 <div className="flex justify-between items-center">
 <h2 className="text-xs font-pixel uppercase tracking-tight">Provision_New_Credential</h2>
 <button onClick={() => { setShowCreate(false); setCreatedKey(null); }} className="text-secondaryText hover:text-primary border-4 border-outline p-1">
 <X className="w-5 h-5" />
 </button>
 </div>

 {!createdKey ? (
 <>
 <div className="space-y-6">
 <div>
 <label className="block text-[10px] font-pixel uppercase text-secondaryText mb-4">Key_Identifier</label>
 <input
 className="w-full pixel-input text-lg font-retro uppercase"
 placeholder="E.G. OS_PRODUCTION_RELAY"
 value={newKeyName}
 onChange={(e) => setNewKeyName(e.target.value)}
 />
 </div>

 <div>
 <label className="block text-[10px] font-pixel uppercase text-secondaryText mb-4">Security_Scope</label>
 <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
 {PERMISSION_OPTIONS.map((opt) => (
 <label key={opt.value} className="flex items-center gap-3 cursor-pointer group">
 <input
 type="checkbox"
 checked={newKeyPermissions.includes(opt.value)}
 onChange={() => togglePermission(opt.value)}
 className="w-5 h-5 border-4 border-outline checked:bg-primary appearance-none cursor-pointer"
 />
 <span className="text-[10px] font-pixel uppercase text-primaryText group-hover:text-primary ">{opt.label}</span>
 </label>
 ))}
 </div>
 </div>

 <div className="flex justify-end pt-4">
 <motion.button onClick={handleCreate} disabled={!newKeyName.trim()} className="btn-primary flex items-center gap-3 py-4 px-8 text-[10px] font-pixel uppercase disabled:opacity-50" {...buttonTap}>
 <Key className="w-5 h-5" /> [ GENERATE_LINK_KEY ]
 </motion.button>
 </div>
 </div>
 </>
 ) : (
 <div className="flex flex-col gap-6">
 <div className="p-6 bg-primary/5 border-4 border-primary shadow-pixel">
 <div className="flex items-center justify-between gap-4">
 <code className="text-xl text-primary font-retro uppercase break-all">{createdKey}</code>
 <motion.button onClick={() => copyToClipboard(createdKey)} className="shrink-0 text-primary hover:text-primary/80 border-4 border-primary p-2" {...buttonTap}>
 <Copy className="w-5 h-5" />
 </motion.button>
 </div>
 </div>
 <p className="text-[10px] font-pixel uppercase text-[#FF4B4B]">
 !! WARNING: THIS CREDENTIAL WILL ONLY BE DISPLAYED ONCE. PERSIST DATA IMMEDIATELY.
 </p>
 <div className="flex justify-end">
 <motion.button onClick={() => { setShowCreate(false); setCreatedKey(null); }} className="btn-secondary py-2 px-6 text-[10px] font-pixel uppercase" {...buttonTap}>
 [ DISMISS ]
 </motion.button>
 </div>
 </div>
 )}
 </motion.div>
 )}

 <div className="pixel-panel overflow-hidden">
 <table className="w-full text-left">
 <thead className="bg-surface-high border-b-4 border-outline text-[10px] font-pixel uppercase tracking-tighter text-secondaryText">
 <tr>
 <th className="px-6 py-4 font-normal">Credential_Alias</th>
 <th className="px-6 py-4 font-normal">Auth_Scope</th>
 <th className="px-6 py-4 font-normal">Last_Handshake</th>
 <th className="px-6 py-4 font-normal">Created</th>
 <th className="px-6 py-4 font-normal text-right">Link</th>
 </tr>
 </thead>
 <tbody className="text-lg font-retro uppercase text-primaryText">
 {loading ? (
 <tr>
 <td colSpan={5} className="px-6 py-8 text-center"><Skeleton className="h-4 w-32 mx-auto" /></td>
 </tr>
 ) : keys.length === 0 ? (
 <tr>
 <td colSpan={5} className="px-6 py-8 text-center text-secondaryText font-retro opacity-50">
 NULL_REGISTRY: NO CREDENTIALS ASSIGNED.
 </td>
 </tr>
 ) : (
 keys.map((key) => (
 <tr key={key.id} className="border-b-4 border-outline/5 hover:bg-surface-high ">
 <td className="px-6 py-6">
 <div className="flex items-center gap-3">
 <Key className="w-5 h-5 text-primary" />
 <span className="font-retro">{key.name}</span>
 </div>
 </td>
 <td className="px-6 py-6">
 <div className="flex flex-wrap gap-2">
 {key.permissions.length === 0 ? (
 <span className="text-[8px] font-pixel uppercase text-secondaryText opacity-40">[ NIL ]</span>
 ) : (
 key.permissions.map((p) => (
 <span key={p} className="text-[8px] font-pixel px-2 py-1 border-4 border-outline bg-secondary/10 text-secondary uppercase">
 {p}
 </span>
 ))
 )}
 </div>
 </td>
 <td className="px-6 py-6">
 <div className="flex items-center gap-2 text-sm text-secondaryText">
 <Clock className="w-4 h-4" />
 {key.last_used_at ? new Date(key.last_used_at).toLocaleDateString() : 'NEVER'}
 </div>
 </td>
 <td className="px-6 py-6">
 <div className="flex items-center gap-2 text-sm text-secondaryText">
 <Calendar className="w-4 h-4" />
 {key.created_at ? new Date(key.created_at).toLocaleDateString() : '-'}
 </div>
 </td>
 <td className="px-6 py-6 text-right">
 <motion.button
 onClick={() => handleRevoke(key.id)}
 disabled={revokingId === key.id}
 className="text-secondaryText hover:text-[#FF4B4B] p-1 border-4 border-transparent hover:border-outline"
 title="Revoke key"
 {...buttonTap}
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

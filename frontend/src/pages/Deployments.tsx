import { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { apiClient } from '../api/client';
import { buttonTap, cardInteractions } from '../lib/animations';
import { Skeleton } from '../components/ui/Skeleton';
import { Rocket, Trash2, Copy, Check, ExternalLink, ToggleLeft, ToggleRight, Plus, Code, X, Shield, Globe } from 'lucide-react';

interface Deployment {
 id: string;
 workflow_id: string;
 name: string;
 description?: string;
 endpoint_url: string;
 auth_type: string;
 status: string;
 created_at: string;
}

interface WorkflowOption {
 id: string;
 name: string;
}

export default function Deployments() {
 const [deployments, setDeployments] = useState<Deployment[]>([]);
 const [workflows, setWorkflows] = useState<WorkflowOption[]>([]);
 const [loading, setLoading] = useState(true);
 const [modalOpen, setModalOpen] = useState(false);
 const [mcpModalOpen, setMcpModalOpen] = useState(false);
 const [mcpConfig, setMcpConfig] = useState<any>(null);
 const [copiedKey, setCopiedKey] = useState<string | null>(null);

 const [form, setForm] = useState({
 workflow_id: '',
 name: '',
 description: '',
 auth_type: 'none',
 });

 const fetchDeployments = useCallback(async () => {
 try {
 const data = await apiClient.listDeployments();
 setDeployments(data);
 } catch (err) {
 console.error('Failed to load deployments', err);
 }
 }, []);

 const fetchWorkflows = useCallback(async () => {
 try {
 const data = await apiClient.getWorkflowTemplatesV2();
 setWorkflows(data.map((w: any) => ({ id: w.id, name: w.name })));
 } catch (err) {
 console.error('Failed to load workflows', err);
 }
 }, []);

 useEffect(() => {
 Promise.all([fetchDeployments(), fetchWorkflows()]).finally(() => setLoading(false));
 }, [fetchDeployments, fetchWorkflows]);

 const handleCreate = async () => {
 if (!form.workflow_id || !form.name) return;
 try {
 await apiClient.createDeployment(form);
 setModalOpen(false);
 setForm({ workflow_id: '', name: '', description: '', auth_type: 'none' });
 await fetchDeployments();
 } catch (err) {
 alert(err instanceof Error ? err.message : 'Failed to create deployment');
 }
 };

 const handleDelete = async (id: string) => {
 if (!confirm('Delete this deployment?')) return;
 try {
 await apiClient.deleteDeployment(id);
 await fetchDeployments();
 } catch (err) {
 alert(err instanceof Error ? err.message : 'Failed to delete');
 }
 };

 const handleToggleStatus = async (id: string, current: string) => {
 const next = current === 'active' ? 'inactive' : 'active';
 try {
 await apiClient.updateDeploymentStatus(id, next);
 await fetchDeployments();
 } catch (err) {
 alert(err instanceof Error ? err.message : 'Failed to update status');
 }
 };

 const handleExportMCP = async (deployment: Deployment) => {
 try {
 const config = await apiClient.exportMCP({
 workflow_id: deployment.workflow_id,
 name: deployment.name,
 description: deployment.description,
 auth_type: deployment.auth_type,
 });
 setMcpConfig(config);
 setMcpModalOpen(true);
 } catch (err) {
 alert(err instanceof Error ? err.message : 'Failed to export MCP config');
 }
 };

 const copyToClipboard = (text: string, label: string) => {
 navigator.clipboard.writeText(text);
 setCopiedKey(label);
 setTimeout(() => setCopiedKey(null), 2000);
 };

 if (loading) {
 return (
 <div className="space-y-6">
 <div className="flex justify-between items-center">
 <div className="space-y-2">
 <Skeleton className="h-8 w-48" />
 <Skeleton className="h-4 w-64" />
 </div>
 <Skeleton className="h-10 w-36" />
 </div>
 <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
 <Skeleton className="h-48" />
 <Skeleton className="h-48" />
 </div>
 </div>
 );
 }

 return (
 <div className="flex flex-col gap-10">
 <div className="flex items-center justify-between">
 <div>
 <h1 className="text-4xl font-pixel uppercase tracking-tight mb-2">Edge Deployments</h1>
 <p className="text-xl font-retro uppercase text-secondaryText opacity-60">Provisioning and telemetry for production orchestration endpoints.</p>
 </div>
 <motion.button
 onClick={() => setModalOpen(true)}
 className="btn-primary flex items-center gap-3 py-4 px-6 text-[10px] font-pixel uppercase"
 {...buttonTap}
 >
 <Plus className="w-5 h-5" /> [ NEW_PROVISION ]
 </motion.button>
 </div>

 {deployments.length === 0 ? (
 <motion.div
 initial={{ opacity: 0, scale: 0.95 }}
 animate={{ opacity: 1, scale: 1 }}
 className="pixel-panel p-8 text-center bg-white"
 >
 <Rocket className="w-16 h-16 text-primary mx-auto mb-6" />
 <h3 className="text-lg font-pixel uppercase text-primaryText">System_Idle: No Active Probes</h3>
 <p className="text-lg font-retro uppercase text-secondaryText mt-4 opacity-60">Initialize an endpoint to commence data ingestion.</p>
 <motion.button
 onClick={() => setModalOpen(true)}
 className="btn-primary mt-8 py-4 px-8 text-[10px] font-pixel uppercase"
 {...buttonTap}
 >
 [ INITIALIZE_DEPLOYMENT ]
 </motion.button>
 </motion.div>
 ) : (
 <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
 {deployments.map((d, idx) => (
 <motion.div
 key={d.id}
 initial={{ opacity: 0, scale: 0.95 }}
 animate={{ opacity: 1, scale: 1 }}
 transition={{ delay: idx * 0.05 }}
 {...cardInteractions}
 className="pixel-card p-6 flex flex-col gap-5"
 >
 <div className="flex items-start justify-between">
 <div className="flex items-center gap-3">
 <div className="w-10 h-10 border-4 border-outline bg-surface-high flex items-center justify-center shadow-pixel">
 <Globe className="w-5 h-5 text-primary" />
 </div>
 <div>
 <h3 className="text-xs font-pixel uppercase leading-tight">{d.name}</h3>
 <div className="flex items-center gap-2 mt-2">
 <span className={`text-[8px] font-pixel px-2 py-1 border-4 border-outline uppercase tracking-tighter ${d.status === 'active' ? 'bg-secondary/20 text-secondary' : 'bg-accent-yellow/20 text-accent-yellow'}`}>
 {d.status === 'active' ? 'OK' : 'HALT'}
 </span>
 </div>
 </div>
 </div>
 <div className="flex items-center gap-2">
 <motion.button
 onClick={() => handleExportMCP(d)}
 className="p-2 border-4 border-outline hover:bg-primary/20 "
 title="Export as MCP"
 {...buttonTap}
 >
 <Code className="w-4 h-4 text-primary" />
 </motion.button>
 <motion.button
 onClick={() => handleToggleStatus(d.id, d.status)}
 className="p-2 border-4 border-outline hover:bg-primary/20 "
 title="Toggle status"
 {...buttonTap}
 >
 {d.status === 'active' ? <ToggleRight className="w-4 h-4 text-secondary" /> : <ToggleLeft className="w-4 h-4 text-accent-yellow" />}
 </motion.button>
 <motion.button
 onClick={() => handleDelete(d.id)}
 className="p-2 border-4 border-outline hover:bg-[#FF4B4B]/20 "
 title="Delete"
 {...buttonTap}
 >
 <Trash2 className="w-4 h-4 text-[#FF4B4B]" />
 </motion.button>
 </div>
 </div>

 <div className="flex flex-col gap-3">
 <div className="flex items-center gap-3 text-[10px] font-pixel uppercase text-secondaryText">
 <span>Link:</span>
 <div className="flex-1 bg-surface-high border-4 border-outline px-4 py-2 flex items-center justify-between shadow-pixel overflow-hidden">
 <code className="text-primaryText font-retro truncate">{d.endpoint_url}</code>
 <div className="flex items-center gap-2 ml-2">
 <button
 onClick={() => copyToClipboard(d.endpoint_url, `url-${d.id}`)}
 className="hover:text-primary "
 >
 {copiedKey === `url-${d.id}` ? <Check className="w-3 h-3 text-secondary" /> : <Copy className="w-3 h-3" />}
 </button>
 <a
 href={`${import.meta.env.VITE_API_URL?.replace('/api/v1', '') || 'http://localhost:8000'}${d.endpoint_url}`}
 target="_blank"
 rel="noopener noreferrer"
 className="hover:text-primary "
 >
 <ExternalLink className="w-3 h-3" />
 </a>
 </div>
 </div>
 </div>
 <div className="flex items-center gap-3 text-[10px] font-pixel uppercase text-secondaryText">
 <span>Auth:</span>
 <div className="flex items-center gap-2">
 {d.auth_type === 'api_key' ? 
 <span className="flex items-center gap-1 text-accent-yellow"><Shield className="w-3 h-3" /> [ KEYED ]</span> : 
 <span className="opacity-40">[ OPEN ]</span>
 }
 </div>
 </div>
 {d.description && <p className="text-lg font-retro uppercase text-secondaryText opacity-60 line-clamp-1">{d.description}</p>}
 </div>
 </motion.div>
 ))}
 </div>
 )}

 <AnimatePresence>
 {modalOpen && (
 <motion.div
 initial={{ opacity: 0 }}
 animate={{ opacity: 1 }}
 exit={{ opacity: 0 }}
 className="fixed inset-0 z-50 flex items-center justify-center bg-black/60"
 onClick={() => setModalOpen(false)}
 >
 <motion.div
 initial={{ opacity: 0, scale: 0.95 }}
 animate={{ opacity: 1, scale: 1 }}
 exit={{ opacity: 0, scale: 0.95 }}
 onClick={(e) => e.stopPropagation()}
 className="bg-white border-4 border-outline p-8 w-[540px] shadow-pixel space-y-8"
 >
 <div className="flex items-center justify-between">
 <h3 className="text-xl font-pixel uppercase tracking-tight">Provision_Probe</h3>
 <button
 onClick={() => setModalOpen(false)}
 className="text-secondaryText hover:text-primary border-4 border-outline p-1"
 >
 <X className="w-5 h-5" />
 </button>
 </div>
 <div className="space-y-6">
 <div>
 <label className="text-[10px] font-pixel uppercase text-secondaryText block mb-2">Workflow_Link</label>
 <select className="pixel-input text-lg font-retro uppercase w-full" value={form.workflow_id} onChange={(e) => setForm((p) => ({ ...p, workflow_id: e.target.value }))}>
 <option value="">[ SELECT_CORE_IMAGE ]</option>
 {workflows.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}
 </select>
 </div>
 <div>
 <label className="text-[10px] font-pixel uppercase text-secondaryText block mb-2">Probe_Identifier</label>
 <input className="pixel-input text-lg font-retro uppercase w-full" placeholder="OS_ALPHA_01" value={form.name} onChange={(e) => setForm((p) => ({ ...p, name: e.target.value }))} />
 </div>
 <div>
 <label className="text-[10px] font-pixel uppercase text-secondaryText block mb-2">Registry_Note</label>
 <input className="pixel-input text-lg font-retro uppercase w-full" placeholder="Secondary data relay" value={form.description} onChange={(e) => setForm((p) => ({ ...p, description: e.target.value }))} />
 </div>
 <div>
 <label className="text-[10px] font-pixel uppercase text-secondaryText block mb-2">Access_Protocol</label>
 <div className="grid grid-cols-2 gap-4">
 <button
 onClick={() => setForm((p) => ({ ...p, auth_type: 'none' }))}
 className={`py-4 border-4 font-pixel text-[10px] uppercase flex items-center justify-center gap-2 ${form.auth_type === 'none' ? 'border-primary bg-primary text-white shadow-pixel' : 'border-outline/10 text-secondaryText bg-white hover:border-outline'}`}
 >
 <Globe className="w-4 h-4" /> [ OPEN ]
 </button>
 <button
 onClick={() => setForm((p) => ({ ...p, auth_type: 'api_key' }))}
 className={`py-4 border-4 font-pixel text-[10px] uppercase flex items-center justify-center gap-2 ${form.auth_type === 'api_key' ? 'border-accent-yellow bg-accent-yellow text-primaryText shadow-pixel' : 'border-outline/10 text-secondaryText bg-white hover:border-outline'}`}
 >
 <Shield className="w-4 h-4" /> [ KEYED ]
 </button>
 </div>
 </div>
 <button
 onClick={handleCreate}
 className="btn-primary w-full py-4 text-[10px] font-pixel uppercase mt-4"
 >
 [ INITIALIZE_PROBE ]
 </button>
 </div>
 </motion.div>
 </motion.div>
 )}
 </AnimatePresence>

 {/* MCP Export Modal */}
 <AnimatePresence>
 {mcpModalOpen && mcpConfig && (
 <motion.div
 initial={{ opacity: 0 }}
 animate={{ opacity: 1 }}
 exit={{ opacity: 0 }}
 className="fixed inset-0 z-50 flex items-center justify-center bg-black/60"
 onClick={() => setMcpModalOpen(false)}
 >
 <motion.div
 initial={{ opacity: 0, scale: 0.95 }}
 animate={{ opacity: 1, scale: 1 }}
 exit={{ opacity: 0, scale: 0.95 }}
 onClick={(e) => e.stopPropagation()}
 className="bg-white border-4 border-outline p-8 w-[640px] max-h-[80vh] overflow-y-auto shadow-pixel space-y-6"
 >
 <div className="flex items-center justify-between">
 <h3 className="text-xl font-pixel uppercase tracking-tight flex items-center gap-3"><Code className="w-6 h-6 text-primary" /> MCP_CFG_INJECT</h3>
 <button
 onClick={() => setMcpModalOpen(false)}
 className="text-secondaryText hover:text-primary border-4 border-outline p-1"
 >
 <X className="w-5 h-5" />
 </button>
 </div>
 <p className="font-retro text-lg uppercase text-secondaryText">Inject this parameters into your local MCP controller instance.</p>
 <div className="relative">
 <pre className="bg-surface-high border-4 border-outline p-6 text-sm text-primaryText font-mono overflow-x-auto shadow-pixel">
 {JSON.stringify(mcpConfig, null, 2)}
 </pre>
 <motion.button
 onClick={() => copyToClipboard(JSON.stringify(mcpConfig, null, 2), 'mcp')}
 className="absolute top-4 right-4 p-2 border-4 border-outline bg-white hover:bg-primary/20 "
 {...buttonTap}
 >
 {copiedKey === 'mcp' ? <Check className="w-4 h-4 text-secondary" /> : <Copy className="w-4 h-4" />}
 </motion.button>
 </div>
 </motion.div>
 </motion.div>
 )}
 </AnimatePresence>
 </div>
 );
}

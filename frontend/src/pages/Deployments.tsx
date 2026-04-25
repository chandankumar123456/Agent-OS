import { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { apiClient } from '../api/client';
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
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-primaryText">Deployments</h1>
          <p className="text-sm text-secondaryText mt-1">Deploy workflows as REST API endpoints or MCP servers.</p>
        </div>
        <motion.button
          onClick={() => setModalOpen(true)}
          className="btn-primary flex items-center gap-2 text-sm"
          whileTap={{ scale: 0.96 }}
          whileHover={{ scale: 1.02 }}
        >
          <Plus className="w-4 h-4" /> New Deployment
        </motion.button>
      </div>

      {deployments.length === 0 ? (
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="bg-surface-low border border-outline/10 rounded-xl p-12 text-center"
        >
          <Rocket className="w-12 h-12 text-secondaryText mx-auto mb-4" />
          <h3 className="text-lg font-semibold text-primaryText">No deployments yet</h3>
          <p className="text-sm text-secondaryText mt-2">Deploy a workflow to expose it as a public API endpoint.</p>
          <motion.button
            onClick={() => setModalOpen(true)}
            className="btn-primary mt-4 text-sm"
            whileTap={{ scale: 0.96 }}
          >
            Create Deployment
          </motion.button>
        </motion.div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {deployments.map((d, idx) => (
            <motion.div
              key={d.id}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: idx * 0.05 }}
              whileHover={{ y: -3, boxShadow: '0 8px 30px rgba(0,229,255,0.06)' }}
              className="bg-surface-low border border-outline/10 rounded-xl p-5 hover:border-outline/20 transition-colors"
            >
              <div className="flex items-start justify-between mb-3">
                <div className="flex items-center gap-2">
                  <Globe className="w-5 h-5 text-primary" />
                  <h3 className="font-semibold text-primaryText">{d.name}</h3>
                  <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-bold ${d.status === 'active' ? 'bg-emerald-500/20 text-emerald-400' : 'bg-yellow-500/20 text-yellow-400'}`}>{d.status}</span>
                </div>
                <div className="flex items-center gap-1">
                  <motion.button
                    onClick={() => handleExportMCP(d)}
                    className="p-1.5 rounded-lg hover:bg-surface-high text-secondaryText hover:text-primary transition-colors"
                    title="Export as MCP"
                    whileTap={{ scale: 0.85 }}
                  >
                    <Code className="w-4 h-4" />
                  </motion.button>
                  <motion.button
                    onClick={() => handleToggleStatus(d.id, d.status)}
                    className="p-1.5 rounded-lg hover:bg-surface-high text-secondaryText hover:text-primary transition-colors"
                    title="Toggle status"
                    whileTap={{ scale: 0.85 }}
                  >
                    {d.status === 'active' ? <ToggleRight className="w-4 h-4 text-emerald-400" /> : <ToggleLeft className="w-4 h-4 text-yellow-400" />}
                  </motion.button>
                  <motion.button
                    onClick={() => handleDelete(d.id)}
                    className="p-1.5 rounded-lg hover:bg-red-500/10 text-secondaryText hover:text-red-400 transition-colors"
                    title="Delete"
                    whileTap={{ scale: 0.85 }}
                  >
                    <Trash2 className="w-4 h-4" />
                  </motion.button>
                </div>
              </div>

              <div className="space-y-2">
                <div className="flex items-center gap-2 text-sm">
                  <span className="text-secondaryText">Endpoint:</span>
                  <code className="bg-surface-high px-2 py-0.5 rounded text-xs text-primaryText font-mono">{d.endpoint_url}</code>
                  <motion.button
                    onClick={() => copyToClipboard(d.endpoint_url, `url-${d.id}`)}
                    className="text-secondaryText hover:text-primary"
                    whileTap={{ scale: 0.85 }}
                    whileHover={{ scale: 1.1 }}
                  >
                    {copiedKey === `url-${d.id}` ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
                  </motion.button>
                  <motion.a
                    href={`${import.meta.env.VITE_API_URL?.replace('/api/v1', '') || 'http://localhost:8000'}${d.endpoint_url}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-secondaryText hover:text-primary"
                    whileTap={{ scale: 0.9 }}
                  >
                    <ExternalLink className="w-3 h-3" />
                  </motion.a>
                </div>
                <div className="flex items-center gap-2 text-sm">
                  <span className="text-secondaryText">Auth:</span>
                  {d.auth_type === 'api_key' ? <span className="flex items-center gap-1 text-xs text-amber-400"><Shield className="w-3 h-3" /> API Key</span> : <span className="text-xs text-secondaryText">None</span>}
                </div>
                {d.description && <p className="text-xs text-secondaryText">{d.description}</p>}
              </div>
            </motion.div>
          ))}
        </div>
      )}

      {/* New Deployment Modal */}
      <AnimatePresence>
        {modalOpen && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
            onClick={() => setModalOpen(false)}
          >
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 20 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 20 }}
              transition={{ type: 'spring', stiffness: 300, damping: 25 }}
              onClick={(e) => e.stopPropagation()}
              className="bg-surface-low border border-outline/20 rounded-xl p-6 w-[480px] shadow-2xl"
            >
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-semibold text-primaryText">New Deployment</h3>
                <motion.button
                  onClick={() => setModalOpen(false)}
                  className="text-secondaryText hover:text-primaryText"
                  whileTap={{ scale: 0.85 }}
                  whileHover={{ scale: 1.1, rotate: 90 }}
                >
                  <X className="w-5 h-5" />
                </motion.button>
              </div>
              <div className="space-y-3">
                <div>
                  <label className="text-xs text-secondaryText block mb-1">Workflow</label>
                  <select className="obsidian-input text-sm w-full transition-transform duration-200 focus:scale-[1.01]" value={form.workflow_id} onChange={(e) => setForm((p) => ({ ...p, workflow_id: e.target.value }))}>
                    <option value="">Select a workflow...</option>
                    {workflows.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}
                  </select>
                </div>
                <div>
                  <label className="text-xs text-secondaryText block mb-1">Name</label>
                  <input className="obsidian-input text-sm w-full transition-transform duration-200 focus:scale-[1.01]" placeholder="My API" value={form.name} onChange={(e) => setForm((p) => ({ ...p, name: e.target.value }))} />
                </div>
                <div>
                  <label className="text-xs text-secondaryText block mb-1">Description</label>
                  <input className="obsidian-input text-sm w-full transition-transform duration-200 focus:scale-[1.01]" placeholder="Optional description" value={form.description} onChange={(e) => setForm((p) => ({ ...p, description: e.target.value }))} />
                </div>
                <div>
                  <label className="text-xs text-secondaryText block mb-1">Authentication</label>
                  <div className="flex gap-3">
                    <motion.button
                      onClick={() => setForm((p) => ({ ...p, auth_type: 'none' }))}
                      className={`flex-1 py-2 rounded-lg border text-sm flex items-center justify-center gap-2 ${form.auth_type === 'none' ? 'border-primary bg-primary/10 text-primary' : 'border-outline/10 text-secondaryText hover:bg-surface-high'}`}
                      whileTap={{ scale: 0.98 }}
                    >
                      <Globe className="w-4 h-4" /> None
                    </motion.button>
                    <motion.button
                      onClick={() => setForm((p) => ({ ...p, auth_type: 'api_key' }))}
                      className={`flex-1 py-2 rounded-lg border text-sm flex items-center justify-center gap-2 ${form.auth_type === 'api_key' ? 'border-primary bg-primary/10 text-primary' : 'border-outline/10 text-secondaryText hover:bg-surface-high'}`}
                      whileTap={{ scale: 0.98 }}
                    >
                      <Shield className="w-4 h-4" /> API Key
                    </motion.button>
                  </div>
                </div>
                <motion.button
                  onClick={handleCreate}
                  className="btn-primary text-sm w-full mt-2"
                  whileTap={{ scale: 0.96 }}
                  whileHover={{ scale: 1.02 }}
                >
                  Deploy
                </motion.button>
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
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
            onClick={() => setMcpModalOpen(false)}
          >
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 20 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 20 }}
              transition={{ type: 'spring', stiffness: 300, damping: 25 }}
              onClick={(e) => e.stopPropagation()}
              className="bg-surface-low border border-outline/20 rounded-xl p-6 w-[600px] max-h-[80vh] overflow-y-auto shadow-2xl"
            >
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-semibold text-primaryText flex items-center gap-2"><Code className="w-5 h-5 text-primary" /> MCP Server Config</h3>
                <motion.button
                  onClick={() => setMcpModalOpen(false)}
                  className="text-secondaryText hover:text-primaryText"
                  whileTap={{ scale: 0.85 }}
                  whileHover={{ scale: 1.1, rotate: 90 }}
                >
                  <X className="w-5 h-5" />
                </motion.button>
              </div>
              <p className="text-sm text-secondaryText mb-3">Add this configuration to your MCP client (e.g., Claude Desktop, Cursor):</p>
              <div className="relative">
                <pre className="bg-surface-high rounded-lg p-4 text-xs text-primaryText font-mono overflow-x-auto">
                  {JSON.stringify(mcpConfig, null, 2)}
                </pre>
                <motion.button
                  onClick={() => copyToClipboard(JSON.stringify(mcpConfig, null, 2), 'mcp')}
                  className="absolute top-2 right-2 p-1.5 rounded bg-surface-low hover:bg-surface-high text-secondaryText hover:text-primary transition-colors"
                  whileTap={{ scale: 0.85 }}
                >
                  {copiedKey === 'mcp' ? <Check className="w-4 h-4 text-emerald-400" /> : <Copy className="w-4 h-4" />}
                </motion.button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

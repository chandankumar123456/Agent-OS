import { useEffect, useMemo, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Search,
  Wrench,
  Globe,
  Server,
  Code2,
  Container,
  Zap,
  Download,
  X,
  Play,
  Loader2,
  ChevronRight,
  Package,
  User,
  FileCode,
} from 'lucide-react';
import { apiClient, type ToolV2Info, type ToolV2HealthMetrics } from '../api/client';
import EmptyState from '../components/EmptyState';
import { Skeleton } from '../components/ui/Skeleton';

type TabKey = 'all' | 'native' | 'mcp' | 'openapi' | 'python' | 'docker' | 'custom';

const TABS: { key: TabKey; label: string }[] = [
  { key: 'all', label: 'All' },
  { key: 'native', label: 'Native' },
  { key: 'mcp', label: 'MCP' },
  { key: 'openapi', label: 'APIs' },
  { key: 'custom', label: 'Custom' },
];

const IMPLEMENTATION_ICONS: Record<string, any> = {
  native: Zap,
  mcp: Server,
  openapi: Globe,
  python: Code2,
  docker: Container,
};

const IMPLEMENTATION_LABELS: Record<string, string> = {
  native: 'Native',
  mcp: 'MCP',
  openapi: 'OpenAPI',
  python: 'Python',
  docker: 'Docker',
};

function healthStatusDot(health: ToolV2HealthMetrics) {
  if (!health) return { color: 'bg-gray-500', status: 'unknown' };
  if (health.error_rate > 0.5) return { color: 'bg-red-500', status: 'unhealthy' };
  if (health.error_rate > 0.1 || health.avg_latency_ms > 5000) return { color: 'bg-amber-400', status: 'degraded' };
  return { color: 'bg-green-500', status: 'healthy' };
}

function formatNumber(n: number) {
  return new Intl.NumberFormat('en-US', { maximumFractionDigits: 1 }).format(n);
}

interface SchemaProperty {
  type?: string;
  description?: string;
  enum?: any[];
  default?: any;
}

function SchemaViewer({ schema, title }: { schema?: Record<string, any> | null; title: string }) {
  if (!schema || Object.keys(schema).length === 0) {
    return (
      <div className="text-xs text-secondaryText">
        No {title.toLowerCase()} schema defined.
      </div>
    );
  }
  return (
    <div className="space-y-2">
      <div className="text-xs font-semibold uppercase tracking-widest text-secondaryText">{title}</div>
      <pre className="text-xs text-secondaryText bg-surface-lowest p-3 rounded-lg border border-outline/10 overflow-x-auto">
        {JSON.stringify(schema, null, 2)}
      </pre>
    </div>
  );
}

function TestPanel({ tool, onClose }: { tool: ToolV2Info; onClose: () => void }) {
  const [params, setParams] = useState<Record<string, any>>({});
  const [executing, setExecuting] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [execTime, setExecTime] = useState<number | null>(null);
  const [error, setError] = useState('');

  const properties = tool.input_schema?.properties || {};
  const required = tool.input_schema?.required || [];

  const handleExecute = async () => {
    setExecuting(true);
    setError('');
    setResult(null);
    setExecTime(null);
    const start = performance.now();
    try {
      const res = await apiClient.executeToolV2(tool.tool_id, params);
      setResult(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Execution failed');
    } finally {
      setExecTime(performance.now() - start);
      setExecuting(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h4 className="text-sm font-semibold">Test Tool</h4>
        <button onClick={onClose} className="text-secondaryText hover:text-primaryText transition-colors">
          <X className="w-4 h-4" />
        </button>
      </div>

      <div className="space-y-3 max-h-64 overflow-y-auto pr-1">
        {Object.entries(properties as Record<string, SchemaProperty>).map(([key, prop]) => {
          const isRequired = required.includes(key);
          const type = prop.type || 'string';
          if (type === 'boolean') {
            return (
              <label key={key} className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  className="rounded border-outline/30 bg-surface-lowest"
                  checked={!!params[key]}
                  onChange={(e) => setParams((p) => ({ ...p, [key]: e.target.checked }))}
                />
                <span className="text-primaryText">{key}</span>
                {isRequired && <span className="text-red-400 text-xs">*</span>}
                {prop.description && <span className="text-secondaryText text-xs ml-1">— {prop.description}</span>}
              </label>
            );
          }
          if (type === 'number' || type === 'integer') {
            return (
              <div key={key} className="space-y-1">
                <label className="text-xs text-secondaryText flex items-center gap-1">
                  {key}
                  {isRequired && <span className="text-red-400">*</span>}
                </label>
                <input
                  type="number"
                  className="w-full obsidian-input text-sm"
                  placeholder={prop.description || key}
                  value={params[key] ?? ''}
                  onChange={(e) => setParams((p) => ({ ...p, [key]: e.target.valueAsNumber }))}
                />
              </div>
            );
          }
          if (type === 'string' && (key === 'code' || prop.description?.toLowerCase().includes('code'))) {
            return (
              <div key={key} className="space-y-1">
                <label className="text-xs text-secondaryText flex items-center gap-1">
                  {key}
                  {isRequired && <span className="text-red-400">*</span>}
                </label>
                <textarea
                  rows={5}
                  className="w-full obsidian-input text-sm font-mono"
                  placeholder={prop.description || key}
                  value={params[key] ?? ''}
                  onChange={(e) => setParams((p) => ({ ...p, [key]: e.target.value }))}
                />
              </div>
            );
          }
          return (
            <div key={key} className="space-y-1">
              <label className="text-xs text-secondaryText flex items-center gap-1">
                {key}
                {isRequired && <span className="text-red-400">*</span>}
              </label>
              <input
                type="text"
                className="w-full obsidian-input text-sm"
                placeholder={prop.description || key}
                value={params[key] ?? ''}
                onChange={(e) => setParams((p) => ({ ...p, [key]: e.target.value }))}
              />
            </div>
          );
        })}
      </div>

      <motion.button
        onClick={handleExecute}
        disabled={executing}
        whileTap={{ scale: 0.96 }}
        className="btn-primary w-full flex items-center justify-center gap-2 text-sm disabled:opacity-50"
      >
        {executing ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
        Execute
      </motion.button>

      {error && (
        <div className="p-3 rounded-lg border border-red-500/20 bg-red-500/10 text-xs text-red-400">
          {error}
        </div>
      )}

      {result !== null && (
        <div className="space-y-1">
          <div className="flex items-center justify-between text-xs text-secondaryText">
            <span>Result</span>
            {execTime !== null && <span>{formatNumber(execTime)}ms</span>}
          </div>
          <pre className="text-xs text-secondaryText bg-surface-lowest p-3 rounded-lg border border-outline/10 overflow-x-auto max-h-64">
            {JSON.stringify(result, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}

function ToolDrawer({ tool, onClose }: { tool: ToolV2Info; onClose: () => void }) {
  const [showTest, setShowTest] = useState(false);
  const ImplIcon = IMPLEMENTATION_ICONS[tool.implementation.type] || Wrench;
  const health = healthStatusDot(tool.health);

  return (
    <motion.div
      initial={{ x: '100%' }}
      animate={{ x: 0 }}
      exit={{ x: '100%' }}
      transition={{ type: 'spring', damping: 25, stiffness: 200 }}
      className="fixed inset-y-0 right-0 w-full max-w-md bg-surface-low border-l border-outline/20 shadow-2xl z-50 flex flex-col"
    >
      <div className="flex items-center justify-between p-5 border-b border-outline/10">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-surface-high flex items-center justify-center border border-outline/10">
            <ImplIcon className="w-5 h-5 text-primary" />
          </div>
          <div>
            <h3 className="text-base font-semibold">{tool.name}</h3>
            <p className="text-xs text-secondaryText">{tool.tool_id}</p>
          </div>
        </div>
        <button onClick={onClose} className="text-secondaryText hover:text-primaryText transition-colors">
          <X className="w-5 h-5" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-5 space-y-6">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs px-2 py-1 rounded-full bg-surface-high border border-outline/10 text-primaryText flex items-center gap-1">
            <ImplIcon className="w-3 h-3" />
            {IMPLEMENTATION_LABELS[tool.implementation.type] || tool.implementation.type}
          </span>
          <span className="text-xs px-2 py-1 rounded-full bg-surface-high border border-outline/10 text-secondaryText">
            {tool.category}
          </span>
          {tool.tags.map((tag) => (
            <span key={tag} className="text-xs px-2 py-1 rounded-full bg-surface-high border border-outline/10 text-secondaryText">
              {tag}
            </span>
          ))}
          <span className="text-xs px-2 py-1 rounded-full bg-surface-high border border-outline/10 text-secondaryText flex items-center gap-1">
            <User className="w-3 h-3" />
            {tool.author}
          </span>
        </div>

        <p className="text-sm text-secondaryText leading-relaxed">{tool.description}</p>

        <div className="grid grid-cols-3 gap-3">
          <div className="bg-surface-lowest border border-outline/10 rounded-lg p-3 text-center">
            <div className="text-lg font-semibold">{tool.health.invocation_count}</div>
            <div className="text-[10px] uppercase tracking-widest text-secondaryText">Invocations</div>
          </div>
          <div className="bg-surface-lowest border border-outline/10 rounded-lg p-3 text-center">
            <div className="text-lg font-semibold">{formatNumber(tool.health.avg_latency_ms)}ms</div>
            <div className="text-[10px] uppercase tracking-widest text-secondaryText">Avg Latency</div>
          </div>
          <div className="bg-surface-lowest border border-outline/10 rounded-lg p-3 text-center">
            <div className={`text-lg font-semibold ${tool.health.error_rate > 0.1 ? 'text-amber-400' : 'text-green-400'}`}>
              {formatNumber(tool.health.error_rate * 100)}%
            </div>
            <div className="text-[10px] uppercase tracking-widest text-secondaryText">Error Rate</div>
          </div>
        </div>

        <div className="flex items-center gap-2 text-xs">
          <span className={`w-2 h-2 rounded-full ${health.color}`} />
          <span className="text-secondaryText capitalize">{health.status}</span>
        </div>

        {tool.dependencies.length > 0 && (
          <div className="space-y-2">
            <div className="text-xs font-semibold uppercase tracking-widest text-secondaryText flex items-center gap-1">
              <Package className="w-3 h-3" /> Dependencies
            </div>
            <div className="flex flex-wrap gap-2">
              {tool.dependencies.map((dep) => (
                <span key={dep} className="text-xs px-2 py-1 rounded bg-surface-high border border-outline/10 text-secondaryText">
                  {dep}
                </span>
              ))}
            </div>
          </div>
        )}

        <SchemaViewer schema={tool.input_schema} title="Input Schema" />
        <SchemaViewer schema={tool.output_schema} title="Output Schema" />

        {!showTest && (
          <motion.button
            onClick={() => setShowTest(true)}
            whileTap={{ scale: 0.96 }}
            className="btn-primary w-full flex items-center justify-center gap-2 text-sm"
          >
            <Play className="w-4 h-4" /> Test Tool
          </motion.button>
        )}

        {showTest && <TestPanel tool={tool} onClose={() => setShowTest(false)} />}
      </div>
    </motion.div>
  );
}

export default function Tools() {
  const [tools, setTools] = useState<ToolV2Info[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [activeTab, setActiveTab] = useState<TabKey>('all');
  const [selectedTool, setSelectedTool] = useState<ToolV2Info | null>(null);
  const [showImportModal, setShowImportModal] = useState(false);
  const [importUrl, setImportUrl] = useState('');
  const [importCategory, setImportCategory] = useState('api');
  const [importing, setImporting] = useState(false);
  const [importError, setImportError] = useState('');
  const [importSuccess, setImportSuccess] = useState('');

  const refresh = async () => {
    try {
      const data = await apiClient.getToolsV2();
      setTools(data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
  }, []);

  const filtered = useMemo(() => {
    return tools.filter((t) => {
      const matchesTab = activeTab === 'all' || t.implementation.type === activeTab || (activeTab === 'custom' && !['native', 'mcp', 'openapi', 'python', 'docker'].includes(t.implementation.type));
      const q = search.toLowerCase();
      const matchesSearch =
        !q ||
        t.name.toLowerCase().includes(q) ||
        t.description.toLowerCase().includes(q) ||
        t.tool_id.toLowerCase().includes(q) ||
        t.tags.some((tag) => tag.toLowerCase().includes(q));
      return matchesTab && matchesSearch;
    });
  }, [tools, activeTab, search]);

  const handleImport = async () => {
    if (!importUrl.trim()) return;
    setImporting(true);
    setImportError('');
    setImportSuccess('');
    try {
      const res = await apiClient.ingestOpenAPISpec(importUrl.trim(), importCategory.trim() || 'api');
      setImportSuccess(`Imported ${res.count} tool(s) successfully`);
      setImportUrl('');
      await refresh();
    } catch (e) {
      setImportError(e instanceof Error ? e.message : 'Import failed');
    } finally {
      setImporting(false);
    }
  };

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex flex-col gap-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight mb-1">Tool Marketplace</h1>
          <p className="text-secondaryText text-sm">Discover, register, and test tools available to agents.</p>
        </div>
        <button
          onClick={() => setShowImportModal(true)}
          className="btn-primary flex items-center gap-2 text-sm"
        >
          <Download className="w-4 h-4" /> Import OpenAPI
        </button>
      </div>

      {/* Search & Tabs */}
      <div className="flex flex-col md:flex-row gap-4">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-secondaryText" />
          <input
            className="w-full obsidian-input pl-10 transition-transform duration-200 focus:scale-[1.01]"
            placeholder="Search tools..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <div className="flex gap-2 overflow-x-auto">
          {TABS.map((tab) => (
            <motion.button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              whileTap={{ scale: 0.95 }}
              className={`relative text-xs px-4 py-2 rounded-lg border whitespace-nowrap transition-colors ${
                activeTab === tab.key
                  ? 'bg-primary text-background border-primary font-medium'
                  : 'bg-surface-low border-outline/20 text-secondaryText hover:border-primary/30'
              }`}
            >
              {tab.label}
              {activeTab === tab.key && (
                <motion.div
                  layoutId="toolsTab"
                  className="absolute inset-0 rounded-lg border-2 border-primary/50"
                  transition={{ type: 'spring', stiffness: 300, damping: 30 }}
                />
              )}
            </motion.button>
          ))}
        </div>
      </div>

      {/* Grid */}
      {loading ? (
        <div className="text-center py-16"><Skeleton className="h-4 w-32 mx-auto" /></div>
      ) : tools.length === 0 ? (
        <EmptyState
          icon={FileCode}
          title="No tools registered"
          description="Import an OpenAPI spec or register custom tools to get started."
          actionLabel="Import OpenAPI"
          onAction={() => setShowImportModal(true)}
        />
      ) : filtered.length === 0 ? (
        <div className="text-center py-16 text-secondaryText">
          No tools match your filters.
          <div className="mt-2 text-xs">Try adjusting your search or import new tools.</div>
        </div>
      ) : (
        <motion.div
          className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4"
          initial="hidden"
          animate="visible"
          variants={{
            hidden: {},
            visible: { transition: { staggerChildren: 0.05 } },
          }}
        >
          {filtered.map((tool) => {
            const ImplIcon = IMPLEMENTATION_ICONS[tool.implementation.type] || Wrench;
            const health = healthStatusDot(tool.health);
            return (
              <motion.div
                key={tool.tool_id}
                layout
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                whileHover={{ y: -3, boxShadow: '0 8px 30px rgba(0,229,255,0.06)' }}
                whileTap={{ scale: 0.98 }}
                className="bg-surface-low border border-outline/20 rounded-xl hover:border-primary/30 transition-colors p-5 flex flex-col gap-4"
              >
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-lg bg-surface-high flex items-center justify-center border border-outline/10">
                      <ImplIcon className="w-5 h-5 text-primary" />
                    </div>
                    <div>
                      <h3 className="text-sm font-semibold leading-tight">{tool.name}</h3>
                      <div className="flex items-center gap-2 mt-1">
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-surface-high border border-outline/10 text-secondaryText uppercase tracking-wider">
                          {tool.category}
                        </span>
                        <span className={`w-1.5 h-1.5 rounded-full ${health.color}`} title={health.status} />
                      </div>
                    </div>
                  </div>
                </div>

                <p className="text-sm text-secondaryText line-clamp-2">{tool.description}</p>

                <div className="flex flex-wrap gap-1.5">
                  {(tool.tags || []).slice(0, 4).map((tag) => (
                    <span
                      key={tag}
                      className="text-[10px] px-2 py-0.5 rounded-full bg-surface-high border border-outline/10 text-secondaryText"
                    >
                      {tag}
                    </span>
                  ))}
                  {(tool.tags || []).length > 4 && (
                    <span className="text-[10px] px-2 py-0.5 rounded-full bg-surface-high border border-outline/10 text-secondaryText">
                      +{tool.tags.length - 4}
                    </span>
                  )}
                </div>

                <div className="mt-auto flex items-center justify-between border-t border-outline/10 pt-3">
                  <div className="flex items-center gap-1.5 text-[10px] text-secondaryText">
                    <User className="w-3 h-3" />
                    {tool.author}
                  </div>
                  <motion.button
                    onClick={() => setSelectedTool(tool)}
                    whileTap={{ scale: 0.96 }}
                    className="text-xs flex items-center gap-1 text-primary hover:underline"
                  >
                    Details <ChevronRight className="w-3 h-3" />
                  </motion.button>
                </div>
              </motion.div>
            );
          })}
        </motion.div>
      )}

      {/* Import Modal */}
      <AnimatePresence>
        {showImportModal && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4"
            onClick={() => setShowImportModal(false)}
          >
            <motion.div
              initial={{ scale: 0.95, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.95, opacity: 0 }}
              onClick={(e) => e.stopPropagation()}
              className="bg-surface-low border border-outline/20 rounded-xl w-full max-w-lg p-6 space-y-4 shadow-2xl"
            >
              <div className="flex items-center justify-between">
                <h3 className="text-lg font-semibold">Install from OpenAPI</h3>
                <button onClick={() => setShowImportModal(false)} className="text-secondaryText hover:text-primaryText">
                  <X className="w-5 h-5" />
                </button>
              </div>

              <div className="space-y-3">
                <div>
                  <label className="text-xs text-secondaryText block mb-1">Spec URL</label>
                  <input
                    className="w-full obsidian-input text-sm"
                    placeholder="https://example.com/openapi.yaml"
                    value={importUrl}
                    onChange={(e) => setImportUrl(e.target.value)}
                  />
                </div>
                <div>
                  <label className="text-xs text-secondaryText block mb-1">Category</label>
                  <input
                    className="w-full obsidian-input text-sm"
                    placeholder="api"
                    value={importCategory}
                    onChange={(e) => setImportCategory(e.target.value)}
                  />
                </div>
              </div>

              {importError && (
                <div className="p-3 rounded-lg border border-red-500/20 bg-red-500/10 text-xs text-red-400">
                  {importError}
                </div>
              )}
              {importSuccess && (
                <div className="p-3 rounded-lg border border-green-500/20 bg-green-500/10 text-xs text-green-400">
                  {importSuccess}
                </div>
              )}

              <div className="flex justify-end gap-2 pt-2">
                <button onClick={() => setShowImportModal(false)} className="btn-secondary text-sm">
                  Cancel
                </button>
                <button
                  onClick={handleImport}
                  disabled={importing || !importUrl.trim()}
                  className="btn-primary text-sm flex items-center gap-2 disabled:opacity-50"
                >
                  {importing ? <Loader2 className="w-4 h-4 animate-spin" /> : <Download className="w-4 h-4" />}
                  Import
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Drawer */}
      <AnimatePresence>
        {selectedTool && (
          <>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="fixed inset-0 bg-black/40 z-40"
              onClick={() => setSelectedTool(null)}
            />
            <ToolDrawer tool={selectedTool} onClose={() => setSelectedTool(null)} />
          </>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

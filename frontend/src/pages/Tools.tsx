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
 Package,
 User,
 FileCode,
} from 'lucide-react';
import { apiClient, type ToolV2Info, type ToolV2HealthMetrics } from '../api/client';
import { buttonTap, cardInteractions } from '../lib/animations';
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
 <pre className="text-xs text-secondaryText bg-surface-lowest p-4 rounded-none border border-outline/10 overflow-x-auto">
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
 <button onClick={onClose} className="text-secondaryText hover:text-primaryText ">
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
 className="rounded-none border-outline/30 bg-surface-lowest"
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
 <div className="p-4 rounded-none border border-red-500/20 bg-red-500/10 text-xs text-red-400">
 {error}
 </div>
 )}

 {result !== null && (
 <div className="space-y-1">
 <div className="flex items-center justify-between text-xs text-secondaryText">
 <span>Result</span>
 {execTime !== null && <span>{formatNumber(execTime)}ms</span>}
 </div>
 <pre className="text-xs text-secondaryText bg-surface-lowest p-4 rounded-none border border-outline/10 overflow-x-auto max-h-64">
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
 <div className="flex items-center justify-between p-6 border-b border-outline/10">
 <div className="flex items-center gap-3">
 <div className="w-10 h-10 rounded-none bg-surface-high flex items-center justify-center border border-outline/10">
 <ImplIcon className="w-5 h-5 text-primary" />
 </div>
 <div>
 <h3 className="text-base font-semibold">{tool.name}</h3>
 <p className="text-xs text-secondaryText">{tool.tool_id}</p>
 </div>
 </div>
 <button onClick={onClose} className="text-secondaryText hover:text-primaryText ">
 <X className="w-5 h-5" />
 </button>
 </div>

 <div className="flex-1 overflow-y-auto p-6 space-y-6">
 <div className="flex flex-wrap items-center gap-2">
 <span className="text-xs px-2 py-1 rounded-none bg-surface-high border border-outline/10 text-primaryText flex items-center gap-1">
 <ImplIcon className="w-3 h-3" />
 {IMPLEMENTATION_LABELS[tool.implementation.type] || tool.implementation.type}
 </span>
 <span className="text-xs px-2 py-1 rounded-none bg-surface-high border border-outline/10 text-secondaryText">
 {tool.category}
 </span>
 {tool.tags.map((tag) => (
 <span key={tag} className="text-xs px-2 py-1 rounded-none bg-surface-high border border-outline/10 text-secondaryText">
 {tag}
 </span>
 ))}
 <span className="text-xs px-2 py-1 rounded-none bg-surface-high border border-outline/10 text-secondaryText flex items-center gap-1">
 <User className="w-3 h-3" />
 {tool.author}
 </span>
 </div>

 <p className="text-sm text-secondaryText leading-relaxed">{tool.description}</p>

 <div className="grid grid-cols-3 gap-3">
 <div className="bg-surface-lowest border border-outline/10 rounded-none p-4 text-center">
 <div className="text-lg font-semibold">{tool.health.invocation_count}</div>
 <div className="text-[10px] uppercase tracking-widest text-secondaryText">Invocations</div>
 </div>
 <div className="bg-surface-lowest border border-outline/10 rounded-none p-4 text-center">
 <div className="text-lg font-semibold">{formatNumber(tool.health.avg_latency_ms)}ms</div>
 <div className="text-[10px] uppercase tracking-widest text-secondaryText">Avg Latency</div>
 </div>
 <div className="bg-surface-lowest border border-outline/10 rounded-none p-4 text-center">
 <div className={`text-lg font-semibold ${tool.health.error_rate > 0.1 ? 'text-amber-400' : 'text-green-400'}`}>
 {formatNumber(tool.health.error_rate * 100)}%
 </div>
 <div className="text-[10px] uppercase tracking-widest text-secondaryText">Error Rate</div>
 </div>
 </div>

 <div className="flex items-center gap-2 text-xs">
 <span className={`w-2 h-2 rounded-none ${health.color}`} />
 <span className="text-secondaryText capitalize">{health.status}</span>
 </div>

 {tool.dependencies.length > 0 && (
 <div className="space-y-2">
 <div className="text-xs font-semibold uppercase tracking-widest text-secondaryText flex items-center gap-1">
 <Package className="w-3 h-3" /> Dependencies
 </div>
 <div className="flex flex-wrap gap-2">
 {tool.dependencies.map((dep) => (
 <span key={dep} className="text-xs px-2 py-1 rounded-none bg-surface-high border border-outline/10 text-secondaryText">
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
 <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex flex-col gap-10">
 {/* Header */}
 <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-6">
 <div>
 <h1 className="text-4xl font-pixel uppercase tracking-tight mb-2">Tool Marketplace</h1>
 <p className="text-secondaryText text-xl font-retro uppercase opacity-60">Registry of authorized orchestration modules.</p>
 </div>
 <button
 onClick={() => setShowImportModal(true)}
 className="btn-primary flex items-center gap-3 py-4"
 >
 <Download className="w-5 h-5" /> [ IMPORT_SPEC ]
 </button>
 </div>

 {/* Search & Tabs */}
 <div className="flex flex-col md:flex-row gap-6">
 <div className="relative flex-1">
 <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-secondaryText" />
 <input
 className="w-full pixel-input pl-8 py-4 text-lg font-retro uppercase"
 placeholder="Search Registry..."
 value={search}
 onChange={(e) => setSearch(e.target.value)}
 />
 </div>
 <div className="flex gap-3 overflow-x-auto pb-2 md:pb-0">
 {TABS.map((tab) => (
 <motion.button
 key={tab.key}
 onClick={() => setActiveTab(tab.key)}
 {...buttonTap}
 className={`text-[10px] font-pixel uppercase px-6 py-2 border-4 whitespace-nowrap ${
 activeTab === tab.key
 ? 'bg-primary text-white border-outline shadow-pixel'
 : 'bg-white border-outline/10 text-secondaryText hover:border-outline'
 }`}
 >
 {tab.label}
 </motion.button>
 ))}
 </div>
 </div>

 {/* Grid */}
 {loading ? (
 <div className="text-center py-8"><Skeleton className="h-4 w-32 mx-auto" /></div>
 ) : tools.length === 0 ? (
 <EmptyState
 icon={FileCode}
 title="No tools registered"
 description="Import an OpenAPI spec or register custom tools to get started."
 actionLabel="Import OpenAPI"
 onAction={() => setShowImportModal(true)}
 />
 ) : filtered.length === 0 ? (
 <div className="text-center py-8 text-secondaryText">
 No tools match your filters.
 <div className="mt-2 text-xs">Try adjusting your search or import new tools.</div>
 </div>
 ) : (
 <motion.div
 className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-8"
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
 initial={{ opacity: 0, scale: 0.95 }}
 animate={{ opacity: 1, scale: 1 }}
 {...cardInteractions}
 className="pixel-card p-6 flex flex-col gap-5 cursor-pointer group"
 onClick={() => setSelectedTool(tool)}
 >
 <div className="flex items-start justify-between">
 <div className="flex items-center gap-4">
 <div className="w-12 h-12 border-4 border-outline bg-surface-high flex items-center justify-center group-hover:bg-primary/20 shadow-pixel">
 <ImplIcon className="w-6 h-6 text-primary" />
 </div>
 <div>
 <h3 className="text-xs font-pixel uppercase leading-tight group-hover:text-primary ">{tool.name}</h3>
 <div className="flex items-center gap-2 mt-2">
 <span className="text-[8px] font-pixel px-2 py-1 border-4 border-outline bg-accent-yellow text-primaryText uppercase tracking-tighter">
 {tool.category}
 </span>
 <div className={`w-3 h-3 border-4 border-outline ${health.color}`} title={health.status} />
 </div>
 </div>
 </div>
 </div>

 <p className="text-lg font-retro text-secondaryText line-clamp-2 leading-relaxed uppercase opacity-80">{tool.description}</p>

 <div className="flex flex-wrap gap-2">
 {(tool.tags || []).slice(0, 4).map((tag) => (
 <span
 key={tag}
 className="text-[8px] font-pixel px-2 py-1 border-4 border-outline bg-white text-secondaryText uppercase"
 >
 {tag}
 </span>
 ))}
 </div>

 <div className="mt-auto flex items-center justify-between border-t-4 border-outline/5 pt-4">
 <div className="flex items-center gap-2 text-[8px] font-pixel text-secondaryText uppercase">
 <User className="w-3 h-3" />
 {tool.author}
 </div>
 <div className="text-[10px] font-pixel text-primary uppercase underline">
 [ VIEW_DETAILS ]
 </div>
 </div>
 </motion.div>
 );
 })}
 </motion.div>
 )} <AnimatePresence>
 {showImportModal && (
 <motion.div
 initial={{ opacity: 0 }}
 animate={{ opacity: 1 }}
 exit={{ opacity: 0 }}
 className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4"
 onClick={() => setShowImportModal(false)}
 >
 <motion.div
 initial={{ scale: 0.95, opacity: 0 }}
 animate={{ scale: 1, opacity: 1 }}
 exit={{ scale: 0.95, opacity: 0 }}
 onClick={(e) => e.stopPropagation()}
 className="bg-white border-4 border-outline w-full max-w-lg p-8 space-y-6 shadow-pixel"
 >
 <div className="flex items-center justify-between">
 <h3 className="text-xl font-pixel uppercase tracking-tight">Import Toolset</h3>
 <button onClick={() => setShowImportModal(false)} className="text-secondaryText hover:text-primaryText border-4 border-outline p-1">
 <X className="w-5 h-5" />
 </button>
 </div>

 <div className="space-y-4">
 <div>
 <label className="text-[10px] font-pixel uppercase text-secondaryText block mb-2">Spec Target URL</label>
 <input
 className="w-full pixel-input text-lg font-retro"
 placeholder="https://core.os/openapi.yaml"
 value={importUrl}
 onChange={(e) => setImportUrl(e.target.value)}
 />
 </div>
 <div>
 <label className="text-[10px] font-pixel uppercase text-secondaryText block mb-2">Registry Category</label>
 <input
 className="w-full pixel-input text-lg font-retro uppercase"
 placeholder="system_mod"
 value={importCategory}
 onChange={(e) => setImportCategory(e.target.value)}
 />
 </div>
 </div>

 {importError && (
 <div className="p-4 border-4 border-[#FF4B4B]/20 bg-[#FF4B4B]/10 font-retro text-lg text-[#FF4B4B] uppercase">
 !! ERR: {importError}
 </div>
 )}
 {importSuccess && (
 <div className="p-4 border-4 border-secondary/20 bg-secondary/10 font-retro text-lg text-secondary uppercase">
 {'>> '} {importSuccess}
 </div>
 )}

 <div className="flex justify-end gap-3 pt-4">
 <button onClick={() => setShowImportModal(false)} className="btn-secondary py-4 px-6">
 [ CANCEL ]
 </button>
 <button
 onClick={handleImport}
 disabled={importing || !importUrl.trim()}
 className="btn-primary py-4 px-6 flex items-center gap-2 disabled:opacity-50"
 >
 {importing ? <Loader2 className="w-5 h-5 animate-spin" /> : <Download className="w-5 h-5" />}
 [ INITIALIZE_IMPORT ]
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

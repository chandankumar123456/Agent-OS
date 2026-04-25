import { useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Skeleton } from '../components/ui/Skeleton';
import {
  Activity,
  CheckCircle,
  Clock,
  XCircle,
  AlertTriangle,
  Eye,
  Layers,
  Zap,
  BarChart3,
  ChevronRight,
  X,
} from 'lucide-react';
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';
import { apiClient, type DashboardMetrics, type TraceListItem, type TraceDetail } from '../api/client';

const CHART_COLORS = ['#06b6d4', '#22c55e', '#f59e0b', '#ef4444', '#8b5cf6'];

const Monitor = () => {
  const [metrics, setMetrics] = useState<DashboardMetrics | null>(null);
  const [traces, setTraces] = useState<TraceListItem[]>([]);
  const [traceTotal, setTraceTotal] = useState(0);
  const [selectedTrace, setSelectedTrace] = useState<TraceDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [tracePage, setTracePage] = useState(1);

  useEffect(() => {
    let mounted = true;
    const loadData = async () => {
      try {
        const [dashboardData, tracesData] = await Promise.all([
          apiClient.getDashboardMetrics(),
          apiClient.getTraces(tracePage, 10),
        ]);
        if (!mounted) return;
        setMetrics(dashboardData);
        setTraces(tracesData.traces);
        setTraceTotal(tracesData.total);
      } catch (err) {
        console.error('Failed to load analytics data', err);
      } finally {
        if (mounted) setLoading(false);
      }
    };
    loadData();
    return () => {
      mounted = false;
    };
  }, [tracePage]);

  const openTrace = async (traceId: string) => {
    try {
      const detail = await apiClient.getTraceDetail(traceId);
      setSelectedTrace(detail);
    } catch (err) {
      console.error('Failed to load trace detail', err);
    }
  };

  const kpiCards = metrics
    ? [
        {
          label: 'Total Tasks',
          value: metrics.total_tasks,
          icon: Layers,
          color: 'text-cyan-400',
          bg: 'bg-cyan-400/10',
        },
        {
          label: 'Success Rate',
          value:
            metrics.total_tasks > 0
              ? `${((metrics.completed_tasks / metrics.total_tasks) * 100).toFixed(1)}%`
              : '0%',
          icon: CheckCircle,
          color: 'text-green-400',
          bg: 'bg-green-400/10',
        },
        {
          label: 'Avg Duration',
          value: `${metrics.avg_task_duration.toFixed(1)}s`,
          icon: Clock,
          color: 'text-amber-400',
          bg: 'bg-amber-400/10',
        },
        {
          label: 'Tokens Used',
          value: metrics.total_tokens_used.toLocaleString(),
          icon: Zap,
          color: 'text-primary',
          bg: 'bg-primary/10',
        },
      ]
    : [];

  if (loading) {
    return (
      <div className="flex flex-col gap-8">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <Skeleton className="h-24" />
          <Skeleton className="h-24" />
          <Skeleton className="h-24" />
          <Skeleton className="h-24" />
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <Skeleton className="h-80" />
          <Skeleton className="h-80" />
          <Skeleton className="h-80" />
        </div>
        <Skeleton className="h-64" />
        <Skeleton className="h-48" />
      </div>
    );
  }

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex flex-col gap-8">
      {/* Header */}
      <div className="flex justify-between items-end">
        <div>
          <h1 className="text-3xl font-bold tracking-tight mb-1 cursor-default">Analytics Dashboard</h1>
          <p className="text-secondaryText text-sm">
            System observability, traces, and performance metrics.
          </p>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        {kpiCards.map((stat, i) => (
          <motion.div
            key={i}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ type: 'spring', stiffness: 300, delay: i * 0.1 }}
            whileHover={{ y: -3, boxShadow: '0 8px 30px rgba(0,229,255,0.06)' }}
            className="bg-surface-low border border-outline/20 rounded-xl p-5"
          >
            <div className="flex justify-between items-start mb-4">
              <span className="text-secondaryText text-sm font-medium">{stat.label}</span>
              <div className={`w-8 h-8 rounded-lg ${stat.bg} flex items-center justify-center`}>
                <stat.icon className={`w-4 h-4 ${stat.color}`} />
              </div>
            </div>
            <div className="text-3xl font-bold tracking-tight text-primaryText">{stat.value}</div>
          </motion.div>
        ))}
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Tasks Over Time */}
        <motion.div whileHover={{ scale: 1.01 }} transition={{ type: 'spring', stiffness: 400 }}>
          <div className="bg-surface-low border border-outline/20 rounded-xl p-6">
            <h3 className="text-sm font-semibold text-secondaryText mb-4 flex items-center gap-2">
              <Activity className="w-4 h-4 text-cyan-400" />
              Tasks Over Time (7d)
            </h3>
          <div className="w-full h-64 min-w-0">
            <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={0} debounce={1}>
              <LineChart data={metrics?.tasks_over_time || []}>
                <CartesianGrid strokeDasharray="3 3" stroke="#2a2a2b" />
                <XAxis
                  dataKey="date"
                  tick={{ fill: '#bac9cc', fontSize: 12 }}
                  tickFormatter={(value: string) => (value || '').slice(5)}
                  axisLine={{ stroke: '#3b494c' }}
                />
                <YAxis
                  tick={{ fill: '#bac9cc', fontSize: 12 }}
                  axisLine={{ stroke: '#3b494c' }}
                  allowDecimals={false}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: '#1c1b1c',
                    border: '1px solid #3b494c',
                    borderRadius: '0.5rem',
                    color: '#e5e2e3',
                  }}
                />
                <Line
                  type="monotone"
                  dataKey="count"
                  stroke="#06b6d4"
                  strokeWidth={2}
                  dot={{ fill: '#06b6d4', r: 3 }}
                  activeDot={{ r: 5 }}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
          </div>
        </motion.div>

        {/* Tasks by Status */}
        <motion.div whileHover={{ scale: 1.01 }} transition={{ type: 'spring', stiffness: 400 }}>
          <div className="bg-surface-low border border-outline/20 rounded-xl p-6">
            <h3 className="text-sm font-semibold text-secondaryText mb-4 flex items-center gap-2">
              <BarChart3 className="w-4 h-4 text-green-400" />
              Tasks by Status
            </h3>
          <div className="w-full h-64 min-w-0">
            <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={0} debounce={1}>
              <BarChart data={metrics?.tasks_by_status || []}>
                <CartesianGrid strokeDasharray="3 3" stroke="#2a2a2b" />
                <XAxis
                  dataKey="status"
                  tick={{ fill: '#bac9cc', fontSize: 12 }}
                  axisLine={{ stroke: '#3b494c' }}
                />
                <YAxis
                  tick={{ fill: '#bac9cc', fontSize: 12 }}
                  axisLine={{ stroke: '#3b494c' }}
                  allowDecimals={false}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: '#1c1b1c',
                    border: '1px solid #3b494c',
                    borderRadius: '0.5rem',
                    color: '#e5e2e3',
                  }}
                />
                <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                  {(metrics?.tasks_by_status || []).map((_entry, index) => (
                    <Cell key={`cell-${index}`} fill={CHART_COLORS[index % CHART_COLORS.length]} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          </div>
        </motion.div>

        {/* Top Agents */}
        <motion.div whileHover={{ scale: 1.01 }} transition={{ type: 'spring', stiffness: 400 }}>
          <div className="bg-surface-low border border-outline/20 rounded-xl p-6">
            <h3 className="text-sm font-semibold text-secondaryText mb-4 flex items-center gap-2">
              <Layers className="w-4 h-4 text-amber-400" />
              Top Agents
            </h3>
          <div className="w-full h-64 min-w-0">
            <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={0} debounce={1}>
              <PieChart>
                <Pie
                  data={metrics?.top_agents || []}
                  cx="50%"
                  cy="50%"
                  innerRadius={60}
                  outerRadius={80}
                  paddingAngle={4}
                  dataKey="count"
                  nameKey="agent_name"
                >
                  {(metrics?.top_agents || []).map((_entry, index) => (
                    <Cell key={`cell-${index}`} fill={CHART_COLORS[index % CHART_COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{
                    backgroundColor: '#1c1b1c',
                    border: '1px solid #3b494c',
                    borderRadius: '0.5rem',
                    color: '#e5e2e3',
                  }}
                />
              </PieChart>
            </ResponsiveContainer>
            <div className="flex flex-wrap gap-3 justify-center mt-2">
              {(metrics?.top_agents || []).map((entry, index) => (
                <div key={entry.agent_name} className="flex items-center gap-1.5 text-xs text-secondaryText">
                  <div
                    className="w-2.5 h-2.5 rounded-full"
                    style={{ backgroundColor: CHART_COLORS[index % CHART_COLORS.length] }}
                  />
                  {entry.agent_name}
                </div>
              ))}
            </div>
            </div>
          </div>
        </motion.div>
      </div>

      {/* Recent Traces Table */}
      <div className="bg-surface-low border border-outline/20 rounded-xl p-6">
        <h3 className="text-sm font-semibold text-secondaryText mb-4 flex items-center gap-2">
          <Eye className="w-4 h-4 text-primary" />
          Recent Traces
        </h3>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-outline/20 text-secondaryText">
                <th className="pb-3 font-medium">Trace ID</th>
                <th className="pb-3 font-medium">Task ID</th>
                <th className="pb-3 font-medium">Status</th>
                <th className="pb-3 font-medium">Duration</th>
                <th className="pb-3 font-medium">Started At</th>
                <th className="pb-3 font-medium text-right">Action</th>
              </tr>
            </thead>
            <tbody className="text-primaryText">
              {traces.map((trace, idx) => (
                <motion.tr
                  key={trace.trace_id}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ delay: idx * 0.03 }}
                  whileHover={{ backgroundColor: 'rgba(42,42,43,0.5)' }}
                  className="border-b border-outline/10 hover:bg-surface-high/50 transition-colors"
                >
                  <td className="py-3 font-mono text-xs">{(trace.trace_id || '').slice(0, 8)}...</td>
                  <td className="py-3 font-mono text-xs">{(trace.task_id || '').slice(0, 8)}...</td>
                  <td className="py-3">
                    <span
                      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${
                        trace.status === 'completed'
                          ? 'bg-green-400/10 text-green-400'
                          : trace.status === 'failed'
                          ? 'bg-red-400/10 text-red-400'
                          : trace.status === 'running'
                          ? 'bg-amber-400/10 text-amber-400'
                          : 'bg-surface-highest text-secondaryText'
                      }`}
                    >
                      {trace.status === 'completed' && <CheckCircle className="w-3 h-3" />}
                      {trace.status === 'failed' && <XCircle className="w-3 h-3" />}
                      {trace.status === 'running' && <Activity className="w-3 h-3" />}
                      {trace.status}
                    </span>
                  </td>
                  <td className="py-3 text-secondaryText">{trace.duration}s</td>
                  <td className="py-3 text-secondaryText">
                    {trace.created_at ? new Date(trace.created_at).toLocaleString() : '-'}
                  </td>
                  <td className="py-3 text-right">
                    <motion.button
                      onClick={() => openTrace(trace.trace_id)}
                      whileTap={{ scale: 0.95 }}
                      whileHover={{ x: 2 }}
                      className="inline-flex items-center gap-1 text-xs text-primary hover:text-primary-container transition-colors"
                    >
                      View <ChevronRight className="w-3 h-3" />
                    </motion.button>
                  </td>
                </motion.tr>
              ))}
            </tbody>
          </table>
        </div>
        {traceTotal > 10 && (
          <div className="flex justify-between items-center mt-4 text-xs text-secondaryText">
            <span>
              Showing {(tracePage - 1) * 10 + 1}-{Math.min(tracePage * 10, traceTotal)} of{' '}
              {traceTotal}
            </span>
            <div className="flex gap-2">
              <motion.button
                onClick={() => setTracePage((p) => Math.max(1, p - 1))}
                disabled={tracePage === 1}
                whileTap={{ scale: 0.95 }}
                className="px-3 py-1 rounded-lg bg-surface-high border border-outline/20 disabled:opacity-40 hover:bg-surface-highest transition-colors"
              >
                Previous
              </motion.button>
              <motion.button
                onClick={() => setTracePage((p) => (p * 10 < traceTotal ? p + 1 : p))}
                disabled={tracePage * 10 >= traceTotal}
                whileTap={{ scale: 0.95 }}
                className="px-3 py-1 rounded-lg bg-surface-high border border-outline/20 disabled:opacity-40 hover:bg-surface-highest transition-colors"
              >
                Next
              </motion.button>
            </div>
          </div>
        )}
      </div>

      {/* Recent Errors */}
      <div className="bg-surface-low border border-outline/20 rounded-xl p-6">
        <h3 className="text-sm font-semibold text-secondaryText mb-4 flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 text-red-400" />
          Recent Errors
        </h3>
        {metrics?.recent_errors && metrics.recent_errors.length > 0 ? (
          <div className="space-y-3">
            {metrics.recent_errors.map((err, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: i * 0.05 }}
                className="flex items-start gap-3 p-3 rounded-lg bg-surface-high/50 border border-red-400/10"
              >
                <XCircle className="w-4 h-4 text-red-400 mt-0.5 shrink-0" />
                <div className="min-w-0">
                  <div className="text-xs text-secondaryText mb-1">
                    Task {(err.task_id || '').slice(0, 8)}... ·{' '}
                    {err.created_at ? new Date(err.created_at).toLocaleString() : '-'}
                  </div>
                  <div className="text-sm text-primaryText truncate">{err.error}</div>
                </div>
              </motion.div>
            ))}
          </div>
        ) : (
          <div className="text-sm text-secondaryText py-4">No recent errors.</div>
        )}
      </div>

      {/* Trace Detail Modal */}
      <AnimatePresence>
        {selectedTrace && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm"
            onClick={() => setSelectedTrace(null)}
          >
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 20 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 20 }}
              onClick={(e) => e.stopPropagation()}
              className="bg-surface-low border border-outline/20 rounded-xl w-full max-w-3xl max-h-[80vh] overflow-y-auto shadow-2xl"
            >
              <div className="sticky top-0 bg-surface-low/95 backdrop-blur border-b border-outline/20 px-6 py-4 flex justify-between items-center">
                <div>
                  <h2 className="text-lg font-semibold text-primaryText">Trace Detail</h2>
                  <p className="text-xs text-secondaryText font-mono mt-0.5">
                    {selectedTrace.trace_id}
                  </p>
                </div>
                <motion.button
                  onClick={() => setSelectedTrace(null)}
                  whileTap={{ scale: 0.85 }}
                  whileHover={{ scale: 1.1, rotate: 90 }}
                  className="p-1.5 rounded-lg hover:bg-surface-high transition-colors"
                >
                  <X className="w-5 h-5 text-secondaryText" />
                </motion.button>
              </div>

              <div className="p-6 space-y-4">
                <div className="flex gap-4 text-sm flex-wrap">
                  <div className="bg-surface-high rounded-lg px-3 py-2 border border-outline/10">
                    <span className="text-secondaryText">Task:</span>{' '}
                    <span className="font-mono text-primaryText">
                      {(selectedTrace.task_id || '').slice(0, 12)}...
                    </span>
                  </div>
                  <div className="bg-surface-high rounded-lg px-3 py-2 border border-outline/10">
                    <span className="text-secondaryText">Status:</span>{' '}
                    <span
                      className={`font-medium ${
                        selectedTrace.status === 'completed'
                          ? 'text-green-400'
                          : selectedTrace.status === 'failed'
                          ? 'text-red-400'
                          : 'text-amber-400'
                      }`}
                    >
                      {selectedTrace.status}
                    </span>
                  </div>
                </div>

                <div className="space-y-3">
                  <h3 className="text-sm font-semibold text-secondaryText">Timeline</h3>
                  {selectedTrace.spans.map((span, idx) => (
                    <motion.div
                      key={span.span_id}
                      initial={{ opacity: 0, x: -10 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: idx * 0.05 }}
                      className={`relative pl-6 pb-4 ${
                        idx < selectedTrace.spans.length - 1 ? 'border-l border-outline/20' : ''
                      }`}
                    >
                      <div
                        className={`absolute left-0 top-0 w-3 h-3 rounded-full -translate-x-1.5 ring-4 ring-surface-low ${
                          span.status === 'success' || span.status === 'completed'
                            ? 'bg-green-400'
                            : span.status === 'error' || span.status === 'failed'
                            ? 'bg-red-400'
                            : 'bg-amber-400'
                        }`}
                      />
                      <div className="bg-surface-high rounded-lg p-4 border border-outline/10">
                        <div className="flex justify-between items-start mb-2">
                          <div>
                            <div className="text-sm font-medium text-primaryText">
                              {span.operation}
                            </div>
                            <div className="text-xs text-secondaryText mt-0.5">
                              Agent: {span.agent_name}
                            </div>
                          </div>
                          {span.duration !== null && (
                            <div className="text-xs text-secondaryText bg-surface-low px-2 py-1 rounded">
                              {span.duration}s
                            </div>
                          )}
                        </div>
                        {span.error && (
                          <div className="text-xs text-red-400 bg-red-400/5 border border-red-400/10 rounded p-2 mt-2">
                            {span.error}
                          </div>
                        )}
                      </div>
                    </motion.div>
                  ))}
                  {selectedTrace.spans.length === 0 && (
                    <div className="text-sm text-secondaryText">No spans recorded for this trace.</div>
                  )}
                </div>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
};

export default Monitor;

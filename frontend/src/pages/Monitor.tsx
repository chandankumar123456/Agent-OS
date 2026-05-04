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
import { cardInteractions, buttonTap } from '../lib/animations';

const CHART_COLORS = ['#B388FF', '#4ECDC4', '#FFE66D', '#FF80AB', '#FF6B00'];

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
   color: 'text-accent-purple',
   bg: 'bg-accent-purple/10',
  },
  {
   label: 'Success Rate',
   value:
    metrics.total_tasks > 0
     ? `${((metrics.completed_tasks / metrics.total_tasks) * 100).toFixed(1)}%`
     : '0%',
   icon: CheckCircle,
   color: 'text-secondary',
   bg: 'bg-secondary/10',
  },
  {
   label: 'Avg Duration',
   value: `${metrics.avg_task_duration.toFixed(1)}s`,
   icon: Clock,
   color: 'text-accent-yellow',
   bg: 'bg-accent-yellow/10',
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
  <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex flex-col gap-10">
  {/* Header */}
  <div className="flex justify-between items-end">
   <div>
    <h1 className="text-4xl font-pixel uppercase tracking-tight mb-2">Analytics Console</h1>
    <p className="text-secondaryText text-xl font-retro uppercase opacity-60">
     System metrics and execution trace telemetry.
    </p>
   </div>
  </div>

  {/* KPI Cards */}
  <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
   {kpiCards.map((stat, i) => (
    <motion.div
     key={i}
     initial={{ opacity: 0, scale: 0.95 }}
     animate={{ opacity: 1, scale: 1 }}
     {...cardInteractions}
     className="pixel-card p-6 flex flex-col justify-between"
    >
     <div className="flex justify-between items-start mb-6">
      <span className="text-[10px] font-pixel uppercase tracking-tighter text-secondaryText">{stat.label}</span>
      <div className={`w-10 h-10 border-4 border-outline ${stat.bg} flex items-center justify-center shadow-pixel`}>
       <stat.icon className={`w-5 h-5 ${stat.color}`} />
      </div>
     </div>
     <div className="text-4xl font-retro uppercase tracking-tighter text-primaryText">{stat.value}</div>
    </motion.div>
   ))}
  </div>

  {/* Charts Row */}
  <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
   {/* Tasks Over Time */}
   <motion.div {...cardInteractions}>
    <div className="pixel-panel p-6 h-full">
     <h3 className="text-[10px] font-pixel uppercase tracking-tighter text-secondaryText mb-6 flex items-center gap-3">
      <Activity className="w-5 h-5 text-accent-mint" />
      Tasks_History_7D
     </h3>
     <div className="w-full h-64 min-w-0" style={{ minHeight: '256px' }}>
      <ResponsiveContainer width="100%" height="100%">
       <LineChart data={metrics?.tasks_over_time || []}>
        <CartesianGrid strokeDasharray="0" stroke="#000000" opacity={0.1} />
        <XAxis
         dataKey="date"
         tick={{ fill: '#000000', fontSize: 10, fontFamily: 'VT323' }}
         tickFormatter={(value: string) => (value || '').slice(5)}
         axisLine={{ stroke: '#000000', strokeWidth: 4 }}
        />
        <YAxis
         tick={{ fill: '#000000', fontSize: 10, fontFamily: 'VT323' }}
         axisLine={{ stroke: '#000000', strokeWidth: 4 }}
         allowDecimals={false}
        />
        <Tooltip
         contentStyle={{
          backgroundColor: '#FFFFFF',
          border: '4px solid #000000',
          borderRadius: '0',
          fontFamily: 'VT323',
          fontSize: '14px',
          textTransform: 'uppercase',
          boxShadow: '4px 4px 0px 0px #000000',
         }}
        />
        <Line
         type="stepAfter"
         dataKey="count"
         stroke="#FF6B00"
         strokeWidth={4}
         dot={{ fill: '#FF6B00', r: 4, strokeWidth: 4, stroke: '#000000' }}
         activeDot={{ r: 6, strokeWidth: 4, stroke: '#000000' }}
        />
       </LineChart>
      </ResponsiveContainer>
     </div>
    </div>
   </motion.div>

   {/* Tasks by Status */}
   <motion.div {...cardInteractions}>
    <div className="pixel-panel p-6 h-full">
     <h3 className="text-[10px] font-pixel uppercase tracking-tighter text-secondaryText mb-6 flex items-center gap-3">
      <BarChart3 className="w-5 h-5 text-secondary" />
      Status_Distribution
     </h3>
     <div className="w-full h-64 min-w-0" style={{ minHeight: '256px' }}>
      <ResponsiveContainer width="100%" height="100%">
       <BarChart data={metrics?.tasks_by_status || []}>
        <CartesianGrid strokeDasharray="0" stroke="#000000" opacity={0.1} />
        <XAxis
         dataKey="status"
         tick={{ fill: '#000000', fontSize: 10, fontFamily: 'VT323' }}
         axisLine={{ stroke: '#000000', strokeWidth: 4 }}
        />
        <YAxis
         tick={{ fill: '#000000', fontSize: 10, fontFamily: 'VT323' }}
         axisLine={{ stroke: '#000000', strokeWidth: 4 }}
         allowDecimals={false}
        />
        <Tooltip
         contentStyle={{
          backgroundColor: '#FFFFFF',
          border: '4px solid #000000',
          borderRadius: '0',
          fontFamily: 'VT323',
          fontSize: '14px',
          textTransform: 'uppercase',
          boxShadow: '4px 4px 0px 0px #000000',
         }}
        />
        <Bar dataKey="count" radius={0}>
         {(metrics?.tasks_by_status || []).map((_entry, index) => (
          <Cell key={`cell-${index}`} fill={CHART_COLORS[index % CHART_COLORS.length]} stroke="#000000" strokeWidth={4} />
         ))}
        </Bar>
       </BarChart>
      </ResponsiveContainer>
     </div>
    </div>
   </motion.div>

   {/* Top Agents */}
   <motion.div {...cardInteractions}>
    <div className="pixel-panel p-6 h-full">
     <h3 className="text-[10px] font-pixel uppercase tracking-tighter text-secondaryText mb-6 flex items-center gap-3">
      <Layers className="w-5 h-5 text-accent-yellow" />
      Agent_Load_Factor
     </h3>
     <div className="w-full h-64 min-w-0" style={{ minHeight: '256px' }}>
      <ResponsiveContainer width="100%" height="100%">
       <PieChart>
        <Pie
         data={metrics?.top_agents || []}
         cx="50%"
         cy="45%"
         innerRadius={40}
         outerRadius={60}
         paddingAngle={0}
         dataKey="count"
         nameKey="agent_name"
         stroke="#000000"
         strokeWidth={4}
        >
         {(metrics?.top_agents || []).map((_entry, index) => (
          <Cell key={`cell-${index}`} fill={CHART_COLORS[index % CHART_COLORS.length]} />
         ))}
        </Pie>
        <Tooltip
         contentStyle={{
          backgroundColor: '#FFFFFF',
          border: '4px solid #000000',
          borderRadius: '0',
          fontFamily: 'VT323',
          fontSize: '14px',
          textTransform: 'uppercase',
          boxShadow: '4px 4px 0px 0px #000000',
         }}
        />
       </PieChart>
      </ResponsiveContainer>
      <div className="flex flex-wrap gap-4 justify-center mt-4">
       {(metrics?.top_agents || []).map((entry, index) => (
        <div key={entry.agent_name} className="flex items-center gap-2 text-[10px] font-pixel text-black uppercase">
         <div
          className="w-4 h-4 border-4 border-outline"
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
  <div className="pixel-panel p-8">
   <h3 className="text-[10px] font-pixel uppercase tracking-tighter text-secondaryText mb-6 flex items-center gap-3">
    <Eye className="w-5 h-5 text-primary" />
    Execution_Trace_Logs
   </h3>
   <div className="overflow-x-auto">
    <table className="w-full text-left">
     <thead>
      <tr className="border-b-4 border-outline text-[10px] font-pixel uppercase text-secondaryText">
       <th className="pb-4 font-normal">Trace_UID</th>
       <th className="pb-4 font-normal">Parent_Task</th>
       <th className="pb-4 font-normal">Status</th>
       <th className="pb-4 font-normal">Delta_T</th>
       <th className="pb-4 font-normal">Timestamp</th>
       <th className="pb-4 font-normal text-right">Link</th>
      </tr>
     </thead>
     <tbody className="text-lg font-retro uppercase text-primaryText">
      {traces.map((trace, idx) => (
       <motion.tr
        key={trace.trace_id}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: idx * 0.03 }}
        className="border-b-4 border-outline/5 hover:bg-surface-high cursor-pointer group"
        onClick={() => openTrace(trace.trace_id)}
       >
        <td className="py-4 font-mono text-sm opacity-50">{(trace.trace_id || '').slice(0, 12)}</td>
        <td className="py-4 font-mono text-sm opacity-50">{(trace.task_id || '').slice(0, 12)}</td>
        <td className="py-4">
         <span
          className={`inline-flex items-center gap-2 px-4 py-1 border-4 border-outline text-[10px] font-pixel ${
           trace.status === 'completed'
            ? 'bg-secondary text-black'
            : trace.status === 'failed'
            ? 'bg-[#FF4B4B] text-white'
            : trace.status === 'running'
            ? 'bg-accent-yellow text-black'
            : 'bg-white text-black'
          }`}
         >
          {trace.status}
         </span>
        </td>
        <td className="py-4 text-secondaryText">{trace.duration}S</td>
        <td className="py-4 text-secondaryText">
         {trace.created_at ? new Date(trace.created_at).toLocaleString() : '-'}
        </td>
        <td className="py-4 text-right">
         <div className="inline-flex items-center gap-2 text-[10px] font-pixel text-primary underline group-hover:no-underline">
          [ ACCESS ]
         </div>
        </td>
       </motion.tr>
      ))}
     </tbody>
    </table>
   </div>
   {traceTotal > 10 && (
    <div className="flex justify-between items-center mt-8 text-[10px] font-pixel uppercase text-secondaryText">
     <span>
      Recs {(tracePage - 1) * 10 + 1}-{Math.min(tracePage * 10, traceTotal)} // Total {traceTotal}
     </span>
     <div className="flex gap-4">
      <button
       onClick={(e) => { e.stopPropagation(); setTracePage((p) => Math.max(1, p - 1)); }}
       disabled={tracePage === 1}
       className="btn-secondary py-2 px-4 disabled:opacity-40"
      >
       PREV
      </button>
      <button
       onClick={(e) => { e.stopPropagation(); setTracePage((p) => (p * 10 < traceTotal ? p + 1 : p)); }}
       disabled={tracePage * 10 >= traceTotal}
       className="btn-secondary py-2 px-4 disabled:opacity-40"
      >
       NEXT
      </button>
     </div>
    </div>
   )}
  </div>

  {/* Recent Errors */}
  <div className="pixel-panel p-8 border-[#FF4B4B]/20">
   <h3 className="text-[10px] font-pixel uppercase tracking-tighter text-[#FF4B4B] mb-6 flex items-center gap-3">
    <AlertTriangle className="w-5 h-5" />
    Critical_System_Exceptions
   </h3>
   {metrics?.recent_errors && metrics.recent_errors.length > 0 ? (
    <div className="space-y-4">
     {metrics.recent_errors.map((err, i) => (
      <motion.div
       key={i}
       initial={{ opacity: 0, x: -10 }}
       animate={{ opacity: 1, x: 0 }}
       transition={{ delay: i * 0.05 }}
       className="flex items-start gap-4 p-4 border-4 border-[#FF4B4B]/10 bg-[#FF4B4B]/5"
      >
       <XCircle className="w-5 h-5 text-[#FF4B4B] shrink-0" />
       <div className="min-w-0">
        <div className="text-[10px] font-pixel uppercase text-secondaryText mb-2">
         Unit {(err.task_id || '').slice(0, 12)} // {err.created_at ? new Date(err.created_at).toLocaleString() : '-'}
        </div>
        <div className="text-lg font-retro uppercase text-primaryText break-all">{err.error}</div>
       </div>
      </motion.div>
     ))}
    </div>
   ) : (
    <div className="font-retro text-lg text-secondaryText py-4 uppercase opacity-50">No exceptional states recorded.</div>
   )}
  </div>

  {/* Trace Detail Modal */}
  <AnimatePresence>
   {selectedTrace && (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
     <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="absolute inset-0 bg-black/80"
      onClick={() => setSelectedTrace(null)}
     />
     <motion.div
      initial={{ opacity: 0, scale: 0.95, y: 20 }}
      animate={{ opacity: 1, scale: 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.95, y: 20 }}
      className="pixel-panel bg-white w-full max-w-3xl max-h-[80vh] overflow-hidden flex flex-col shadow-pixel-lg"
     >
      <div className="bg-primary px-6 py-4 flex justify-between items-center border-b-4 border-outline">
       <div>
        <h2 className="text-xl font-pixel text-white uppercase leading-none">Trace Detail</h2>
        <p className="text-xs text-white/70 font-retro mt-2 uppercase">
         ID: {selectedTrace.trace_id}
        </p>
       </div>
       <motion.button
        onClick={() => setSelectedTrace(null)}
        {...buttonTap}
        className="p-2 bg-white border-4 border-outline hover:bg-accent-yellow"
       >
        <X className="w-6 h-6 text-black" />
       </motion.button>
      </div>

      <div className="p-8 overflow-y-auto space-y-8 bg-background">
       <div className="flex gap-4 text-sm flex-wrap">
        <div className="pixel-panel px-4 py-2 bg-white">
         <span className="text-[10px] font-pixel uppercase text-secondaryText">Task:</span>{' '}
         <span className="font-retro text-xl uppercase">
          {(selectedTrace.task_id || '').slice(0, 12)}...
         </span>
        </div>
        <div className="pixel-panel px-4 py-2 bg-white">
         <span className="text-[10px] font-pixel uppercase text-secondaryText">Status:</span>{' '}
         <span
          className={`font-pixel text-[10px] uppercase ${
           selectedTrace.status === 'completed'
            ? 'text-secondary'
            : selectedTrace.status === 'failed'
            ? 'text-[#FF4B4B]'
            : 'text-accent-yellow'
          }`}
         >
          {selectedTrace.status}
         </span>
        </div>
       </div>

       <div className="space-y-6">
        <h3 className="text-[10px] font-pixel uppercase text-secondaryText flex items-center gap-2">
         <div className="w-2 h-2 bg-primary" /> Timeline_Sequence
        </h3>
        {selectedTrace.spans.map((span, idx) => (
         <motion.div
          key={span.span_id}
          initial={{ opacity: 0, x: -10 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: idx * 0.05 }}
          className={`relative pl-10 pb-8 ${
           idx < selectedTrace.spans.length - 1 ? 'border-l-4 border-outline/10' : ''
          }`}
         >
          <div
           className={`absolute left-0 top-0 w-6 h-6 border-4 border-outline -translate-x-[14px] ${
            span.status === 'success' || span.status === 'completed'
             ? 'bg-secondary'
             : span.status === 'error' || span.status === 'failed'
             ? 'bg-[#FF4B4B]'
             : 'bg-accent-yellow'
           }`}
          />
          <div className="pixel-card bg-white">
           <div className="flex justify-between items-start mb-4">
            <div>
             <div className="text-xl font-retro uppercase text-black">
              {span.operation}
             </div>
             <div className="text-[10px] font-pixel uppercase text-secondaryText mt-2">
              Operator: {span.agent_name}
             </div>
            </div>
            {span.duration !== null && (
             <div className="text-[10px] font-pixel uppercase bg-background px-2 py-1 border-4 border-outline">
              {span.duration}S
             </div>
            )}
           </div>
           {span.error && (
            <div className="text-lg font-retro uppercase text-[#FF4B4B] bg-[#FF4B4B]/5 border-4 border-[#FF4B4B]/20 p-4 mt-4">
             {span.error}
            </div>
           )}
          </div>
         </motion.div>
        ))}
       </div>
      </div>
     </motion.div>
    </div>
   )}
  </AnimatePresence>
  </motion.div>
 );
};

export default Monitor;

import React, { useEffect, useState, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { 
  Play, 
  Square, 
  Activity, 
  Terminal, 
  Zap, 
  Clock, 
  AlertCircle, 
  ChevronRight,
  Loader2,
  Trash2
} from 'lucide-react';
import { apiClient, type Task, type DashboardMetrics } from '../api/client';
import { buttonTap, cardInteractions, staggerContainer, staggerItem } from '../lib/animations';
import QuickStartPanel from '../components/QuickStartPanel';
import { StatusBadge } from '../components/ui/StatusBadge';
import { SkeletonStatsGrid, SkeletonTaskItem } from '../components/ui/Skeleton';

const Dashboard = () => {
  const [query, setQuery] = useState('');
  const [mode, setMode] = useState<'task' | 'workflow' | 'autonomous' | 'collaboration'>('task');
  const [tasks, setTasks] = useState<Task[]>([]);
  const [metrics, setMetrics] = useState<DashboardMetrics | null>(null);
  const [currentTask, setCurrentTask] = useState<Task | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isLoadingTasks, setIsLoadingTasks] = useState(true);
  const [loadError, setLoadError] = useState('');
  
  // Real-time status via WebSocket or polling
  const [wsStatus, setWsStatus] = useState<'connecting' | 'open' | 'closed'>('closed');
  const [wsTaskId, setWsTaskId] = useState<string | null>(null);

  const initialLoadRef = useRef(false);

  const loadTasks = async () => {
    try {
      const allTasks = await apiClient.listTasks(10);
      setTasks(allTasks);
    } catch (err) {
      console.error('Failed to load tasks:', err);
    }
  };

  const loadMetrics = async () => {
    try {
      const data = await apiClient.getDashboardMetrics();
      setMetrics(data);
    } catch (err) {
      console.error('Failed to load metrics:', err);
    }
  };

  const loadDashboardData = async () => {
    setIsLoadingTasks(true);
    setLoadError('');
    try {
      await Promise.all([loadTasks(), loadMetrics()]);
    } catch (err) {
      setLoadError('Failed to synchronize with kernel.');
    } finally {
      setIsLoadingTasks(false);
    }
  };

  useEffect(() => {
    if (initialLoadRef.current) return;
    initialLoadRef.current = true;
    loadDashboardData();

    // Poll for updates every 10 seconds
    const interval = setInterval(loadDashboardData, 10000);
    return () => clearInterval(interval);
  }, []);

  const handleExecuteTask = async (customQuery?: string) => {
    const taskQuery = customQuery || query;
    if (!taskQuery.trim()) return;

    setIsSubmitting(true);
    setLoadError('');
    try {
      const response = await apiClient.createTask({
        query: taskQuery,
        mode,
        config: {},
      });
      
      const newTask = await apiClient.getTask(response.task_id);
      setCurrentTask(newTask);
      setQuery('');

      // Start polling for this specific task
      apiClient.pollTaskStatus(response.task_id, (updatedTask) => {
        setCurrentTask(updatedTask);
        if (updatedTask.status === 'completed' || updatedTask.status === 'failed') {
          loadDashboardData();
        }
      });

    } catch (err) {
      setLoadError(err instanceof Error ? err.message : 'Execution failed.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDeleteTask = async (taskId: string) => {
    try {
      await apiClient.deleteTask(taskId);
      setTasks(prev => prev.filter(t => t.task_id !== taskId));
      loadMetrics();
    } catch (err) {
      console.error('Failed to delete task:', err);
    }
  };

  const kpis = [
    { label: 'Active_Nodes', value: metrics?.total_tasks || 0, icon: Activity, color: 'text-accent-purple' },
    { label: 'Sync_Success', value: metrics ? `${((metrics.completed_tasks / (metrics.total_tasks || 1)) * 100).toFixed(0)}%` : '0%', icon: Zap, color: 'text-secondary' },
    { label: 'Mean_Delta', value: metrics ? `${metrics.avg_task_duration.toFixed(1)}s` : '0s', icon: Clock, color: 'text-accent-yellow' },
    { label: 'Kernel_Load', value: 'NOMINAL', icon: Terminal, color: 'text-primary' },
  ];

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex flex-col gap-10 max-w-[1600px] mx-auto pb-10">
      {/* System Status Banner */}
      {loadError && (
        <motion.div 
          initial={{ y: -20, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          className="p-6 border-4 border-[#FF4B4B] bg-[#FF4B4B]/10 font-retro text-2xl text-[#FF4B4B] uppercase flex items-center gap-4"
        >
          <AlertCircle className="w-8 h-8" />
          !! CRITICAL_ERROR: {loadError}
        </motion.div>
      )}

      <div className="flex justify-between items-end">
        <div>
          <h1 className="text-4xl font-pixel uppercase tracking-tight mb-2">Command Center</h1>
          <p className="text-xl font-retro uppercase text-secondaryText opacity-60">Primary interface for neural orchestration and task dispatch.</p>
        </div>
      </div>

      {/* KPI Grid */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
        {isLoadingTasks && !metrics ? (
          <SkeletonStatsGrid />
        ) : (
          kpis.map((kpi, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.05 }}
              {...cardInteractions}
              className="pixel-card bg-white p-6 flex flex-col gap-4"
            >
              <div className="flex justify-between items-start">
                <span className="text-[10px] font-pixel text-secondaryText uppercase tracking-tighter">{kpi.label}</span>
                <kpi.icon className={`w-6 h-6 ${kpi.color}`} />
              </div>
              <div className="text-4xl font-retro text-black uppercase">{kpi.value}</div>
            </motion.div>
          ))
        )}
      </div>

      <div className="flex flex-col lg:flex-row gap-10">
        <div className="flex-1 flex flex-col gap-10">
          {/* Execution Input */}
          <div className="pixel-panel p-8 bg-white">
            <h2 className="text-[10px] font-pixel uppercase tracking-tight mb-8 flex items-center gap-3">
              <Terminal className="w-5 h-5 text-primary" /> Task_Execution_Buffer
            </h2>
            <form onSubmit={(e) => { e.preventDefault(); handleExecuteTask(); }} className="space-y-8">
              <div className="relative">
                <textarea
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="ENTER COMMAND OR DIRECTIVE..."
                  className="w-full pixel-input min-h-[160px] py-6 text-2xl resize-none uppercase"
                />
              </div>
              <div className="flex flex-wrap items-center justify-between gap-6">
                <div className="flex items-center gap-6">
                  <label className="text-[10px] font-pixel uppercase text-secondaryText">Kernel_Mode:</label>
                  <select 
                    value={mode}
                    onChange={(e) => setMode(e.target.value as any)}
                    className="pixel-input py-3 text-lg font-pixel uppercase pr-10 cursor-pointer"
                  >
                    <option value="task">TASK</option>
                    <option value="workflow">WORKFLOW</option>
                    <option value="autonomous">AUTONOMOUS</option>
                    <option value="collaboration">COLLAB</option>
                  </select>
                </div>
                <motion.button
                  type="submit"
                  disabled={isSubmitting || !query.trim()}
                  {...buttonTap}
                  className="btn-primary flex items-center gap-4 py-4 px-10 disabled:opacity-50"
                >
                  {isSubmitting ? <Loader2 className="w-6 h-6 animate-spin" /> : <Play className="w-6 h-6" />}
                  {isSubmitting ? '[ EXECUTING... ]' : '[ INITIALIZE_TASK ]'}
                </motion.button>
              </div>
            </form>

            {/* Current Active Task */}
            <AnimatePresence>
              {currentTask && (
                <motion.div
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: 'auto', opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  className="mt-10 pt-10 border-t-4 border-outline/10"
                >
                  <div className="pixel-card bg-background/50">
                    <div className="flex justify-between items-start mb-6">
                      <div className="flex flex-col gap-2">
                        <span className="text-[10px] font-pixel text-secondaryText uppercase">ACTIVE_UNIT_ID</span>
                        <span className="text-xl font-retro text-primary uppercase">{currentTask.task_id}</span>
                      </div>
                      <StatusBadge status={currentTask.status} />
                    </div>
                    {currentTask.status === 'running' && (
                      <div className="w-full h-4 border-4 border-outline bg-white mb-6 overflow-hidden">
                        <motion.div 
                          className="h-full bg-primary"
                          animate={{ x: ['-100%', '100%'] }}
                          transition={{ repeat: Infinity, duration: 1.5, ease: 'linear' }}
                        />
                      </div>
                    )}
                    <div className="p-6 border-4 border-outline bg-white">
                      <p className="text-2xl font-retro text-black uppercase leading-tight">{currentTask.query}</p>
                    </div>
                    {currentTask.status === 'running' && (
                      <motion.button
                        onClick={async () => {
                          try {
                            await apiClient.deleteTask(currentTask.task_id);
                            setCurrentTask(prev => prev ? {...prev, status: 'cancelled'} : prev);
                          } catch (e) { console.error(e); }
                        }}
                        {...buttonTap}
                        className="mt-6 btn-danger py-3 w-full"
                      >
                        [ TERMINATE_PROCESS ]
                      </motion.button>
                    )}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>

          <QuickStartPanel onExecuteTask={handleExecuteTask} collapsible />
        </div>

        {/* Task Log Sidebar */}
        <div className="w-full lg:w-96 flex flex-col gap-10">
          <div className="pixel-panel flex-1 bg-white flex flex-col overflow-hidden">
            <div className="p-6 border-b-4 border-outline flex justify-between items-center bg-background">
              <h2 className="text-[10px] font-pixel uppercase tracking-tight flex items-center gap-3">
                <Activity className="w-4 h-4 text-secondary" /> Sync_Log
              </h2>
              <motion.button 
                onClick={loadDashboardData} 
                {...buttonTap}
                className="p-2 border-4 border-outline bg-white hover:bg-surface-high"
              >
                <Activity className={`w-4 h-4 ${isLoadingTasks ? 'animate-spin' : ''}`} />
              </motion.button>
            </div>
            
            <div className="flex-1 overflow-y-auto p-6 space-y-6">
              {isLoadingTasks && tasks.length === 0 ? (
                Array.from({ length: 5 }).map((_, i) => <SkeletonTaskItem key={i} />)
              ) : tasks.length === 0 ? (
                <div className="text-center py-20 font-retro text-xl text-secondaryText uppercase opacity-50">
                  NO_LOGS_FOUND.
                </div>
              ) : (
                <motion.div variants={staggerContainer} initial="hidden" animate="visible" className="space-y-4">
                  {tasks.map((task) => (
                    <motion.div 
                      key={task.task_id} 
                      variants={staggerItem}
                      className="pixel-card-small p-4 border-4 border-outline bg-white hover:border-primary group transition-none cursor-pointer"
                    >
                      <div className="flex justify-between items-start mb-3">
                        <div className="flex flex-col gap-1 min-w-0">
                          <span className="text-[8px] font-pixel text-secondaryText uppercase leading-none truncate">{(task.task_id || '').slice(0, 12)}</span>
                          <span className="text-lg font-retro text-black uppercase truncate leading-none">{task.query}</span>
                        </div>
                        <StatusBadge status={task.status} showIcon={false} />
                      </div>
                      <div className="flex justify-between items-center mt-4">
                        <span className="text-[10px] font-retro text-secondaryText uppercase">{new Date(task.created_at).toLocaleTimeString()}</span>
                        <div className="flex gap-2">
                           <motion.button 
                            onClick={(e) => { e.stopPropagation(); handleDeleteTask(task.task_id); }}
                            {...buttonTap}
                            className="p-1 border-4 border-outline bg-white text-[#FF4B4B] hover:bg-[#FF4B4B]/10 opacity-0 group-hover:opacity-100 transition-opacity"
                          >
                            <Trash2 className="w-4 h-4" />
                          </motion.button>
                          <ChevronRight className="w-4 h-4 text-primary group-hover:translate-x-1 transition-transform" />
                        </div>
                      </div>
                    </motion.div>
                  ))}
                </motion.div>
              )}
            </div>
          </div>
        </div>
      </div>
    </motion.div>
  );
};

export default Dashboard;

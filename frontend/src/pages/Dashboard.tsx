import React, { useState, useEffect, useCallback, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Activity, Cpu, Server, AlertCircle, CheckCircle2, Play, Loader2, ChevronRight, Radio, ClipboardList } from 'lucide-react';
import { apiClient } from '../api/client';
import type { Task, CreateTaskRequest, TaskTrace } from '../api/client';
import OnboardingModal from '../components/OnboardingModal';
import QuickStartPanel from '../components/QuickStartPanel';
import EmptyState from '../components/EmptyState';
import { TourProvider, dashboardTourSteps } from '../components/Onboarding';
import { useToast } from '../components/ToastProvider';
import { useWebSocket } from '../hooks/useWebSocket';
import { AnimatedNumber } from '../components/ui/AnimatedNumber';
import { SkeletonTaskItem, Skeleton } from '../components/ui/Skeleton';
import { StatusBadge } from '../components/ui/StatusBadge';
import { cardInteractions } from '../lib/animations';

const Dashboard = () => {
  const [query, setQuery] = useState('');
  const [mode, setMode] = useState<'task' | 'workflow' | 'autonomous' | 'collaboration'>('task');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [currentTask, setCurrentTask] = useState<Task | null>(null);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [showResult, setShowResult] = useState(false);
  const [taskTrace, setTaskTrace] = useState<TaskTrace | null>(null);
  const [loadError, setLoadError] = useState('');
  const [isLoadingTasks, setIsLoadingTasks] = useState(false);
  const [isLoadingTrace, setIsLoadingTrace] = useState(false);
  const [metrics, setMetrics] = useState({
    requests_total: 0,
    errors_total: 0,
    error_rate: 0,
    avg_response_time: 0,
  });
  const [showOnboarding, setShowOnboarding] = useState(false);
  const [showTour, setShowTour] = useState(false);
  const { showToast } = useToast();
  const processedTaskIds = useRef<Set<string>>(new Set());

  const wsTaskId = currentTask?.task_id && (currentTask.status === 'pending' || currentTask.status === 'running')
    ? currentTask.task_id
    : null;

  const { messages, status: wsStatus } = useWebSocket({ taskId: wsTaskId });

  useEffect(() => {
    if (messages.length === 0) return;
    const lastMessage = messages[messages.length - 1];
    if (lastMessage?.type !== 'task.status_changed') return;

    const payload = lastMessage.payload || {};
    const newStatus = payload.status as string;
    const taskId = payload.task_id as string;
    if (!taskId || !newStatus) return;

    setCurrentTask((prev) => {
      if (!prev || prev.task_id !== taskId) return prev;
      return { ...prev, status: newStatus } as Task;
    });

    if (newStatus === 'completed' || newStatus === 'failed' || newStatus === 'cancelled') {
      if (!processedTaskIds.current.has(taskId)) {
        processedTaskIds.current.add(taskId);
        setIsSubmitting(false);
        setShowResult(true);
        showToast(
          newStatus === 'completed' ? 'Task completed successfully' : `Task ${newStatus}`,
          newStatus === 'completed' ? 'success' : 'error'
        );
        apiClient.getTask(taskId)
          .then((task) => {
            setCurrentTask(task);
            setTasks((prev) =>
              prev.some((t) => t.task_id === task.task_id)
                ? prev.map((t) => (t.task_id === task.task_id ? task : t))
                : [task, ...prev]
            );
          })
          .catch(() => {});
        loadTaskTrace(taskId);
      }
    }
  }, [messages, showToast]);

  useEffect(() => {
    const checkOnboarding = async () => {
      try {
        const state = await apiClient.getOnboardingState();
        if (!state.onboarding_complete) {
          setShowOnboarding(true);
        } else {
          const hasSeenTour = localStorage.getItem('tour_dashboard');
          if (!hasSeenTour) {
            setShowTour(true);
          }
        }
      } catch {
        // Fallback to localStorage if API fails
        const hasCompleted = localStorage.getItem('hasCompletedOnboarding');
        if (!hasCompleted || hasCompleted === 'false') {
          setShowOnboarding(true);
        }
      }
    };
    checkOnboarding();
  }, []);

  useEffect(() => {
    const handler = (e: CustomEvent<{ query: string }>) => {
      setQuery(e.detail.query);
      setShowOnboarding(false);
    };
    window.addEventListener('onboarding:set-demo-task', handler as EventListener);
    return () => window.removeEventListener('onboarding:set-demo-task', handler as EventListener);
  }, []);

  const handleExecuteTask = useCallback((taskQuery: string) => {
    setQuery(taskQuery);
    setTimeout(() => {
      const form = document.getElementById('dashboard-task-form') as HTMLFormElement | null;
      if (form) {
        form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
      }
    }, 300);
  }, []);

  const loadMetrics = async () => {
    try {
      const data = await apiClient.getMetrics();
      setMetrics(data);
    } catch (error) {
      console.error('Failed to load metrics:', error);
    }
  };

  const loadDashboardData = async () => {
    setIsLoadingTasks(true);
    setLoadError('');
    try {
      await Promise.all([loadTasks(), loadMetrics()]);
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : 'Failed to load dashboard data');
    } finally {
      setIsLoadingTasks(false);
    }
  };

  const loadTaskTrace = async (taskId: string) => {
    setIsLoadingTrace(true);
    try {
      const trace = await apiClient.getTaskTrace(taskId);
      setTaskTrace(trace);
    } catch (error) {
      console.error('Failed to load task trace:', error);
      setLoadError(error instanceof Error ? error.message : 'Failed to load task trace');
      setTaskTrace(null);
    } finally {
      setIsLoadingTrace(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;

    setIsSubmitting(true);
    setShowResult(false);
    try {
      const request: CreateTaskRequest = {
        query: query.trim(),
        config: { max_steps: 10, timeout: 300 },
        mode: mode
      };
      
      const response = await apiClient.createTask(request);
      apiClient.pollTaskStatus(
        response.task_id,
          (task) => {
            setCurrentTask(task);
            setTasks(prev => prev.some(t => t.task_id === task.task_id) ? prev.map(t => t.task_id === task.task_id ? task : t) : [task, ...prev]);
            if (task.status === 'completed' || task.status === 'failed') {
              setIsSubmitting(false);
              setShowResult(true);
              loadTaskTrace(task.task_id);
            }
          },
          2000,
          150
        ).catch(() => {
        setIsSubmitting(false);
        setLoadError('Task polling timed out');
      });
      
      setQuery('');
    } catch (error) {
      console.error('Failed to create task:', error);
      setLoadError(error instanceof Error ? error.message : 'Failed to create task');
      setIsSubmitting(false);
    }
  };

  const loadTasks = async () => {
    try {
      const allTasks = await apiClient.listTasks();
      if (!Array.isArray(allTasks)) {
        console.error('listTasks did not return an array:', allTasks);
        setTasks([]);
        setLoadError('Unexpected API response format');
        return;
      }
      setTasks(
        [...allTasks].sort((a, b) => {
          const left = a.created_at ? new Date(a.created_at).getTime() : 0;
          const right = b.created_at ? new Date(b.created_at).getTime() : 0;
          return right - left;
        })
      );
    } catch (error) {
      console.error('Failed to load tasks:', error);
      setLoadError(error instanceof Error ? error.message : 'Failed to load tasks');
    }
  };

  React.useEffect(() => {
    loadDashboardData();
  }, []);

  const containerVariants = {
    hidden: { opacity: 0 },
    visible: { 
      opacity: 1,
      transition: { staggerChildren: 0.1 }
    }
  };

  const itemVariants = {
    hidden: { opacity: 0, y: 15 },
    visible: { opacity: 1, y: 0, transition: { duration: 0.4 } }
  };

  const handleOnboardingClose = () => {
    setShowOnboarding(false);
    setShowTour(true);
  };

  return (
    <>
      {showTour && <TourProvider tourId="dashboard" steps={dashboardTourSteps} onComplete={() => setShowTour(false)} />}
      <motion.div 
        variants={containerVariants}
        initial="hidden"
        animate="visible"
        className="flex flex-col gap-8"
      >
      <div className="flex justify-between items-end">
        <div>
          <h1 className="text-3xl font-bold tracking-tight mb-1 cursor-default">System Overview</h1>
          <p className="text-secondaryText text-sm">Real-time telemetry and agent orchestration status.</p>
        </div>
        <div className="flex items-center gap-3 bg-surface-highest px-4 py-2 rounded-lg border border-outline/10 shadow-sm">
          <span className="w-2 h-2 rounded-full bg-[#00FF88] shadow-[0_0_10px_rgba(0,255,136,0.3)] animate-pulse"></span>
          <span className="text-xs font-semibold uppercase tracking-widest text-primaryText">System Nominal</span>
        </div>
      </div>

      {loadError && (
        <div className="p-4 rounded-lg border border-[#FF4B4B]/20 bg-[#FF4B4B]/10 text-sm text-[#FF4B4B]">
          {loadError}
        </div>
      )}

      {/* Task Submission Form */}
      <motion.div variants={itemVariants} className="obsidian-panel border border-outline/10 p-6">
        <h2 className="text-lg font-semibold tracking-tight mb-4">Execute New Task</h2>
        <form id="dashboard-task-form" onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div className="flex gap-4">
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Enter your task query (e.g., 'Find cheapest healthy breakfast ingredients')"
              className="flex-1 bg-surface-highest border border-outline/20 rounded-lg px-4 py-3 text-primaryText placeholder:text-secondaryText/50 focus:outline-none focus:border-primary/50 transition-colors"
              disabled={isSubmitting}
            />
            <select
              value={mode}
              onChange={(e) => setMode(e.target.value as any)}
              disabled={isSubmitting}
              className="bg-surface-highest border border-outline/20 rounded-lg px-4 py-3 text-primaryText focus:outline-none focus:border-primary/50 transition-colors"
            >
              <option value="task">Task</option>
              <option value="workflow">Workflow</option>
              <option value="autonomous">Autonomous</option>
              <option value="collaboration">Collaboration</option>
            </select>
            <motion.button
              type="submit"
              disabled={isSubmitting || !query.trim()}
              whileTap={{ scale: 0.96 }}
              whileHover={{ scale: 1.02 }}
              transition={{ type: 'spring', stiffness: 500, damping: 30 }}
              className="btn-primary flex items-center gap-2 shadow-glow-cyan disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isSubmitting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
              {isSubmitting ? 'Running...' : 'Execute'}
            </motion.button>
          </div>
        </form>
        
        {/* Current Task Status */}
        {currentTask && (
          <div className="mt-4 p-4 bg-surface-highest rounded-lg border border-outline/10">
            <div className="flex justify-between items-center mb-3">
              <div className="flex items-center gap-2">
                <span className="text-xs text-secondaryText font-mono">Task ID:</span>
                <span className="text-xs font-mono text-primary">{currentTask.task_id}</span>
                {currentTask.result?.mode && (
                  <span className="text-xs px-2 py-0.5 rounded bg-primary/10 text-primary font-medium">
                    {currentTask.result.mode}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-2">
                {currentTask.status === 'running' || currentTask.status === 'pending' ? (
                  <motion.button
                    onClick={async () => {
                      try {
                        await apiClient.deleteTask(currentTask.task_id);
                        setCurrentTask(prev => prev ? {...prev, status: 'cancelled'} : prev);
                      } catch (e) {
                        console.error('Failed to cancel task:', e);
                      }
                    }}
                    whileTap={{ scale: 0.95 }}
                    className="text-xs px-2 py-1 rounded bg-[#FF4B4B]/10 text-[#FF4B4B] hover:bg-[#FF4B4B]/20 transition-colors"
                  >
                    Cancel
                  </motion.button>
                ) : null}
                {currentTask.status === 'waiting_approval' ? (
                  <>
                    <motion.button
                      onClick={async () => {
                        try {
                          await apiClient.approveTask(currentTask.task_id);
                          setCurrentTask(prev => prev ? {...prev, status: 'running'} : prev);
                          showToast('Task approved', 'success');
                        } catch (e) {
                          console.error('Failed to approve task:', e);
                          showToast('Approval failed', 'error');
                        }
                      }}
                      whileTap={{ scale: 0.95 }}
                      className="text-xs px-2 py-1 rounded bg-[#00FF88]/10 text-[#00FF88] hover:bg-[#00FF88]/20 transition-colors"
                    >
                      Approve
                    </motion.button>
                    <motion.button
                      onClick={async () => {
                        try {
                          await apiClient.rejectTask(currentTask.task_id);
                          setCurrentTask(prev => prev ? {...prev, status: 'failed'} : prev);
                          showToast('Task rejected', 'success');
                        } catch (e) {
                          console.error('Failed to reject task:', e);
                          showToast('Rejection failed', 'error');
                        }
                      }}
                      whileTap={{ scale: 0.95 }}
                      className="text-xs px-2 py-1 rounded bg-[#FF4B4B]/10 text-[#FF4B4B] hover:bg-[#FF4B4B]/20 transition-colors"
                    >
                      Reject
                    </motion.button>
                  </>
                ) : null}
                {wsTaskId && wsStatus === 'open' && (
                  <span className="flex items-center gap-1 text-xs text-[#00FF88] font-medium">
                    <Radio className="w-3 h-3 animate-pulse" />
                    Live
                  </span>
                )}
                <StatusBadge status={currentTask.status} />
              </div>
            </div>
            
            {/* Result Display */}
            {showResult && currentTask.result && (
              <div className="mt-3 p-4 bg-background rounded-lg border border-outline/10">
                <h4 className="text-sm font-semibold mb-2 text-[#00FF88]">Result:</h4>
                <pre className="text-xs text-secondaryText overflow-x-auto whitespace-pre-wrap max-h-64">
                  {JSON.stringify(currentTask.result, null, 2)}
                </pre>
              </div>
            )}
            
            {showResult && currentTask.error && (
              <div className="mt-3 p-4 bg-[#FF4B4B]/10 rounded-lg border border-[#FF4B4B]/20">
                <h4 className="text-sm font-semibold mb-2 text-[#FF4B4B]">Error:</h4>
                <pre className="text-xs text-secondaryText overflow-x-auto whitespace-pre-wrap">
                  {JSON.stringify(currentTask.error, null, 2)}
                </pre>
              </div>
            )}

            {isLoadingTrace && (
              <div className="mt-3 space-y-2">
                <Skeleton className="h-3 w-3/4" />
                <Skeleton className="h-3 w-1/2" />
              </div>
            )}
            
            {/* Steps Display */}
            {currentTask.steps?.length > 0 && (
              <div className="mt-3">
                <h4 className="text-sm font-semibold mb-2">Workflow Nodes:</h4>
                <motion.div layout className="grid grid-cols-1 md:grid-cols-2 gap-2">
                  {currentTask.steps.map((node, idx) => (
                    <motion.div
                      key={node.id}
                      initial={{ opacity: 0, y: 8 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: idx * 0.05, type: 'spring', stiffness: 400, damping: 30 }}
                      className="flex flex-col gap-2 px-3 py-3 bg-surface-low rounded-lg text-xs border border-outline/10"
                    >
                      <div className="flex items-center justify-between gap-3">
                        <div className="flex items-center gap-2 min-w-0">
                          <ChevronRight className="w-3 h-3 text-primary shrink-0" />
                          <span className="text-secondaryText truncate">{node.id}</span>
                        </div>
                        <span className={`font-bold uppercase ${node.status === 'failed' ? 'text-[#FF4B4B]' : node.status === 'skipped' ? 'text-secondaryText' : 'text-[#00FF88]'}`}>
                          {node.status}
                        </span>
                      </div>
                      <div className="text-secondaryText">
                        <span className="font-medium text-primaryText">Dependency:</span> {node.depends_on?.length > 0 ? node.depends_on.join(', ') : 'None'}
                      </div>
                    </motion.div>
                  ))}
                </motion.div>
              </div>
            )}

            {taskTrace && taskTrace.node_traces?.length > 0 && (
              <div className="mt-4 p-4 bg-background rounded-lg border border-outline/10">
                <h4 className="text-sm font-semibold mb-2">Trace Events</h4>
                <div className="space-y-2">
                  {taskTrace.node_traces.map((trace) => (
                    <div key={trace.id} className="text-xs flex flex-col gap-1">
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-mono text-secondaryText">{trace.node_id}</span>
                        <span className={`font-bold uppercase ${trace.status === 'failed' ? 'text-[#FF4B4B]' : trace.status === 'skipped' ? 'text-secondaryText' : 'text-[#00FF88]'}`}>{trace.status}</span>
                      </div>
                        <div className="text-secondaryText">Input: <span className="text-primaryText">{JSON.stringify(trace.input_data)}</span></div>
                        <div className="text-secondaryText">Output: <span className="text-primaryText">{JSON.stringify(trace.output_data)}</span></div>
                      {trace.error && <div className="text-[#FF4B4B]">{trace.error}</div>}
                    </div>
                  ))}
                </div>
              </div>
            )}
            {taskTrace && taskTrace.spans?.length === 0 && (
              <div className="mt-6 text-sm text-secondaryText">Run a task to see orchestrator spans here.</div>
            )}
            {taskTrace && taskTrace.spans?.length > 0 && (
              <div className="flex-1 overflow-y-auto pr-2 space-y-4">
                  {taskTrace.spans.map((span) => (
                  <div key={span.span_id} className="flex gap-3 text-sm">
                    <span className="text-secondaryText font-mono text-xs mt-0.5">{new Date(span.start_time).toLocaleTimeString()}</span>
                    <div className="flex flex-col gap-0.5">
                      <span className={`font-medium ${span.status === 'failure' ? 'text-[#FF4B4B]' : 'text-[#00FF88]'}`}>
                        [{span.agent_name}]
                      </span>
                      <span className="text-primaryText/90 leading-tight">
                        {span.operation} {span.error ? `- ${span.error}` : ''}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </motion.div>

      {/* Quick Start - Collapsible */}
      <QuickStartPanel onExecuteTask={handleExecuteTask} collapsible />

      {/* Stats Grid */}
      <div id="metrics-panel" className="grid grid-cols-1 md:grid-cols-4 gap-4">
        {[
          { label: 'Active Agents', value: tasks.length > 0 ? String(tasks.filter(t => t.status === 'running').length + 2) : '2', icon: Activity, trend: '+3 this hour' },
          { label: 'Avg Execution Latency', value: `${Math.round(metrics.avg_response_time * 1000)}ms`, icon: Cpu, trend: `${metrics.requests_total} requests total` },
          { label: 'Error Rate', value: `${(metrics.error_rate * 100).toFixed(2)}%`, icon: Server, trend: `${metrics.errors_total} errors total` },
          { label: 'Total Tasks', value: String(tasks.length), icon: AlertCircle, trend: `${tasks.filter(t => t.status === 'completed').length} completed`, highlight: 'text-primary' }
        ].map((stat, i) => (
          <motion.div
            key={i}
            variants={itemVariants}
            {...cardInteractions}
            className="obsidian-panel p-5 border border-outline/5 hover:border-outline/20 hover:shadow-glow-cyan/50 transition-colors cursor-pointer"
          >
            <div className="flex justify-between items-start mb-4">
              <span className="text-secondaryText text-sm font-medium">{stat.label}</span>
              <stat.icon className="w-5 h-5 text-primary opacity-80" />
            </div>
            <div className={`text-3xl font-bold tracking-tight ${stat.highlight || ''}`}>
              {stat.label === 'Avg Execution Latency' ? (
                <AnimatedNumber value={parseInt(stat.value) || 0} suffix="ms" />
              ) : stat.label === 'Error Rate' ? (
                <AnimatedNumber value={parseFloat(stat.value) || 0} suffix="%" decimals={2} />
              ) : stat.label === 'Total Tasks' ? (
                <AnimatedNumber value={parseInt(stat.value) || 0} />
              ) : (
                stat.value
              )}
            </div>
            <div className="text-xs text-secondaryText mt-2">{stat.trend}</div>
          </motion.div>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Active Workflows */}
        <motion.div variants={itemVariants} id="recent-tasks-panel" className="lg:col-span-2 obsidian-panel border border-outline/5 p-6 relative overflow-hidden">
          <div className="flex justify-between items-center mb-6">
            <h2 className="text-lg font-semibold tracking-tight">Recent Tasks</h2>
            <button onClick={loadTasks} className="text-primary text-sm hover:underline">Refresh</button>
          </div>
          
          <div className="flex flex-col gap-3 max-h-80 overflow-y-auto">
            {isLoadingTasks ? (
              <div className="flex flex-col gap-3">
                <SkeletonTaskItem />
                <SkeletonTaskItem />
                <SkeletonTaskItem />
              </div>
            ) : tasks.length === 0 ? (
              <EmptyState
                icon={ClipboardList}
                title="No tasks yet"
                description="Get started by creating your first task using the form above."
                actionLabel="Create Your First Task"
                actionHref="#dashboard-task-form"
              />
            ) : (
              tasks.slice(0, 5).map((task) => (
                <div key={task.task_id} className="flex flex-col gap-2 p-4 bg-surface-highest rounded-lg">
                  <div className="flex justify-between items-center">
                    <div className="flex items-center gap-3">
                        {task.status === 'completed' ? (
                          <CheckCircle2 className="w-4 h-4 text-[#00FF88]" />
                        ) : task.status === 'failed' ? (
                          <AlertCircle className="w-4 h-4 text-[#FF4B4B]" />
                        ) : (
                        <Loader2 className="w-4 h-4 text-primary animate-spin" />
                      )}
                      <span className="font-medium text-sm truncate max-w-xs">{task.task_id || 'unknown'}</span>
                      <span className="text-xs text-secondaryText font-mono bg-background px-2 py-0.5 rounded">{(task.task_id || 'unknown').slice(0, 8)}</span>
                    </div>
                      <StatusBadge status={task.status} />
                  </div>
                  {task.result && (
                    <div className="text-xs text-secondaryText mt-1 truncate">
                      Result: {JSON.stringify(task.result).slice(0, 100)}...
                    </div>
                  )}
                </div>
              ))
            )}
          </div>
        </motion.div>

        {/* Task Trace / Runtime Log */}
        <motion.div variants={itemVariants} className="obsidian-panel border border-outline/5 p-6 flex flex-col h-full">
          <div className="flex justify-between items-center mb-6">
            <h2 className="text-lg font-semibold tracking-tight">Task Trace</h2>
          </div>
          
          <div className="flex-1 overflow-y-auto pr-2 space-y-4">
            {taskTrace ? (
              taskTrace.spans?.length === 0 ? (
                <div className="text-sm text-secondaryText">Run a task to see orchestrator spans here.</div>
              ) : (
                taskTrace.spans.map((span) => (
                  <div key={span.span_id} className="flex gap-3 text-sm">
                    <span className="text-secondaryText font-mono text-xs mt-0.5">{new Date(span.start_time).toLocaleTimeString()}</span>
                    <div className="flex flex-col gap-0.5">
                      <span className={`font-medium ${span.status === 'failure' ? 'text-[#FF4B4B]' : 'text-[#00FF88]'}`}>
                        [{span.agent_name}]
                      </span>
                      <span className="text-primaryText/90 leading-tight">
                        {span.operation} {span.error ? `- ${span.error}` : ''}
                      </span>
                    </div>
                  </div>
                ))
              )
            ) : null}
            {taskTrace && taskTrace.workflow_state && taskTrace.workflow_state.nodes?.length > 0 && (
              <div className="mt-6 pt-4 border-t border-outline/10 space-y-2">
                <h3 className="text-sm font-semibold">Workflow Snapshot</h3>
                {taskTrace.workflow_state.nodes.map((node) => (
                  <div key={node.id} className="flex items-center justify-between text-xs bg-surface-low rounded-md px-3 py-2">
                    <span className="truncate mr-2">{node.agent_type} #{node.step_number}</span>
                    <span className={`font-bold uppercase ${node.status === 'failed' ? 'text-[#FF4B4B]' : node.status === 'skipped' ? 'text-secondaryText' : 'text-[#00FF88]'}`}>{node.status}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </motion.div>
      </div>

      <AnimatePresence>
        {showOnboarding && (
          <OnboardingModal onClose={handleOnboardingClose} />
        )}
      </AnimatePresence>
      </motion.div>
    </>
  );
};

export default Dashboard;

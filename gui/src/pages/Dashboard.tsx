import { useState, useEffect, useRef } from 'react'
import { useApp } from '../context/AppContext'
import { supervisorApi, type Task } from '../api/supervisor'
import { subscribeToSupervisorEvents } from '../api/events'
import { SafetyDialog } from '../components/SafetyDialog'
import { 
  Play, 
  Pause, 
  RotateCcw, 
  X, 
  Terminal,
  Clock,
  CheckCircle,
  XCircle,
  Activity,
  Shield
} from 'lucide-react'

export function Dashboard() {
  const { state, refreshTasks } = useApp()
  const [newTaskQuery, setNewTaskQuery] = useState('')
  const [isCreating, setIsCreating] = useState(false)
  const [approvalTask, setApprovalTask] = useState<Task | null>(null)
  const refreshTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Debounced refresh to avoid multiple rapid calls
  const debouncedRefresh = () => {
    if (refreshTimeoutRef.current) {
      clearTimeout(refreshTimeoutRef.current)
    }
    refreshTimeoutRef.current = setTimeout(() => {
      refreshTasks()
    }, 300)
  }

  useEffect(() => {
    // Initial load
    refreshTasks()

    // Subscribe to Supervisor WebSocket events for real-time updates
    const unlistenPromise = subscribeToSupervisorEvents(() => {
      debouncedRefresh()
    })

    // Fallback polling (30s instead of 5s — events provide real-time updates)
    const interval = setInterval(refreshTasks, 30000)

    return () => {
      clearInterval(interval)
      unlistenPromise.then(unlisten => unlisten())
      if (refreshTimeoutRef.current) {
        clearTimeout(refreshTimeoutRef.current)
      }
    }
  }, [])

  useEffect(() => {
    // Check for tasks awaiting approval
    const pendingApproval = state.tasks.find(t => t.status === 'pending')
    if (pendingApproval && !approvalTask) {
      // Only show dialog for desktop automation tasks that might need approval
      const query = pendingApproval.query.toLowerCase()
      if (query.includes('click') || query.includes('type') || query.includes('screenshot') || query.includes('desktop')) {
        setApprovalTask(pendingApproval)
      }
    }
  }, [state.tasks])

  const handleCreateTask = async () => {
    if (!newTaskQuery.trim()) return
    setIsCreating(true)
    try {
      await supervisorApi.createTask(newTaskQuery)
      setNewTaskQuery('')
      await refreshTasks()
    } catch (error) {
      console.error('Failed to create task:', error)
    } finally {
      setIsCreating(false)
    }
  }

  const handleCancelTask = async (taskId: string) => {
    try {
      await supervisorApi.cancelTask(taskId)
      await refreshTasks()
    } catch (error) {
      console.error('Failed to cancel task:', error)
    }
  }

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'running':
        return <Activity className="w-4 h-4 text-blue-400" />
      case 'completed':
        return <CheckCircle className="w-4 h-4 text-green-400" />
      case 'failed':
        return <XCircle className="w-4 h-4 text-red-400" />
      case 'cancelled':
        return <X className="w-4 h-4 text-gray-400" />
      case 'pending':
        return <Shield className="w-4 h-4 text-yellow-400" />
      default:
        return <Clock className="w-4 h-4 text-yellow-400" />
    }
  }

  const getStatusClass = (status: string) => {
    switch (status) {
      case 'running':
        return 'bg-blue-500/10 border-blue-500/30 text-blue-400'
      case 'completed':
        return 'bg-green-500/10 border-green-500/30 text-green-400'
      case 'failed':
        return 'bg-red-500/10 border-red-500/30 text-red-400'
      case 'cancelled':
        return 'bg-gray-500/10 border-gray-500/30 text-gray-400'
      case 'pending':
        return 'bg-yellow-500/10 border-yellow-500/30 text-yellow-400'
      default:
        return 'bg-yellow-500/10 border-yellow-500/30 text-yellow-400'
    }
  }

  return (
    <div className="h-full flex flex-col">
      {approvalTask && (
        <SafetyDialog
          task={approvalTask}
          onApprove={() => { setApprovalTask(null); refreshTasks() }}
          onReject={() => { setApprovalTask(null); refreshTasks() }}
        />
      )}
      {/* Header with stats */}
      <div className="p-6 border-b border-gray-800">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h2 className="text-2xl font-bold">Dashboard</h2>
            <p className="text-gray-400 mt-1">Manage and monitor your agent tasks</p>
          </div>
          <div className="flex gap-4">
            <div className="bg-agentos-dark px-4 py-2 rounded-lg border border-gray-800">
              <div className="text-2xl font-bold text-blue-400">{state.activeTasks}</div>
              <div className="text-xs text-gray-500">Active</div>
            </div>
            <div className="bg-agentos-dark px-4 py-2 rounded-lg border border-gray-800">
              <div className="text-2xl font-bold text-green-400">{state.completedTasks}</div>
              <div className="text-xs text-gray-500">Completed</div>
            </div>
            <div className="bg-agentos-dark px-4 py-2 rounded-lg border border-gray-800">
              <div className="text-2xl font-bold text-red-400">{state.failedTasks}</div>
              <div className="text-xs text-gray-500">Failed</div>
            </div>
          </div>
        </div>

        {/* Quick task creation */}
        <div className="flex gap-3">
          <input
            type="text"
            value={newTaskQuery}
            onChange={(e) => setNewTaskQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleCreateTask()}
            placeholder="What would you like the agent to do?"
            className="flex-1 bg-agentos-dark border border-gray-700 rounded-lg px-4 py-3 text-white placeholder-gray-500 focus:outline-none focus:border-agentos-primary focus:ring-1 focus:ring-agentos-primary"
          />
          <button
            onClick={handleCreateTask}
            disabled={isCreating || !newTaskQuery.trim()}
            className="bg-agentos-primary hover:bg-blue-600 disabled:bg-gray-700 disabled:cursor-not-allowed text-white px-6 py-3 rounded-lg font-medium flex items-center gap-2 transition-colors"
          >
            {isCreating ? (
              <RotateCcw className="w-5 h-5 animate-spin" />
            ) : (
              <Play className="w-5 h-5" />
            )}
            Run Task
          </button>
        </div>
      </div>

      {/* Task list */}
      <div className="flex-1 overflow-auto p-6">
        {state.tasks.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-gray-500">
            <Terminal className="w-16 h-16 mb-4 opacity-50" />
            <p className="text-lg font-medium">No tasks yet</p>
            <p className="text-sm">Create your first task above</p>
          </div>
        ) : (
          <div className="space-y-3">
            {state.tasks.map((task) => (
              <div
                key={task.id}
                className="bg-agentos-dark border border-gray-800 rounded-lg p-4 hover:border-gray-700 transition-colors"
              >
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-3 mb-2">
                      {getStatusIcon(task.status)}
                      <span className="text-sm text-gray-400 font-mono">{task.id.slice(0, 8)}</span>
                      <span className={`text-xs px-2 py-1 rounded-full border ${getStatusClass(task.status)}`}>
                        {task.status}
                      </span>
                    </div>
                    <p className="text-white font-medium">{task.query}</p>
                    <div className="flex items-center gap-4 mt-2 text-sm text-gray-500">
                      <span>{task.steps.length} steps</span>
                      <span>•</span>
                      <span>{new Date(task.created_at).toLocaleString()}</span>
                    </div>
                  </div>
                  <div className="flex gap-2">
                    {task.status === 'running' && (
                      <button className="p-2 hover:bg-gray-800 rounded-lg transition-colors text-gray-400 hover:text-white">
                        <Pause className="w-4 h-4" />
                      </button>
                    )}
                    <button
                      onClick={() => handleCancelTask(task.id)}
                      className="p-2 hover:bg-gray-800 rounded-lg transition-colors text-gray-400 hover:text-white"
                      title="Cancel task"
                    >
                      <X className="w-4 h-4" />
                    </button>
                  </div>
                </div>

                {/* Step progress */}
                {task.steps.length > 0 && (
                  <div className="mt-4 pt-4 border-t border-gray-800">
                    <div className="flex gap-2">
                      {task.steps.map((step) => (
                        <div
                          key={step.id}
                          className={`flex-1 h-1 rounded-full ${
                            step.status === 'completed'
                              ? 'bg-green-500'
                              : step.status === 'running'
                              ? 'bg-blue-500'
                              : step.status === 'failed'
                              ? 'bg-red-500'
                              : 'bg-gray-700'
                          }`}
                        />
                      ))}
                    </div>
                    <div className="mt-2 text-sm text-gray-400">
                      Step {task.steps.filter(s => s.status === 'completed').length} of {task.steps.length}
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

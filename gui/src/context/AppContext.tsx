import { createContext, useContext, useState, ReactNode } from 'react'
import { supervisorApi, type Task, type TaskStep } from '../api/supervisor'

export type { Task, TaskStep }

interface AppState {
  tasks: Task[]
  selectedTask: Task | null
  activeTasks: number
  completedTasks: number
  failedTasks: number
}

interface AppContextType {
  state: AppState
  setSelectedTask: (task: Task | null) => void
  refreshTasks: () => Promise<void>
}

const defaultState: AppState = {
  tasks: [],
  selectedTask: null,
  activeTasks: 0,
  completedTasks: 0,
  failedTasks: 0,
}

const AppContext = createContext<AppContextType | undefined>(undefined)

export function AppProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AppState>(defaultState)

  const setSelectedTask = (task: Task | null) => {
    setState(prev => ({ ...prev, selectedTask: task }))
  }

  const refreshTasks = async () => {
    try {
      const tasks = await supervisorApi.listTasks()
      const activeTasks = tasks.filter(t => t.status === 'running').length
      const completedTasks = tasks.filter(t => t.status === 'completed').length
      const failedTasks = tasks.filter(t => t.status === 'failed').length
      setState(prev => ({ ...prev, tasks, activeTasks, completedTasks, failedTasks }))
    } catch (error) {
      console.error('Failed to refresh tasks:', error)
      // Fall back to mock data if API is not available (e.g., during development)
      const mockTasks: Task[] = [
        {
          id: 'task-1',
          query: 'Open Chrome and search for rust tutorials',
          status: 'running',
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          steps: [
            { id: 'step-1', index: 0, description: 'Focus Chrome window', status: 'completed' },
            { id: 'step-2', index: 1, description: 'Click on address bar', status: 'running' },
          ],
        },
        {
          id: 'task-2',
          query: 'Create a text file with hello world',
          status: 'completed',
          created_at: new Date(Date.now() - 3600000).toISOString(),
          updated_at: new Date(Date.now() - 3500000).toISOString(),
          steps: [
            { id: 'step-1', index: 0, description: 'Open Notepad', status: 'completed' },
            { id: 'step-2', index: 1, description: 'Type hello world', status: 'completed' },
            { id: 'step-3', index: 2, description: 'Save file', status: 'completed' },
          ],
        },
      ]

      const activeTasks = mockTasks.filter(t => t.status === 'running').length
      const completedTasks = mockTasks.filter(t => t.status === 'completed').length
      const failedTasks = mockTasks.filter(t => t.status === 'failed').length

      setState(prev => ({
        ...prev,
        tasks: mockTasks,
        activeTasks,
        completedTasks,
        failedTasks,
      }))
    }
  }

  return (
    <AppContext.Provider value={{ state, setSelectedTask, refreshTasks }}>
      {children}
    </AppContext.Provider>
  )
}

export function useApp() {
  const context = useContext(AppContext)
  if (!context) {
    throw new Error('useApp must be used within AppProvider')
  }
  return context
}

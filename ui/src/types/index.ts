import { ReactNode } from 'react'

export interface LayoutProps {
  children: ReactNode
  currentPage: string
  onNavigate: (page: string) => void
  daemonConnected: boolean
}

export interface Task {
  id: string
  query: string
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'
  createdAt: string
  updatedAt: string
  steps: TaskStep[]
}

export interface TaskStep {
  id: string
  description: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  result?: string
}

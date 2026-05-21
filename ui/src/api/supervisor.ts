const API_BASE = 'http://127.0.0.1:8080/api/v1'

// API response types (snake_case to match Supervisor REST API)
export interface Task {
  id: string
  query: string
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'
  created_at: string // ISO 8601
  updated_at: string
  completed_at?: string
  steps: TaskStep[]
  result?: string
  error?: string
}

export interface TaskStep {
  id: string
  index: number
  description: string
  status: 'pending' | 'running' | 'completed' | 'failed' | 'skipped'
  result?: string
  started_at?: string
  completed_at?: string
}

interface CreateTaskRequest {
  query: string
}

interface CreateTaskResponse {
  task_id: string
  status: string
}

interface ListTasksResponse {
  tasks: Task[]
  total: number
}

interface CancelTaskRequest {
  reason?: string
}

interface CancelTaskResponse {
  success: boolean
}

class SupervisorAPI {
  private async fetchWithError<T>(url: string, options?: RequestInit): Promise<T> {
    const response = await fetch(url, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...options?.headers,
      },
    })

    if (!response.ok) {
      let errorMessage = `HTTP error! status: ${response.status}`
      try {
        const errorData = await response.json()
        if (errorData.error) {
          errorMessage = errorData.error
        }
      } catch {
        // If parsing fails, use the default error message
      }
      throw new Error(errorMessage)
    }

    return response.json() as Promise<T>
  }

  async createTask(query: string): Promise<{ taskId: string; status: string }> {
    const body: CreateTaskRequest = { query }
    const response = await this.fetchWithError<CreateTaskResponse>(
      `${API_BASE}/tasks`,
      {
        method: 'POST',
        body: JSON.stringify(body),
      }
    )
    return { taskId: response.task_id, status: response.status }
  }

  async listTasks(status?: string, limit?: number, offset?: number): Promise<Task[]> {
    const params = new URLSearchParams()
    if (status) params.append('status', status)
    if (limit !== undefined) params.append('limit', limit.toString())
    if (offset !== undefined) params.append('offset', offset.toString())

    const queryString = params.toString()
    const url = `${API_BASE}/tasks${queryString ? `?${queryString}` : ''}`

    const response = await this.fetchWithError<ListTasksResponse>(url)
    return response.tasks
  }

  async getTask(id: string): Promise<Task> {
    return this.fetchWithError<Task>(`${API_BASE}/tasks/${id}`)
  }

  async cancelTask(id: string, reason?: string): Promise<void> {
    const body: CancelTaskRequest = { reason }
    await this.fetchWithError<CancelTaskResponse>(
      `${API_BASE}/tasks/${id}/cancel`,
      {
        method: 'POST',
        body: JSON.stringify(body),
      }
    )
  }

  async approveTask(id: string, reason?: string): Promise<Task> {
    const body = { reason }
    return this.fetchWithError<Task>(
      `${API_BASE}/tasks/${id}/approve`,
      {
        method: 'POST',
        body: JSON.stringify(body),
      }
    )
  }

  async rejectTask(id: string, reason?: string): Promise<Task> {
    const body = { reason }
    return this.fetchWithError<Task>(
      `${API_BASE}/tasks/${id}/reject`,
      {
        method: 'POST',
        body: JSON.stringify(body),
      }
    )
  }

  // ─── Agent Configuration API ───────────────────────────────

  async listAgentConfigs(): Promise<AgentConfig[]> {
    return this.fetchWithError<AgentConfig[]>(`${API_BASE}/agent-configs`)
  }

  async getAgentConfig(id: string): Promise<AgentConfig> {
    return this.fetchWithError<AgentConfig>(`${API_BASE}/agent-configs/${id}`)
  }

  async createAgentConfig(config: { name: string; description?: string; role?: string }): Promise<AgentConfig> {
    return this.fetchWithError<AgentConfig>(
      `${API_BASE}/agent-configs`,
      {
        method: 'POST',
        body: JSON.stringify(config),
      }
    )
  }

  async updateAgentConfig(id: string, config: Partial<AgentConfig>): Promise<AgentConfig> {
    return this.fetchWithError<AgentConfig>(
      `${API_BASE}/agent-configs/${id}`,
      {
        method: 'PUT',
        body: JSON.stringify(config),
      }
    )
  }

  async deleteAgentConfig(id: string): Promise<void> {
    await this.fetchWithError<{ message: string }>(
      `${API_BASE}/agent-configs/${id}`,
      { method: 'DELETE' }
    )
  }

  // ─── Tool Definitions API ──────────────────────────────────

  async listTools(category?: string): Promise<ToolDef[]> {
    const params = category && category !== 'All' ? `?category=${encodeURIComponent(category)}` : ''
    return this.fetchWithError<ToolDef[]>(`${API_BASE}/tools${params}`)
  }

  async getTool(name: string): Promise<ToolDef> {
    return this.fetchWithError<ToolDef>(`${API_BASE}/tools/${encodeURIComponent(name)}`)
  }

  async listToolCategories(): Promise<string[]> {
    const resp = await this.fetchWithError<{ categories: string[] }>(`${API_BASE}/tools/categories`)
    return resp.categories
  }
}

export interface AgentConfig {
  id: string
  name: string
  description: string
  role: string
  system_prompt?: string
  model?: string
  temperature?: number
  max_tokens?: number
  status: string
  created_at: string
  updated_at: string
}

export interface ToolDef {
  id: string
  name: string
  description: string
  category: string
  type: string
  status: string
  parameters_schema?: string
  created_at: string
  updated_at: string
}

export const supervisorApi = new SupervisorAPI()

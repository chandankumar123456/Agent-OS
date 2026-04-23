const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';

export interface WorkflowState {
  workflow: {
    id: string | null;
    task_id: string | null;
    name: string | null;
    definition: any;
    status: string | null;
  } | null;
  nodes: WorkflowNode[];
  edges: Array<{ id: string; from_node_id: string; to_node_id: string }>;
}

export interface WorkflowNode {
  id: string;
  step_number: number;
  agent_type: string;
  status: string;
  depends_on: number[];
  input_data?: any;
  output_data?: any;
  confidence?: number;
}

export interface Task {
  task_id: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
  result: any;
  steps: WorkflowNode[];
  workflow_state: WorkflowState;
  error: { message: string } | null;
  created_at: string | null;
}

export interface TaskTraceSpan {
  span_id: string;
  operation: string;
  agent_name: string;
  start_time: string;
  end_time?: string | null;
  status: string;
  error?: string | null;
}

export interface TaskTrace {
  trace_id: string;
  task_id: string;
  user_id: string;
  status: string;
  workflow_state: WorkflowState;
  node_traces: Array<{
    id: string;
    task_id: string;
    user_id: string;
    trace_id: string;
    node_id: string;
    status: string;
    input_data: any;
    output_data: any;
    error: string | null;
    started_at: string | null;
    finished_at: string | null;
    created_at: string | null;
    updated_at: string | null;
  }>;
  spans: TaskTraceSpan[];
}

export interface CreateTaskRequest {
  query: string;
  config?: {
    max_steps?: number;
    timeout?: number;
  };
  mode?: 'task' | 'workflow' | 'autonomous' | 'collaboration';
}

export interface CreateTaskResponse {
  task_id: string;
  status: string;
  created_at: string;
}

export interface ToolInfo {
  name: string;
  description: string;
  type: string;
  status: string;
  parameters?: Record<string, any>;
}

export interface AgentInfo {
  agent_id: string;
  name: string;
  role: string;
  status: string;
  system_prompt?: string;
  model?: string;
  temperature?: number;
  max_tokens?: number;
  tools?: string[];
}

class ApiClient {
  private baseUrl: string;

  constructor(baseUrl: string = API_BASE_URL) {
    this.baseUrl = baseUrl;
  }

  private getAuthHeaders(): HeadersInit {
    const accessToken = localStorage.getItem('accessToken');

    const headers: HeadersInit = {
      'Content-Type': 'application/json',
    };

    if (accessToken) {
      headers['Authorization'] = `Bearer ${accessToken}`;
    }

    return headers;
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const url = `${this.baseUrl}${endpoint}`;

    const response = await fetch(url, {
      ...options,
      headers: {
        ...this.getAuthHeaders(),
        ...options.headers,
      },
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ error: 'Request failed' }));
      const message = error.error?.message || error.error || error.detail || `HTTP ${response.status}`;
      if (response.status === 401 || response.status === 403) {
        localStorage.removeItem('accessToken');
        localStorage.removeItem('user');
        window.dispatchEvent(new CustomEvent('auth:expired', { detail: { status: response.status, message } }));
      }
      throw new Error(message);
    }

    return response.json();
  }

  async createTask(request: CreateTaskRequest): Promise<CreateTaskResponse> {
    return this.request<CreateTaskResponse>('/tasks', {
      method: 'POST',
      body: JSON.stringify(request),
    });
  }

  async getTask(taskId: string): Promise<Task> {
    return this.request<Task>(`/tasks/${taskId}`);
  }

  async listTasks(limit: number = 50, offset: number = 0): Promise<Task[]> {
    return this.request<Task[]>(`/tasks?limit=${limit}&offset=${offset}`);
  }

  async deleteTask(taskId: string): Promise<void> {
    return this.request<void>(`/tasks/${taskId}`, {
      method: 'DELETE',
    });
  }

  async pollTaskStatus(
    taskId: string,
    onStatusChange?: (task: Task) => void,
    interval: number = 2000,
    maxAttempts: number = 60
  ): Promise<Task> {
    let attempts = 0;

    return new Promise((resolve, reject) => {
      const poll = async () => {
        try {
          const task = await this.getTask(taskId);

          if (onStatusChange) {
            onStatusChange(task);
          }

          if (task.status === 'completed' || task.status === 'failed' || task.status === 'cancelled') {
            resolve(task);
            return;
          }

          attempts++;
          if (attempts >= maxAttempts) {
            reject(new Error('Polling timeout'));
            return;
          }

          setTimeout(poll, interval);
        } catch (error) {
          reject(error);
        }
      };

      poll();
    });
  }

  async getTaskTrace(taskId: string): Promise<TaskTrace> {
    return this.request<TaskTrace>(`/tasks/${taskId}/trace`);
  }

  async getHealth(): Promise<{ status: string; version: string }> {
    return this.request<{ status: string; version: string }>('/health');
  }

  async getMetrics(): Promise<{
    requests_total: number;
    errors_total: number;
    error_rate: number;
    avg_response_time: number;
  }> {
    return this.request<{
      requests_total: number;
      errors_total: number;
      error_rate: number;
      avg_response_time: number;
    }>('/metrics');
  }

  async getTools(): Promise<Array<{name: string; description: string; type: string; status: string}>> {
    return this.request<Array<{name: string; description: string; type: string; status: string}>>('/tools');
  }

  async createTool(tool: { name: string; description: string; type?: string; parameters_schema?: Record<string, any>; template?: string }): Promise<ToolInfo> {
    const response = await this.request<{ success: boolean; tool: ToolInfo }>('/tools', {
      method: 'POST',
      body: JSON.stringify(tool),
    });
    return response.tool;
  }

  async executeTool(toolName: string, parameters: Record<string, any>): Promise<any> {
    return this.request(`/tools/${toolName}/execute`, {
      method: 'POST',
      body: JSON.stringify({ parameters }),
    });
  }

  async getConfig(): Promise<Record<string, any>> {
    return this.request<Record<string, any>>('/config');
  }

  async updateConfig(key: string, value: any): Promise<{success: boolean; message: string}> {
    return this.request<{success: boolean; message: string}>('/config', {
      method: 'POST',
      body: JSON.stringify({ key, value }),
    });
  }

  async resetConfig(): Promise<{success: boolean; message: string}> {
    return this.request<{success: boolean; message: string}>('/config/reset', {
      method: 'POST',
    });
  }

  async listAgents(): Promise<AgentInfo[]> {
    const response = await this.request<{ agents: AgentInfo[] }>('/agents');
    return response.agents;
  }

  async createAgent(agent: { name: string; role: string; system_prompt?: string; model?: string; temperature?: number; max_tokens?: number; tools?: string[] }): Promise<AgentInfo> {
    return this.request<AgentInfo>('/agents', {
      method: 'POST',
      body: JSON.stringify(agent),
    });
  }

  async updateAgent(agentId: string, agent: { name: string; role: string; system_prompt?: string; model?: string; temperature?: number; max_tokens?: number; tools?: string[] }): Promise<AgentInfo> {
    return this.request<AgentInfo>(`/agents/${agentId}`, {
      method: 'PUT',
      body: JSON.stringify(agent),
    });
  }

  async deleteAgent(agentId: string): Promise<{ message: string }> {
    return this.request<{ message: string }>(`/agents/${agentId}`, {
      method: 'DELETE',
    });
  }
}

export const apiClient = new ApiClient();
export default apiClient;

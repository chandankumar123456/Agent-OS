const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';

export interface TaskStep {
  step_id?: string;
  step?: string;
  agent?: string;
  agent_type?: string;
  status?: string;
  result?: any;
  output_data?: any;
  input_data?: any;
  confidence?: number;
}

export interface Task {
  task_id: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
  result?: any;
  steps?: TaskStep[];
  error?: any;
  created_at?: string;
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
  trace_id?: string;
  task_id?: string;
  message?: string;
  spans?: TaskTraceSpan[];
}

export interface CreateTaskRequest {
  query: string;
  config?: {
    max_steps?: number;
    timeout?: number;
  };
}

export interface CreateTaskResponse {
  task_id: string;
  status: string;
  created_at: string;
}

class ApiClient {
  private baseUrl: string;

  constructor(baseUrl: string = API_BASE_URL) {
    this.baseUrl = baseUrl;
  }

  private getRootUrl(): string {
    return this.baseUrl.replace(/\/api\/v1\/?$/, '');
  }

  private getAuthHeaders(): HeadersInit {
    const apiKey = localStorage.getItem('apiKey');
    const accessToken = localStorage.getItem('accessToken');
    
    const headers: HeadersInit = {
      'Content-Type': 'application/json',
    };
    
    if (apiKey) {
      headers['x-api-key'] = apiKey;
    }
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
      const error = await response.json().catch(() => ({ detail: 'Request failed' }));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    return response.json();
  }

  private normalizeTaskStep(step: any): TaskStep {
    if (!step || typeof step !== 'object') {
      return {};
    }

    const nestedStep = step.step && typeof step.step === 'object' ? step.step : null;
    const stepName =
      typeof step.step === 'string'
        ? step.step
        : nestedStep?.step || nestedStep?.result || step.result?.step;

    return {
      ...step,
      step: stepName,
      agent: step.agent || step.agent_type || nestedStep?.agent || nestedStep?.agent_type,
      agent_type: step.agent_type || nestedStep?.agent_type,
      result: step.result ?? step.output_data,
      output_data: step.output_data ?? step.result,
    };
  }

  private normalizeTask(task: any): Task {
    if (!task || typeof task !== 'object') {
      return task;
    }

    return {
      ...task,
      task_id: String(task.task_id),
      status: task.status,
      steps: Array.isArray(task.steps) ? task.steps.map((step: any) => this.normalizeTaskStep(step)) : [],
    };
  }

  async createTask(request: CreateTaskRequest): Promise<CreateTaskResponse> {
    return this.request<CreateTaskResponse>('/tasks', {
      method: 'POST',
      body: JSON.stringify(request),
    });
  }

  async getTask(taskId: string): Promise<Task> {
    const task = await this.request<Task>(`/tasks/${taskId}`);
    return this.normalizeTask(task);
  }

  async listTasks(): Promise<Task[]> {
    const tasks = await this.request<Task[]>('/tasks');
    return tasks.map((task) => this.normalizeTask(task));
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
    return fetch(`${this.getRootUrl()}/health`).then((response) => response.json());
  }

  async getMetrics(): Promise<{
    requests_total: number;
    errors_total: number;
    error_rate: number;
    avg_response_time: number;
  }> {
    return fetch(`${this.getRootUrl()}/metrics`).then((response) => response.json());
  }
}

export const apiClient = new ApiClient();
export default apiClient;

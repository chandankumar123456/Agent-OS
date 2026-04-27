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
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled' | 'waiting_approval';
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

export interface DashboardMetrics {
  total_tasks: number;
  completed_tasks: number;
  failed_tasks: number;
  pending_tasks: number;
  avg_task_duration: number;
  total_tokens_used: number;
  tasks_today: number;
  tasks_by_status: Array<{ status: string; count: number }>;
  tasks_over_time: Array<{ date: string; count: number }>;
  top_agents: Array<{ agent_name: string; count: number }>;
  recent_errors: Array<{ task_id: string; error: string; created_at: string }>;
}

export interface TraceListItem {
  trace_id: string;
  task_id: string;
  status: string;
  created_at: string;
  duration: number;
}

export interface TraceDetail {
  trace_id: string;
  task_id: string;
  status: string;
  created_at: string;
  spans: Array<{
    span_id: string;
    operation: string;
    agent_name: string;
    start_time: string;
    end_time: string | null;
    status: string;
    error: string | null;
    duration: number | null;
  }>;
}

export interface MetricsTimeSeries {
  metric: string;
  range: string;
  data: Array<{ timestamp: string; value: number }>;
}

export interface CreateTaskRequest {
  query: string;
  config?: {
    max_steps?: number;
    timeout?: number;
    workflow_id?: string;
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
  category?: string;
  version?: string;
  health_status?: string;
  tags?: string[];
}

export interface ToolV2HealthMetrics {
  invocation_count: number;
  avg_latency_ms: number;
  error_rate: number;
  last_check?: string | null;
}

export interface ToolV2Implementation {
  type: 'native' | 'mcp' | 'openapi' | 'python' | 'docker';
  config: Record<string, any>;
}

export interface ToolV2Info {
  tool_id: string;
  name: string;
  description: string;
  version: string;
  input_schema: Record<string, any>;
  output_schema?: Record<string, any> | null;
  implementation: ToolV2Implementation;
  category: string;
  tags: string[];
  author: string;
  dependencies: string[];
  sandboxed: boolean;
  timeout: number;
  max_retries: number;
  health: ToolV2HealthMetrics;
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

export interface AgentPayload {
  name: string;
  role: string;
  system_prompt?: string;
  model?: string;
  temperature?: number;
  max_tokens?: number;
  tools?: string[];
}

export interface ChatSession {
  id: string;
  user_id: string;
  agent_id?: string | null;
  title?: string | null;
  created_at: string;
  updated_at: string;
}

export interface ChatMessage {
  id: string;
  session_id: string;
  role: string;
  content: string;
  created_at: string;
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

      // Attempt token refresh on 401 with token_expired
      if (response.status === 401 && error.error === 'token_expired') {
        const refreshed = await this._attemptRefresh();
        if (refreshed) {
          // Retry original request with new token
          const retryResponse = await fetch(url, {
            ...options,
            headers: {
              ...this.getAuthHeaders(),
              ...options.headers,
            },
          });
          if (retryResponse.ok) {
            return retryResponse.json();
          }
          // Retry also failed — do NOT auto-logout if refresh succeeded.
          // The retry failure is likely a permission/server issue, not auth.
          throw new Error(message);
        }
        // Refresh failed — token is genuinely invalid
        window.dispatchEvent(new CustomEvent('auth:expired', { detail: { status: response.status, message } }));
      } else if (response.status === 401) {
        // Non-token_expired 401 — token might be missing or malformed
        window.dispatchEvent(new CustomEvent('auth:expired', { detail: { status: response.status, message } }));
      }
      throw new Error(message);
    }

    return response.json();
  }

  private async _attemptRefresh(): Promise<boolean> {
    const refreshToken = localStorage.getItem('refreshToken');
    if (!refreshToken) return false;
    try {
      const response = await fetch(`${this.baseUrl}/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });
      if (!response.ok) return false;
      const data = await response.json();
      localStorage.setItem('accessToken', data.access_token);
      if (data.refresh_token) {
        localStorage.setItem('refreshToken', data.refresh_token);
      }
      // Notify AuthContext to update its state so UI stays in sync
      window.dispatchEvent(new CustomEvent('auth:token_refreshed', {
        detail: { access_token: data.access_token, user: data.user }
      }));
      return true;
    } catch {
      return false;
    }
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
    maxAttempts: number = 60,
    signal?: AbortSignal
  ): Promise<Task> {
    let attempts = 0;

    return new Promise((resolve, reject) => {
      const poll = async () => {
        if (signal?.aborted) {
          reject(new Error('Polling aborted'));
          return;
        }

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

          const timer = setTimeout(poll, interval);
          signal?.addEventListener('abort', () => {
            clearTimeout(timer);
            reject(new Error('Polling aborted'));
          }, { once: true });
        } catch (error) {
          reject(error);
        }
      };

      poll();
    });
  }

  async getTaskTrace(taskId: string): Promise<TaskTrace | null> {
    const response = await this.request<TaskTrace | { message: string; task_id: string }>(`/tasks/${taskId}/trace`);
    // Backend returns { message: "No trace available" } when no trace exists
    if ('message' in response) {
      return null;
    }
    return response;
  }

  async getHealth(): Promise<{ status: string; version: string }> {
    // Health endpoint is at root level, not under /api/v1
    const response = await fetch(`${this.baseUrl.replace('/api/v1', '')}/health`);
    if (!response.ok) throw new Error('Health check failed');
    return response.json();
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

  async getTools(): Promise<ToolInfo[]> {
    return this.request<ToolInfo[]>('/tools');
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

  async createAgent(agent: AgentPayload): Promise<AgentInfo> {
    return this.request<AgentInfo>('/agents', {
      method: 'POST',
      body: JSON.stringify(agent),
    });
  }

  async updateAgent(agentId: string, agent: AgentPayload): Promise<AgentInfo> {
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

  async getMCPServers(): Promise<Array<{
    id: string;
    name: string;
    endpoint: string;
    tools_list?: any[];
    auth_scope?: string | null;
    health_status: string;
    version: string;
    status: string;
    updated_at?: string | null;
  }>> {
    return this.request<Array<{
      id: string;
      name: string;
      endpoint: string;
      tools_list?: any[];
      auth_scope?: string | null;
      health_status: string;
      version: string;
      status: string;
      updated_at?: string | null;
    }>>('/tools/mcp-servers');
  }

  async getToolCategories(): Promise<string[]> {
    return this.request<{ categories: string[] }>('/tools/categories').then((r) => r.categories);
  }

  async getToolHealth(toolName: string): Promise<{ name: string; status: string }> {
    return this.request<{ name: string; status: string }>(`/tools/${toolName}/health`);
  }

  // Tool Registry V2
  async getToolsV2(): Promise<ToolV2Info[]> {
    const response = await this.request<{ tools: ToolV2Info[] }>('/tools/v2');
    return response.tools;
  }

  async getToolV2(toolId: string): Promise<ToolV2Info> {
    const response = await this.request<{ tool: ToolV2Info }>(`/tools/v2/${toolId}`);
    return response.tool;
  }

  async ingestOpenAPISpec(url: string, category: string = 'api'): Promise<{ tools: ToolV2Info[]; count: number }> {
    return this.request<{ tools: ToolV2Info[]; count: number }>('/tools/v2/ingest-openapi', {
      method: 'POST',
      body: JSON.stringify({ spec_url: url, category }),
    });
  }

  async executeToolV2(toolId: string, parameters: Record<string, any>): Promise<any> {
    return this.request(`/tools/v2/${toolId}/execute`, {
      method: 'POST',
      body: JSON.stringify({ parameters }),
    });
  }

  async getToolHealthV2(toolId: string): Promise<{ tool_id: string; health: ToolV2HealthMetrics }> {
    return this.request<{ tool_id: string; health: ToolV2HealthMetrics }>(`/tools/v2/${toolId}/health`);
  }

  async registerMCPServer(server: { name: string; endpoint: string }): Promise<any> {
    return this.request('/tools/mcp-servers', {
      method: 'POST',
      body: JSON.stringify(server),
    });
  }

  async checkMCPServerHealth(name: string): Promise<{ name: string; health_status: string }> {
    return this.request<{ name: string; health_status: string }>(`/tools/mcp-servers/${name}/health`);
  }

  async saveWorkflow(definition: { name: string; definition: any }): Promise<{ id: string; task_id: string; name: string; definition: any; status: string }> {
    return this.request('/workflows', {
      method: 'POST',
      body: JSON.stringify(definition),
    });
  }

  async getWorkflow(id: string): Promise<{ id: string; task_id: string; name: string; definition: any; status: string }> {
    return this.request(`/workflows/${id}`);
  }

  async getWorkflowTemplates(): Promise<Array<{id: string; name: string; definition: any}>> {
    const response = await this.request<{templates: Array<{id: string; name: string; definition: any}>}>('/workflows/templates');
    return response.templates;
  }

  async executeWorkflow(query: string, workflowId?: string): Promise<CreateTaskResponse> {
    return this.createTask({
      query,
      mode: 'workflow',
      config: { max_steps: 50, timeout: 300, workflow_id: workflowId },
    });
  }

  async approveTask(taskId: string): Promise<{ task_id: string; status: string }> {
    return this.request(`/tasks/${taskId}/approve`, { method: 'POST' });
  }

  async rejectTask(taskId: string): Promise<{ task_id: string; status: string }> {
    return this.request(`/tasks/${taskId}/reject`, { method: 'POST' });
  }

  async getWorkflowTemplatesV2(): Promise<Array<{id: string; name: string; definition: any}>> {
    const response = await this.request<{templates: Array<{id: string; name: string; definition: any}>}>('/workflows/v2/templates');
    return response.templates;
  }

  async validateWorkflowV2(definition: any): Promise<{valid: boolean; errors: string[]}> {
    return this.request<{valid: boolean; errors: string[]}>('/workflows/v2/validate', {
      method: 'POST',
      body: JSON.stringify(definition),
    });
  }

  async executeWorkflowV2(definition: any): Promise<any> {
    return this.request('/workflows/v2/execute', {
      method: 'POST',
      body: JSON.stringify(definition),
    });
  }

  async simulateWorkflowV2(definition: any): Promise<{ workflow_id: string; path: string[]; decisions: Array<{node_id: string; condition: string; result: boolean}>; estimated_tokens: number; completed: string[]; failed: string[] }> {
    return this.request('/workflows/v2/simulate', {
      method: 'POST',
      body: JSON.stringify(definition),
    });
  }

  // Deployments
  async listDeployments(): Promise<Array<{id: string; workflow_id: string; name: string; description?: string; endpoint_url: string; auth_type: string; status: string; created_at: string}>> {
    return this.request('/deployments');
  }

  async createDeployment(body: { workflow_id: string; name: string; description?: string; auth_type: string }): Promise<{ deployment_id: string; endpoint_url: string; api_key?: string }> {
    return this.request('/deployments', {
      method: 'POST',
      body: JSON.stringify(body),
    });
  }

  async deleteDeployment(deploymentId: string): Promise<{ success: boolean }> {
    return this.request(`/deployments/${deploymentId}`, { method: 'DELETE' });
  }

  async updateDeploymentStatus(deploymentId: string, status: string): Promise<{ id: string; status: string }> {
    return this.request(`/deployments/${deploymentId}/status?status=${status}`, { method: 'PATCH' });
  }

  async exportMCP(body: { workflow_id: string; name: string; description?: string; auth_type: string }): Promise<any> {
    return this.request('/deployments/mcp', {
      method: 'POST',
      body: JSON.stringify(body),
    });
  }

  async getOnboardingState(): Promise<{has_completed_tour: boolean; has_created_first_task: boolean; has_created_first_agent: boolean; has_created_first_workflow: boolean; dismissed_prompts: string[]; onboarding_complete: boolean}> {
    return this.request('/onboarding/state');
  }

  async completeOnboardingStep(step: string): Promise<{success: boolean}> {
    return this.request(`/onboarding/complete/${step}`, { method: 'POST' });
  }

  async seedExampleData(): Promise<{success: boolean}> {
    return this.request('/onboarding/seed', { method: 'POST' });
  }

  // API Keys
  async createAPIKey(request: {name: string; permissions: string[]}): Promise<{id: string; name: string; key: string; permissions: string[]; created_at: string}> {
    return this.request('/api-keys', {
      method: 'POST',
      body: JSON.stringify(request),
    });
  }

  async listAPIKeys(): Promise<Array<{id: string; name: string; permissions: string[]; last_used_at: string | null; created_at: string}>> {
    return this.request('/api-keys');
  }

  async revokeAPIKey(keyId: string): Promise<{success: boolean}> {
    return this.request(`/api-keys/${keyId}`, { method: 'DELETE' });
  }

  async getDashboardMetrics(): Promise<DashboardMetrics> {
    return this.request<DashboardMetrics>('/analytics/dashboard');
  }

  async getTraces(page: number = 1, limit: number = 20): Promise<{ traces: TraceListItem[]; total: number }> {
    return this.request<{ traces: TraceListItem[]; total: number }>(`/analytics/traces?page=${page}&limit=${limit}`);
  }

  async getTraceDetail(traceId: string): Promise<TraceDetail> {
    return this.request<TraceDetail>(`/analytics/traces/${traceId}`);
  }

  async getMetricsTimeSeries(metric: string, range: string = '1h'): Promise<MetricsTimeSeries> {
    return this.request<MetricsTimeSeries>(`/analytics/metrics?metric=${metric}&range=${range}`);
  }

  async createAgentV2(agent: Record<string, any>): Promise<any> {
    return this.request('/agents/v2', {
      method: 'POST',
      body: JSON.stringify(agent),
    });
  }

  async createSession(agentId?: string, title?: string): Promise<ChatSession> {
    return this.request<ChatSession>('/chat/sessions', {
      method: 'POST',
      body: JSON.stringify({ agent_id: agentId, title: title || 'New Chat' }),
    });
  }

  async getSessions(): Promise<ChatSession[]> {
    return this.request<ChatSession[]>('/chat/sessions');
  }

  async sendMessage(sessionId: string, content: string): Promise<ChatMessage> {
    return this.request<ChatMessage>(`/chat/sessions/${sessionId}/messages`, {
      method: 'POST',
      body: JSON.stringify({ content }),
    });
  }

  async getMessages(sessionId: string): Promise<ChatMessage[]> {
    return this.request<ChatMessage[]>(`/chat/sessions/${sessionId}/messages`);
  }

  async deleteSession(sessionId: string): Promise<{ message: string }> {
    return this.request<{ message: string }>(`/chat/sessions/${sessionId}`, {
      method: 'DELETE',
    });
  }

  // Providers
  async getProviders(): Promise<Array<{name: string; api_key?: string | null; base_url?: string | null; default_model?: string | null; enabled: boolean}>> {
    return this.request('/providers');
  }

  async testProvider(config: {name: string; api_key?: string; base_url?: string; default_model?: string}): Promise<{success: boolean; provider: string; response?: string; error?: string}> {
    return this.request('/providers/test', {
      method: 'POST',
      body: JSON.stringify(config),
    });
  }

  async getModels(): Promise<Record<string, string[]>> {
    return this.request('/providers/models');
  }

  // Knowledge
  async uploadDocument(file: File, userId?: string): Promise<{id: string; name: string; type: string; content_preview?: string; chunk_count: number; status: string; created_at: string}> {
    const formData = new FormData();
    formData.append('file', file);
    if (userId) formData.append('user_id', userId);
    const headers = this.getAuthHeaders() as Record<string, string>;
    const response = await fetch(`${this.baseUrl}/knowledge/upload`, {
      method: 'POST',
      headers: {
        Authorization: headers['Authorization'] || '',
      },
      body: formData,
    });
    if (!response.ok) {
      const error = await response.json().catch(() => ({ error: 'Upload failed' }));
      throw new Error(error.error || error.detail || 'Upload failed');
    }
    return response.json();
  }

  async getKnowledgeSources(): Promise<Array<{id: string; name: string; type: string; content_preview?: string; chunk_count: number; status: string; created_at: string}>> {
    return this.request('/knowledge');
  }

  async getKnowledgeSource(id: string): Promise<{id: string; name: string; type: string; content_preview?: string; chunk_count: number; status: string; created_at: string}> {
    return this.request(`/knowledge/${id}`);
  }

  async deleteKnowledgeSource(id: string): Promise<{success: boolean}> {
    return this.request(`/knowledge/${id}`, { method: 'DELETE' });
  }

  async queryKnowledge(sourceId: string, query: string, topK: number = 5): Promise<{chunks: Array<{id: string; source_id: string; content: string; metadata?: any}>}> {
    return this.request(`/knowledge/${sourceId}/query`, {
      method: 'POST',
      body: JSON.stringify({ query, top_k: topK }),
    });
  }
}

export const apiClient = new ApiClient();
export default apiClient;

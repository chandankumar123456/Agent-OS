export interface VisibilityEvent {
  type: string;
  task_id: string;
  tool_name: string;
  success: boolean;
  result?: any;
  visibility?: VisibilityPayload;
  error?: string;
  timestamp: string;
}

export interface VisibilityPayload {
  type: 'browser_navigated' | 'browser_screenshot' | 'browser_search' | 'browser_click' | 'browser_type' | 'browser_text' | 'browser_url' | 'browser_title' | 'desktop_screenshot' | 'desktop_click' | 'desktop_type' | 'desktop_key' | 'desktop_windows' | 'desktop_focus' | 'desktop_scroll' | 'file_operation' | 'shell_output' | string;
  [key: string]: any;
}

import { useState, useCallback } from 'react';
import type { VisibilityEvent } from '../types/results';

export function useTaskResults() {
  const [results, setResults] = useState<VisibilityEvent[]>([]);

  const addResult = useCallback((event: any) => {
    if (event.type === 'tool.result' && event.payload?.visibility) {
      const visibilityEvent: VisibilityEvent = {
        type: event.payload.visibility.type,
        task_id: event.payload.task_id || 'unknown',
        tool_name: event.payload.tool_name,
        success: event.payload.success,
        result: event.payload.result,
        visibility: event.payload.visibility,
        error: event.payload.error,
        timestamp: event.timestamp || new Date().toISOString(),
      };
      setResults((prev) => [...prev, visibilityEvent]);
    }
  }, []);

  const clearResults = useCallback(() => setResults([]), []);

  return { results, addResult, clearResults };
}

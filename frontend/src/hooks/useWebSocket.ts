import { useState, useEffect, useRef, useCallback } from 'react';

export type WebSocketStatus = 'connecting' | 'open' | 'closed' | 'error';

interface UseWebSocketOptions {
  taskId: string | null;
  onMessage?: (data: any) => void;
}

interface UseWebSocketReturn {
  messages: any[];
  status: WebSocketStatus;
  send: (data: string) => void;
}

const WS_BASE_URL = import.meta.env.VITE_WS_URL || 'ws://localhost:8000';

export function useWebSocket({ taskId, onMessage }: UseWebSocketOptions): UseWebSocketReturn {
  const [messages, setMessages] = useState<any[]>([]);
  const [status, setStatus] = useState<WebSocketStatus>('closed');
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isUnmountingRef = useRef(false);

  const clearReconnect = useCallback(() => {
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
  }, []);

  const connect = useCallback(() => {
    if (!taskId || isUnmountingRef.current) return;

    clearReconnect();
    setStatus('connecting');

    const url = `${WS_BASE_URL}/ws/tasks/${taskId}`;
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      if (isUnmountingRef.current) {
        ws.close();
        return;
      }
      reconnectAttemptsRef.current = 0;
      setStatus('open');
    };

    ws.onmessage = (event) => {
      if (isUnmountingRef.current) return;
      try {
        const parsed = JSON.parse(event.data);
        setMessages((prev) => [...prev, parsed]);
        if (onMessage) {
          onMessage(parsed);
        }
      } catch {
        setMessages((prev) => [...prev, event.data]);
        if (onMessage) {
          onMessage(event.data);
        }
      }
    };

    ws.onerror = () => {
      if (isUnmountingRef.current) return;
      setStatus('error');
    };

    ws.onclose = () => {
      if (isUnmountingRef.current) return;
      setStatus('closed');
      wsRef.current = null;

      if (taskId) {
        const delay = Math.min(1000 * 2 ** reconnectAttemptsRef.current, 30000);
        reconnectAttemptsRef.current += 1;
        reconnectTimerRef.current = setTimeout(() => {
          if (!isUnmountingRef.current && taskId) {
            connect();
          }
        }, delay);
      }
    };
  }, [taskId, onMessage, clearReconnect]);

  const send = useCallback((data: string) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(data);
    }
  }, []);

  useEffect(() => {
    isUnmountingRef.current = false;
    connect();

    return () => {
      isUnmountingRef.current = true;
      clearReconnect();
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [connect, clearReconnect]);

  return { messages, status, send };
}

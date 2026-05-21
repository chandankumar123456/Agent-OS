//! Frontend event listener for Supervisor WebSocket events.
//!
//! Events are bridged from Supervisor → Rust (events.rs) → Tauri event system → this module.
//! This module provides a type-safe subscription API for the frontend.

import { listen, type UnlistenFn } from '@tauri-apps/api/event'

// ─── Event Types ───────────────────────────────────────────

export interface SupervisorEvent {
  type: string
  timestamp: string
  payload: TaskEventPayload
}

export interface TaskEventPayload {
  task_id: string
  status: string
  query?: string
  error?: string
  step_index?: number
  step_status?: string
}

// ─── Event Subscription ─────────────────────────────────────

type EventCallback = (event: TaskEventPayload) => void

/**
 * Subscribe to all Supervisor events. Calls `onEvent` for every
 * event received through the WebSocket bridge.
 *
 * Returns an unsubscribe function.
 */
export async function subscribeToSupervisorEvents(
  onEvent: EventCallback
): Promise<UnlistenFn> {
  return listen<SupervisorEvent>('supervisor:event', (event) => {
    if (event.payload?.payload) {
      onEvent(event.payload.payload as TaskEventPayload)
    }
  })
}

/**
 * Subscribe to a specific Supervisor event type (e.g., 'task:created').
 * Only fires when the event type matches.
 *
 * Returns an unsubscribe function.
 */
export async function subscribeToEventType(
  eventType: string,
  onEvent: EventCallback
): Promise<UnlistenFn> {
  const eventName = `supervisor:${eventType}`
  return listen<TaskEventPayload>(eventName, (event) => {
    if (event.payload) {
      onEvent(event.payload)
    }
  })
}

// ─── Connection Status ──────────────────────────────────────

type ConnectionCallback = (connected: boolean) => void

/**
 * Watch the WebSocket connection status by listening for
 * connect/disconnect events from the Rust bridge.
 *
 * Returns an unsubscribe function.
 */
export async function watchConnectionStatus(
  onStatus: ConnectionCallback
): Promise<UnlistenFn> {
  // We infer connection health: if no event fires for 15s, assume disconnected.
  let lastEventTime = Date.now()
  const checkInterval = setInterval(() => {
    const elapsed = Date.now() - lastEventTime
    onStatus(elapsed < 20000)
  }, 5000)

  const unlisten = await subscribeToSupervisorEvents(() => {
    lastEventTime = Date.now()
    onStatus(true)
  })

  return () => {
    clearInterval(checkInterval)
    unlisten()
  }
}

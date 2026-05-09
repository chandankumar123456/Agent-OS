# AgentOS API Documentation

Complete reference for the AgentOS HTTP API.

**Base URL:** `http://localhost:8080`

---

## Authentication

Currently, the API uses token-based authentication via query parameters or headers.

### Header Authentication
```
Authorization: Bearer <token>
```

### Query Parameter Authentication
```
GET /api/v1/agents?token=<token>
```

---

## Endpoints

### Health & Status

#### GET /health
Returns the health status of the supervisor.

**Response:**
```json
{
  "status": "healthy",
  "version": "0.1.0",
  "timestamp": "2026-05-09T12:00:00Z",
  "components": {
    "database": "healthy",
    "python_runtime": "healthy",
    "mcp_servers": "healthy"
  }
}
```

**Status Codes:**
- `200 OK` - System is healthy
- `503 Service Unavailable` - One or more components are unhealthy

---

#### GET /status
Returns detailed supervisor status information.

**Response:**
```json
{
  "state": "running",
  "version": "0.1.0",
  "start_time": "2026-05-09T12:00:00Z",
  "uptime": "2h30m",
  "python_runtime": {
    "running": true,
    "pid": 1234,
    "address": "127.0.0.1:8000"
  },
  "mcp_servers": [
    {
      "name": "filesystem",
      "running": true,
      "port": 8001
    }
  ]
}
```

---

### Python Runtime

#### POST /api/v1/python/start
Starts the Python runtime.

**Request Body:**
```json
{
  "port": 8000,
  "host": "127.0.0.1"
}
```

**Response:**
```json
{
  "success": true,
  "pid": 1234,
  "address": "127.0.0.1:8000"
}
```

---

#### POST /api/v1/python/stop
Stops the Python runtime.

**Response:**
```json
{
  "success": true,
  "message": "Python runtime stopped"
}
```

---

### Agent Sessions

#### GET /api/v1/agents
List all agent sessions.

**Query Parameters:**
- `status` (optional) - Filter by status: `active`, `completed`, `failed`
- `limit` (optional) - Maximum number of results (default: 100)
- `offset` (optional) - Offset for pagination (default: 0)

**Response:**
```json
{
  "sessions": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "status": "active",
      "created_at": "2026-05-09T12:00:00Z",
      "updated_at": "2026-05-09T12:05:00Z",
      "action_count": 5
    }
  ],
  "total": 1,
  "limit": 100,
  "offset": 0
}
```

---

#### POST /api/v1/agents
Create a new agent session.

**Request Body:**
```json
{
  "name": "My Agent Session",
  "config": {
    "model": "gpt-4o",
    "max_steps": 10
  }
}
```

**Response:**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "created",
  "created_at": "2026-05-09T12:00:00Z"
}
```

---

#### GET /api/v1/agents/{id}
Get a specific agent session.

**Response:**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "active",
  "created_at": "2026-05-09T12:00:00Z",
  "updated_at": "2026-05-09T12:05:00Z",
  "actions": [
    {
      "sequence": 1,
      "type": "execute",
      "status": "completed",
      "timestamp": "2026-05-09T12:01:00Z"
    }
  ]
}
```

---

#### PUT /api/v1/agents/{id}
Update an agent session.

**Request Body:**
```json
{
  "status": "paused",
  "config": {
    "max_steps": 20
  }
}
```

**Response:**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "paused",
  "updated_at": "2026-05-09T12:10:00Z"
}
```

---

#### DELETE /api/v1/agents/{id}
Delete an agent session.

**Response:**
```json
{
  "success": true,
  "message": "Agent session deleted"
}
```

---

### Worker Pool

#### GET /api/v1/workers/status
Get worker pool status.

**Response:**
```json
{
  "pool_size": 5,
  "active_workers": 3,
  "idle_workers": 2,
  "queue_depth": 0,
  "average_latency_ms": 4.7
}
```

---

#### POST /api/v1/workers/scale
Scale the worker pool.

**Request Body:**
```json
{
  "size": 10
}
```

**Response:**
```json
{
  "success": true,
  "message": "Pool scaled to 10 workers",
  "previous_size": 5,
  "new_size": 10
}
```

---

#### GET /api/v1/workers/{id}/health
Get health status of a specific worker.

**Response:**
```json
{
  "worker_id": "worker-1",
  "healthy": true,
  "last_check": "2026-05-09T12:00:00Z",
  "consecutive_failures": 0
}
```

---

#### GET /api/v1/workers/metrics
Get worker pool metrics.

**Response:**
```json
{
  "total_requests": 1000,
  "successful_requests": 995,
  "failed_requests": 5,
  "total_latency_ms": 4700,
  "average_latency_ms": 4.7,
  "p50_latency_ms": 4.5,
  "p95_latency_ms": 7.2,
  "p99_latency_ms": 12.3
}
```

---

## Error Responses

All errors follow this format:

```json
{
  "error": {
    "code": "NOT_FOUND",
    "message": "Agent session not found",
    "details": "The requested agent session ID does not exist"
  }
}
```

### Error Codes

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `BAD_REQUEST` | 400 | Invalid request parameters |
| `UNAUTHORIZED` | 401 | Authentication required |
| `FORBIDDEN` | 403 | Permission denied |
| `NOT_FOUND` | 404 | Resource not found |
| `CONFLICT` | 409 | Resource already exists |
| `INTERNAL_ERROR` | 500 | Internal server error |
| `SERVICE_UNAVAILABLE` | 503 | Service temporarily unavailable |

---

## Rate Limiting

API requests are rate-limited to prevent abuse.

**Default Limits:**
- 100 requests per minute per IP
- 1000 requests per hour per IP

**Rate Limit Headers:**
```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1620000000
```

When rate limited, the API returns:
```json
{
  "error": {
    "code": "RATE_LIMITED",
    "message": "Rate limit exceeded",
    "retry_after": 60
  }
}
```

---

## WebSocket API

Real-time updates are available via WebSocket.

**Connection URL:**
```
ws://localhost:8080/ws
```

### Events

#### agent_session_created
Sent when a new agent session is created.

```json
{
  "event": "agent_session_created",
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "created_at": "2026-05-09T12:00:00Z"
  }
}
```

#### agent_session_updated
Sent when an agent session is updated.

```json
{
  "event": "agent_session_updated",
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "status": "completed",
    "updated_at": "2026-05-09T12:05:00Z"
  }
}
```

#### worker_pool_scaled
Sent when the worker pool is scaled.

```json
{
  "event": "worker_pool_scaled",
  "data": {
    "previous_size": 5,
    "new_size": 10,
    "timestamp": "2026-05-09T12:00:00Z"
  }
}
```

---

## OpenAPI Specification

The complete OpenAPI 3.0 specification is available at:

```
GET /openapi.json
```

You can use this with tools like Swagger UI or Postman.

---

## SDK Examples

### Python

```python
import requests

BASE_URL = "http://localhost:8080"

# Get health status
response = requests.get(f"{BASE_URL}/health")
print(response.json())

# Create agent session
response = requests.post(
    f"{BASE_URL}/api/v1/agents",
    json={"name": "Test Session"}
)
session_id = response.json()["id"]

# Get session details
response = requests.get(f"{BASE_URL}/api/v1/agents/{session_id}")
print(response.json())
```

### JavaScript

```javascript
const BASE_URL = 'http://localhost:8080';

// Get health status
fetch(`${BASE_URL}/health`)
  .then(res => res.json())
  .then(data => console.log(data));

// Create agent session
fetch(`${BASE_URL}/api/v1/agents`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ name: 'Test Session' })
})
  .then(res => res.json())
  .then(data => console.log(data.id));
```

### cURL

```bash
# Get health status
curl http://localhost:8080/health

# Create agent session
curl -X POST http://localhost:8080/api/v1/agents \
  -H "Content-Type: application/json" \
  -d '{"name": "Test Session"}'

# Get worker pool status
curl http://localhost:8080/api/v1/workers/status
```

---

**Version:** 0.1.0  
**Last Updated:** 2026-05-09

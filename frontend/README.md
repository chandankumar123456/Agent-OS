# frontend/ Technical Documentation

## Purpose
React control plane for interacting with Agent-OS backend APIs.

## Frontend Architecture Diagram

```mermaid
flowchart TB
    User[User] --> Router[React Router]
    Router --> Public[Public Pages
Landing/Login/Signup]
    Router --> Protected[Protected Routes]

    Protected --> Layout[Layout + Navigation]
    Layout --> Dashboard[Dashboard]
    Layout --> AgentBuilder[Agent Builder]
    Layout --> Tools[Tool Registry]
    Layout --> Orchestrator[Orchestrator View]
    Layout --> Monitor[Runtime Monitor]
    Layout --> Settings[Settings]

    Protected --> AuthCtx[AuthContext]
    Dashboard --> APIClient[api/client.ts]
    AgentBuilder --> APIClient
    Tools --> APIClient
    Monitor --> APIClient
    Settings --> APIClient

    APIClient --> Backend[/FastAPI API/]
```

## Technology Stack
- React 19 + TypeScript
- React Router 7
- Vite 8
- Tailwind CSS + custom design utilities
- Vitest + Testing Library
- ESLint + TypeScript ESLint

## Application Architecture
- App shell and protected routing in `src/App.tsx`.
- Auth state management in `src/context/AuthContext.tsx`.
- HTTP integration in `src/api/client.ts`.
- Feature pages in `src/pages/*`.

## Auth and Session Lifecycle

```mermaid
sequenceDiagram
    participant U as User
    participant UI as Frontend
    participant API as Backend
    participant S as localStorage

    U->>UI: Login form submit
    UI->>API: POST /api/v1/auth/login
    API-->>UI: access token + user
    UI->>S: store token and user
    UI->>UI: render protected routes
    UI->>API: authorized API calls
    API-->>UI: 401/403 on expired token
    UI->>S: clear auth state
    UI->>UI: dispatch auth:expired and redirect
```

## Main UI Domains
- Task execution and traces (`Dashboard`).
- Tool registry (`Tools`).
- Agent configuration (`AgentBuilder`).
- Runtime monitor (`Monitor`).
- Mode/agent visibility (`Orchestrator`).
- Runtime config management (`Settings`).

## Scripts
- `npm run dev`
- `npm run lint`
- `npm run test`
- `npm run build`
- `npm run preview`

# frontend/

React + TypeScript UI for interacting with Agent-OS APIs.

## Stack

- React 19 + React Router 7
- Vite 8
- TailwindCSS + custom utility styles
- Vitest + Testing Library
- ESLint + TypeScript ESLint

## Application Areas (`src/pages`)

- `Dashboard`: task submission, polling, trace display, metrics cards.
- `AgentBuilder`: CRUD for agents and tool assignment.
- `Tools`: list/register/execute tools.
- `Orchestrator`: active agent view.
- `Monitor`: runtime metrics panel.
- `Settings`: runtime config view/reset.
- `Login`, `Signup`, `Landing`: auth + entry flows.

## API Client

`src/api/client.ts` centralizes all backend HTTP calls, auth header handling, and auth-expiry event dispatch.

## Scripts

- `npm run dev`
- `npm run lint`
- `npm run test`
- `npm run build`
- `npm run preview`

# frontend/src/ Technical Documentation

## Purpose
Primary frontend source code.

## Entry Modules
- `main.tsx`: React bootstrapping.
- `App.tsx`: route graph and protected-route boundary.
- `index.css`: global Tailwind and custom utility classes.

## Directory Map
- `api/`: typed backend client.
- `context/`: auth provider and auth lifecycle tests.
- `components/`: shared layout shell.
- `pages/`: route-level feature pages.
- `assets/`: bundled visual assets.
- `test/`: test setup.

## Operational Notes
Auth failures propagate through custom `auth:expired` event and force logout.

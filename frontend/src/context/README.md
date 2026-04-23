# frontend/src/context/ Technical Documentation

## Purpose
Global auth/session state and lifecycle management.

## Modules
- `AuthContext.tsx`: provider/hook/login/signup/logout/token expiry handling.
- `AuthContext.test.tsx`: token expiry/invalid token logout behavior tests.

## Session Behavior
- Persists `accessToken` and `user` in localStorage.
- Validates token expiration client-side.
- Listens to storage and custom auth-expired events for cross-tab/session sync.

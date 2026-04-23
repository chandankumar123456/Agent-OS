# app/api/schemas/ Technical Documentation

## Purpose
Shared schema objects for request/response payload validation.

## Modules
- `user.py`:
  - `UserCreate`, `LoginRequest`
  - `UserResponse`, `TokenResponse`
- `error.py`:
  - `ErrorContext`
  - `ErrorEnvelope`

## Design Notes
Schemas are intentionally minimal and used by auth and error response surfaces.

# app/auth/ Technical Documentation

## Purpose
Credential, token, and auth helper utilities.

## Functions
- `hash_password`, `verify_password`
- `create_access_token`, `verify_access_token`
- `generate_api_key`
- `get_password_strength`

## Security Behavior
- Bcrypt is used through passlib context.
- Passwords exceeding bcrypt byte limit (72) are SHA-256 preprocessed.
- JWT includes expiration and requires `sub` claim for validity.

## Used By
- `app/api/routes/auth.py`
- `app/api/deps.py`
- `app/middleware/auth.py`, `app/middleware/rate_limit.py`

# app/config/ Technical Documentation

## Purpose
Runtime configuration model and validation.

## Module
- `settings.py`: `Settings(BaseSettings)` with field validators and required dependency checks.

## Key Technical Characteristics
- Loads env vars from `.env`.
- Validates bounds for retries/timeouts/rate limits.
- Enforces mandatory URLs and OpenAI API key.
- Exposes singleton `settings` instance imported globally.

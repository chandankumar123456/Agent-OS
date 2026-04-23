# app/migrations/ Technical Documentation

## Purpose
Code-based migration orchestration and schema status reporting.

## Module
- `runner.py`: migration table management, file discovery, statement splitting, pending migration application.

## Migration Source
Reads SQL files from repository-level `/migrations` directory.

## Operational Flow
1. Ensure `schema_migrations` table exists.
2. Compare applied versions with disk migration files.
3. Apply pending migrations in order.
4. Record each applied version atomically.

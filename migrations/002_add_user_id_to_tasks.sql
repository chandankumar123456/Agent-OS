-- Migration 002: Add user_id to tasks table
-- Created: 2026-04-22
-- Description: Adds user_id column for multi-user support with proper indexes

-- Add user_id column with default for existing rows
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS user_id VARCHAR(36) DEFAULT 'system' NOT NULL;

-- Backfill any existing NULL values (safety net)
UPDATE tasks SET user_id = 'system' WHERE user_id IS NULL;

-- Add indexes for query performance
CREATE INDEX IF NOT EXISTS idx_tasks_user_id ON tasks(user_id);
CREATE INDEX IF NOT EXISTS idx_tasks_user_id_created_at ON tasks(user_id, created_at DESC);

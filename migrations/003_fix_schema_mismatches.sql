-- Migration 003: Fix schema mismatches in steps and users tables
-- Created: 2026-04-22
-- Description: Add missing columns and fix type mismatches

-- Add missing depends_on column to steps
ALTER TABLE steps ADD COLUMN IF NOT EXISTS depends_on JSON;

-- Fix confidence column type from integer to float (double precision)
ALTER TABLE steps ALTER COLUMN confidence TYPE DOUBLE PRECISION USING confidence::DOUBLE PRECISION;

-- Add missing role column to users
ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR(20) NOT NULL DEFAULT 'user';

-- Backfill any existing NULL roles
UPDATE users SET role = 'user' WHERE role IS NULL;

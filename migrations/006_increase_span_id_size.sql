-- Migration 006: Increase spans.span_id column size
-- Created: 2026-04-25
-- Description: Fixes StringDataRightTruncationError when observability bus writes
-- human-readable span_ids like "planner.reasoning:2026-04-25T16:12:52.274630"

ALTER TABLE spans ALTER COLUMN span_id TYPE VARCHAR(255);

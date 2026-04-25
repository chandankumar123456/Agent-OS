-- Migration 004: Add missing columns and tables for AgentModel, MCP, guardrails, checkpoints
-- Created: 2026-04-24
-- Description: Sync database schema with SQLAlchemy models

-- 1. Add missing columns to agents table
ALTER TABLE agents ADD COLUMN IF NOT EXISTS version VARCHAR(20) DEFAULT '1.0.0';

-- 2. Add missing columns to workflow_nodes table
ALTER TABLE workflow_nodes ADD COLUMN IF NOT EXISTS node_type VARCHAR(20) NOT NULL DEFAULT 'agent';
ALTER TABLE workflow_nodes ADD COLUMN IF NOT EXISTS approval_config JSON;

-- 3. Create mcp_servers table
CREATE TABLE IF NOT EXISTS mcp_servers (
    id VARCHAR(36) PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    endpoint VARCHAR(500) NOT NULL,
    tools_list JSON,
    auth_scope VARCHAR(255),
    health_status VARCHAR(20) DEFAULT 'unknown',
    version VARCHAR(20) DEFAULT '1.0.0',
    status VARCHAR(20) DEFAULT 'active',
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_mcp_servers_name ON mcp_servers(name);

-- 4. Create agent_versions table
CREATE TABLE IF NOT EXISTS agent_versions (
    id VARCHAR(36) PRIMARY KEY,
    agent_key VARCHAR(100) NOT NULL,
    version VARCHAR(20) NOT NULL,
    name VARCHAR(100) NOT NULL,
    role VARCHAR(50) NOT NULL,
    system_prompt TEXT,
    model VARCHAR(100),
    temperature FLOAT,
    max_tokens INTEGER,
    tools JSON,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW(),
    CONSTRAINT uq_agent_version UNIQUE (agent_key, version)
);
CREATE INDEX IF NOT EXISTS idx_agent_versions_agent_key ON agent_versions(agent_key);

-- 5. Create guardrail_rules table
CREATE TABLE IF NOT EXISTS guardrail_rules (
    id VARCHAR(36) PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    rule_type VARCHAR(30) NOT NULL,
    condition JSON NOT NULL DEFAULT '{}',
    action VARCHAR(20) NOT NULL DEFAULT 'block',
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_guardrail_rules_name ON guardrail_rules(name);

-- 6. Create checkpoints table (for LangGraph)
CREATE TABLE IF NOT EXISTS checkpoints (
    thread_id VARCHAR(100) NOT NULL,
    checkpoint_ns VARCHAR(100) NOT NULL DEFAULT '',
    checkpoint_id VARCHAR(100) NOT NULL,
    parent_checkpoint_id VARCHAR(100),
    checkpoint TEXT NOT NULL,
    metadata TEXT,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW(),
    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
);

-- Migration 005: Add v2 tables for deep redesign
-- Created: 2026-04-24
-- Description: Creates tools_v2, agent_config_v2, and user_onboarding_state tables

-- 1. Create tools_v2 table
CREATE TABLE IF NOT EXISTS tools_v2 (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tool_id VARCHAR NOT NULL,
    name VARCHAR NOT NULL,
    description TEXT,
    version VARCHAR DEFAULT '1.0.0',
    input_schema JSON DEFAULT '{}',
    output_schema JSON,
    implementation_type VARCHAR NOT NULL,
    implementation_config JSON DEFAULT '{}',
    category VARCHAR DEFAULT 'general',
    tags JSON DEFAULT '[]',
    author VARCHAR DEFAULT 'system',
    dependencies JSON DEFAULT '[]',
    sandboxed BOOLEAN DEFAULT FALSE,
    timeout INTEGER DEFAULT 30,
    max_retries INTEGER DEFAULT 2,
    invocation_count INTEGER DEFAULT 0,
    avg_latency_ms DOUBLE PRECISION DEFAULT 0.0,
    error_rate DOUBLE PRECISION DEFAULT 0.0,
    status VARCHAR DEFAULT 'active',
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_tools_v2_category ON tools_v2(category);
CREATE UNIQUE INDEX IF NOT EXISTS ix_tools_v2_tool_id ON tools_v2(tool_id);

-- 2. Create agent_config_v2 table
CREATE TABLE IF NOT EXISTS agent_config_v2 (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id VARCHAR NOT NULL,
    name VARCHAR NOT NULL,
    role VARCHAR NOT NULL,
    goal TEXT DEFAULT '',
    backstory TEXT DEFAULT '',
    model VARCHAR DEFAULT 'gpt-4o',
    temperature DOUBLE PRECISION DEFAULT 0.7,
    max_tokens INTEGER DEFAULT 2048,
    reasoning BOOLEAN DEFAULT FALSE,
    max_reasoning_attempts INTEGER DEFAULT 3,
    tools JSON DEFAULT '[]',
    allow_delegation BOOLEAN DEFAULT FALSE,
    memory_enabled BOOLEAN DEFAULT TRUE,
    knowledge_sources JSON DEFAULT '[]',
    max_iter INTEGER DEFAULT 20,
    max_execution_time INTEGER DEFAULT 300,
    max_retry_limit INTEGER DEFAULT 2,
    system_template TEXT,
    prompt_template TEXT,
    response_template TEXT,
    status VARCHAR DEFAULT 'active',
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_agent_config_v2_agent_id ON agent_config_v2(agent_id);

-- 3. Create user_onboarding_state table
CREATE TABLE IF NOT EXISTS user_onboarding_state (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR NOT NULL,
    has_completed_tour BOOLEAN DEFAULT FALSE,
    has_created_first_task BOOLEAN DEFAULT FALSE,
    has_created_first_agent BOOLEAN DEFAULT FALSE,
    has_created_first_workflow BOOLEAN DEFAULT FALSE,
    dismissed_prompts JSON DEFAULT '[]',
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_user_onboarding_state_user_id ON user_onboarding_state(user_id);

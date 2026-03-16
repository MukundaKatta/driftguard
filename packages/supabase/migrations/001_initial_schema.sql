-- DriftGuard Database Schema
-- Migration: 001_initial_schema
-- Description: Create all core tables for the DriftGuard platform

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================================
-- WORKSPACES
-- ============================================================================
CREATE TABLE workspaces (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    owner_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    plan TEXT NOT NULL DEFAULT 'free' CHECK (plan IN ('free', 'pro', 'enterprise')),
    stripe_customer_id TEXT,
    stripe_subscription_id TEXT,
    settings JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_workspaces_owner_id ON workspaces(owner_id);
CREATE UNIQUE INDEX idx_workspaces_stripe_customer ON workspaces(stripe_customer_id) WHERE stripe_customer_id IS NOT NULL;

-- ============================================================================
-- MODEL ENDPOINTS
-- ============================================================================
CREATE TABLE model_endpoints (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    platform TEXT NOT NULL CHECK (platform IN ('bedrock', 'sagemaker', 'openai', 'custom')),
    endpoint_url TEXT,
    api_key TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive', 'archived')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_model_endpoints_workspace ON model_endpoints(workspace_id);
CREATE INDEX idx_model_endpoints_status ON model_endpoints(workspace_id, status);
CREATE UNIQUE INDEX idx_model_endpoints_api_key ON model_endpoints(api_key);

-- ============================================================================
-- MONITORS
-- ============================================================================
CREATE TABLE monitors (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    model_endpoint_id UUID NOT NULL REFERENCES model_endpoints(id) ON DELETE CASCADE,
    drift_type TEXT NOT NULL CHECK (drift_type IN ('data_drift', 'embedding_drift', 'response_drift', 'confidence_drift', 'query_drift')),
    config JSONB NOT NULL DEFAULT '{}',
    schedule_minutes INTEGER NOT NULL DEFAULT 60 CHECK (schedule_minutes >= 1),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'paused', 'disabled')),
    last_run_at TIMESTAMPTZ,
    next_run_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_monitors_workspace ON monitors(workspace_id);
CREATE INDEX idx_monitors_model ON monitors(model_endpoint_id);
CREATE INDEX idx_monitors_status ON monitors(status, next_run_at);
CREATE INDEX idx_monitors_next_run ON monitors(next_run_at) WHERE status = 'active';

-- ============================================================================
-- BASELINES
-- ============================================================================
CREATE TABLE baselines (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    model_endpoint_id UUID NOT NULL REFERENCES model_endpoints(id) ON DELETE CASCADE,
    drift_type TEXT NOT NULL CHECK (drift_type IN ('data_drift', 'embedding_drift', 'response_drift', 'confidence_drift', 'query_drift')),
    data JSONB NOT NULL,
    sample_count INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX idx_baselines_unique ON baselines(workspace_id, model_endpoint_id, drift_type);
CREATE INDEX idx_baselines_model ON baselines(model_endpoint_id);

-- ============================================================================
-- DRIFT RESULTS
-- ============================================================================
CREATE TABLE drift_results (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    monitor_id UUID NOT NULL REFERENCES monitors(id) ON DELETE CASCADE,
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    drift_type TEXT NOT NULL,
    is_drifted BOOLEAN NOT NULL DEFAULT FALSE,
    score DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    details JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_drift_results_monitor ON drift_results(monitor_id, created_at DESC);
CREATE INDEX idx_drift_results_workspace ON drift_results(workspace_id, created_at DESC);
CREATE INDEX idx_drift_results_drifted ON drift_results(workspace_id, is_drifted, created_at DESC);
CREATE INDEX idx_drift_results_type ON drift_results(workspace_id, drift_type, created_at DESC);

-- ============================================================================
-- ALERT CONFIGS
-- ============================================================================
CREATE TABLE alert_configs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    model_endpoint_id UUID NOT NULL REFERENCES model_endpoints(id) ON DELETE CASCADE,
    channel TEXT NOT NULL CHECK (channel IN ('slack', 'pagerduty', 'email', 'sns')),
    destination TEXT NOT NULL,
    severity_threshold TEXT NOT NULL DEFAULT 'warning' CHECK (severity_threshold IN ('info', 'warning', 'critical')),
    config JSONB NOT NULL DEFAULT '{}',
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_alert_configs_workspace ON alert_configs(workspace_id);
CREATE INDEX idx_alert_configs_model ON alert_configs(model_endpoint_id);
CREATE INDEX idx_alert_configs_enabled ON alert_configs(model_endpoint_id, enabled) WHERE enabled = TRUE;

-- ============================================================================
-- ALERT HISTORY
-- ============================================================================
CREATE TABLE alert_history (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    alert_config_id UUID NOT NULL REFERENCES alert_configs(id) ON DELETE CASCADE,
    model_endpoint_id UUID NOT NULL REFERENCES model_endpoints(id) ON DELETE CASCADE,
    drift_result_id UUID REFERENCES drift_results(id) ON DELETE SET NULL,
    channel TEXT NOT NULL,
    destination TEXT NOT NULL,
    severity TEXT NOT NULL,
    message TEXT,
    success BOOLEAN NOT NULL DEFAULT FALSE,
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_alert_history_workspace ON alert_history(workspace_id, created_at DESC);
CREATE INDEX idx_alert_history_model ON alert_history(model_endpoint_id, created_at DESC);
CREATE INDEX idx_alert_history_config ON alert_history(alert_config_id, created_at DESC);
CREATE INDEX idx_alert_history_config_success ON alert_history(alert_config_id, success, created_at DESC);

-- ============================================================================
-- ROW LEVEL SECURITY
-- ============================================================================

ALTER TABLE workspaces ENABLE ROW LEVEL SECURITY;
ALTER TABLE model_endpoints ENABLE ROW LEVEL SECURITY;
ALTER TABLE monitors ENABLE ROW LEVEL SECURITY;
ALTER TABLE baselines ENABLE ROW LEVEL SECURITY;
ALTER TABLE drift_results ENABLE ROW LEVEL SECURITY;
ALTER TABLE alert_configs ENABLE ROW LEVEL SECURITY;
ALTER TABLE alert_history ENABLE ROW LEVEL SECURITY;

-- Workspace access: owner only
CREATE POLICY workspace_owner_policy ON workspaces
    FOR ALL USING (owner_id = auth.uid());

-- Model endpoints: workspace members
CREATE POLICY model_endpoints_workspace_policy ON model_endpoints
    FOR ALL USING (
        workspace_id IN (SELECT id FROM workspaces WHERE owner_id = auth.uid())
    );

-- Monitors: workspace members
CREATE POLICY monitors_workspace_policy ON monitors
    FOR ALL USING (
        workspace_id IN (SELECT id FROM workspaces WHERE owner_id = auth.uid())
    );

-- Baselines: workspace members
CREATE POLICY baselines_workspace_policy ON baselines
    FOR ALL USING (
        workspace_id IN (SELECT id FROM workspaces WHERE owner_id = auth.uid())
    );

-- Drift results: workspace members
CREATE POLICY drift_results_workspace_policy ON drift_results
    FOR ALL USING (
        workspace_id IN (SELECT id FROM workspaces WHERE owner_id = auth.uid())
    );

-- Alert configs: workspace members
CREATE POLICY alert_configs_workspace_policy ON alert_configs
    FOR ALL USING (
        workspace_id IN (SELECT id FROM workspaces WHERE owner_id = auth.uid())
    );

-- Alert history: workspace members
CREATE POLICY alert_history_workspace_policy ON alert_history
    FOR ALL USING (
        workspace_id IN (SELECT id FROM workspaces WHERE owner_id = auth.uid())
    );

-- ============================================================================
-- UPDATED_AT TRIGGER
-- ============================================================================

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_workspaces_updated_at
    BEFORE UPDATE ON workspaces
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_model_endpoints_updated_at
    BEFORE UPDATE ON model_endpoints
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_monitors_updated_at
    BEFORE UPDATE ON monitors
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_baselines_updated_at
    BEFORE UPDATE ON baselines
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_alert_configs_updated_at
    BEFORE UPDATE ON alert_configs
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

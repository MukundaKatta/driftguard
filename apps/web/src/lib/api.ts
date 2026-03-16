const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface FetchOptions extends RequestInit {
  token?: string;
}

async function apiFetch<T>(path: string, options: FetchOptions = {}): Promise<T> {
  const { token, ...fetchOptions } = options;
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const response = await fetch(`${API_URL}${path}`, {
    ...fetchOptions,
    headers,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(error.detail || `API error: ${response.status}`);
  }

  return response.json();
}

export interface ModelEndpoint {
  id: string;
  name: string;
  platform: string;
  endpoint_url: string | null;
  status: string;
  api_key: string;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface Monitor {
  id: string;
  model_endpoint_id: string;
  drift_type: string;
  config: Record<string, unknown>;
  schedule_minutes: number;
  status: string;
  last_run_at: string | null;
  next_run_at: string | null;
  created_at: string;
}

export interface DriftResult {
  id: string;
  monitor_id: string;
  drift_type: string;
  is_drifted: boolean;
  score: number;
  details: Record<string, unknown>;
  created_at: string;
}

export interface AlertConfig {
  id: string;
  model_endpoint_id: string;
  channel: string;
  destination: string;
  severity_threshold: string;
  config: Record<string, unknown>;
  created_at: string;
}

export interface AlertHistoryItem {
  id: string;
  alert_config_id: string;
  model_endpoint_id: string;
  drift_result_id: string;
  channel: string;
  severity: string;
  message: string;
  success: boolean;
  error: string | null;
  created_at: string;
}

export interface DriftReport {
  model_endpoint_id: string;
  period_days: number;
  total_checks: number;
  drift_detected_count: number;
  by_type: Record<string, {
    checks: number;
    drifted: number;
    avg_score: number;
  }>;
}

// Models
export const listModels = (token: string) =>
  apiFetch<{ models: ModelEndpoint[] }>("/api/v1/models", { token });

export const getModel = (id: string, token: string) =>
  apiFetch<ModelEndpoint>(`/api/v1/models/${id}`, { token });

export const createModel = (data: { name: string; platform: string; endpoint_url?: string }, token: string) =>
  apiFetch<{ id: string; name: string; platform: string; api_key: string }>("/api/v1/models", {
    method: "POST",
    body: JSON.stringify(data),
    token,
  });

export const deleteModel = (id: string, token: string) =>
  apiFetch<{ status: string }>(`/api/v1/models/${id}`, { method: "DELETE", token });

// Monitors
export const listMonitors = (token: string) =>
  apiFetch<{ monitors: Monitor[] }>("/api/v1/monitors", { token });

export const getMonitor = (id: string, token: string) =>
  apiFetch<Monitor>(`/api/v1/monitors/${id}`, { token });

export const createMonitor = (
  data: { model_endpoint_id: string; drift_type: string; config?: Record<string, unknown>; schedule_minutes?: number },
  token: string,
) =>
  apiFetch<{ id: string; model_endpoint_id: string; drift_type: string; status: string }>("/api/v1/monitors", {
    method: "POST",
    body: JSON.stringify(data),
    token,
  });

export const deleteMonitor = (id: string, token: string) =>
  apiFetch<{ status: string }>(`/api/v1/monitors/${id}`, { method: "DELETE", token });

// Drift
export const runDriftDetection = (monitorId: string, token: string) =>
  apiFetch<DriftResult>("/api/v1/drift/run", {
    method: "POST",
    body: JSON.stringify({ monitor_id: monitorId }),
    token,
  });

export const listDriftResults = (params: { model_endpoint_id?: string; monitor_id?: string; limit?: number }, token: string) => {
  const searchParams = new URLSearchParams();
  if (params.model_endpoint_id) searchParams.set("model_endpoint_id", params.model_endpoint_id);
  if (params.monitor_id) searchParams.set("monitor_id", params.monitor_id);
  if (params.limit) searchParams.set("limit", String(params.limit));
  return apiFetch<{ results: DriftResult[] }>(`/api/v1/drift/results?${searchParams}`, { token });
};

export const getDriftResult = (id: string, token: string) =>
  apiFetch<DriftResult>(`/api/v1/drift/results/${id}`, { token });

// Alerts
export const listAlertConfigs = (token: string) =>
  apiFetch<{ configs: AlertConfig[] }>("/api/v1/alerts/config", { token });

export const createAlertConfig = (
  data: { model_endpoint_id: string; channel: string; destination: string; severity_threshold?: string },
  token: string,
) =>
  apiFetch<{ id: string; status: string }>("/api/v1/alerts/config", {
    method: "POST",
    body: JSON.stringify(data),
    token,
  });

export const deleteAlertConfig = (id: string, token: string) =>
  apiFetch<{ status: string }>(`/api/v1/alerts/config/${id}`, { method: "DELETE", token });

export const listAlertHistory = (params: { model_endpoint_id?: string; limit?: number }, token: string) => {
  const searchParams = new URLSearchParams();
  if (params.model_endpoint_id) searchParams.set("model_endpoint_id", params.model_endpoint_id);
  if (params.limit) searchParams.set("limit", String(params.limit));
  return apiFetch<{ history: AlertHistoryItem[] }>(`/api/v1/alerts/history?${searchParams}`, { token });
};

// Reports
export const getDriftReport = (modelId: string, days: number, token: string) =>
  apiFetch<DriftReport>(`/api/v1/reports/${modelId}?days=${days}`, { token });

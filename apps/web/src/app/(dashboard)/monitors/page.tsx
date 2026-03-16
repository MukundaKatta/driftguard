"use client";

import { useState } from "react";
import { Header } from "@/components/layout/header";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { driftTypeLabel, formatDate } from "@/lib/utils";
import { Plus, Play, Trash2, Clock, Zap } from "lucide-react";
import useSWR from "swr";
import {
  listMonitors,
  listModels,
  createMonitor,
  deleteMonitor,
  runDriftDetection,
  type Monitor,
} from "@/lib/api";
import { createClient } from "@/lib/supabase";

const DRIFT_TYPES = [
  { value: "data_drift", label: "Data Drift", description: "KS test, PSI, Chi-squared on feature distributions" },
  { value: "embedding_drift", label: "Embedding Drift", description: "Cosine distance, MMD between embedding batches" },
  { value: "response_drift", label: "Response Drift", description: "Distribution shift in model outputs" },
  { value: "confidence_drift", label: "Confidence Drift", description: "Mean confidence score degradation over time" },
  { value: "query_drift", label: "Query Pattern Drift", description: "Clustering shift in input query patterns" },
];

function MonitorCard({
  monitor,
  onRun,
  onDelete,
}: {
  monitor: Monitor;
  onRun: (id: string) => void;
  onDelete: (id: string) => void;
}) {
  const [running, setRunning] = useState(false);

  const handleRun = async () => {
    setRunning(true);
    try {
      await onRun(monitor.id);
    } finally {
      setRunning(false);
    }
  };

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between">
          <div>
            <CardTitle className="text-base">
              {driftTypeLabel(monitor.drift_type)}
            </CardTitle>
            <CardDescription className="mt-1 font-mono text-xs">
              {monitor.model_endpoint_id.slice(0, 8)}...
            </CardDescription>
          </div>
          <Badge
            variant={
              monitor.status === "active"
                ? "success"
                : monitor.status === "paused"
                  ? "warning"
                  : "secondary"
            }
          >
            {monitor.status}
          </Badge>
        </div>
      </CardHeader>
      <CardContent>
        <div className="space-y-3">
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Clock className="h-4 w-4" />
            <span>Every {monitor.schedule_minutes} minutes</span>
          </div>
          {monitor.last_run_at && (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Zap className="h-4 w-4" />
              <span>Last run: {formatDate(monitor.last_run_at)}</span>
            </div>
          )}
          <div className="flex gap-2 pt-2">
            <Button
              size="sm"
              variant="outline"
              onClick={handleRun}
              disabled={running}
            >
              <Play className="mr-1 h-3 w-3" />
              {running ? "Running..." : "Run Now"}
            </Button>
            <Button
              size="sm"
              variant="ghost"
              className="text-red-600 hover:text-red-700"
              onClick={() => onDelete(monitor.id)}
            >
              <Trash2 className="h-3 w-3" />
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function CreateMonitorDialog({
  open,
  onClose,
  onSubmit,
  models,
}: {
  open: boolean;
  onClose: () => void;
  onSubmit: (data: {
    model_endpoint_id: string;
    drift_type: string;
    schedule_minutes: number;
  }) => void;
  models: { id: string; name: string }[];
}) {
  const [modelId, setModelId] = useState("");
  const [driftType, setDriftType] = useState("data_drift");
  const [schedule, setSchedule] = useState(60);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="w-full max-w-lg rounded-lg border bg-card p-6 shadow-xl">
        <h2 className="text-lg font-semibold">Create Drift Monitor</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Configure automated drift detection for a model endpoint.
        </p>
        <div className="mt-4 space-y-4">
          <div>
            <label className="text-sm font-medium">Model Endpoint</label>
            <select
              className="mt-1 w-full rounded-md border bg-background px-3 py-2 text-sm"
              value={modelId}
              onChange={(e) => setModelId(e.target.value)}
            >
              <option value="">Select a model...</option>
              {models.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-sm font-medium">Drift Type</label>
            <div className="mt-2 space-y-2">
              {DRIFT_TYPES.map((dt) => (
                <label
                  key={dt.value}
                  className={`flex cursor-pointer items-start gap-3 rounded-lg border p-3 transition-colors ${
                    driftType === dt.value
                      ? "border-primary bg-primary/5"
                      : "hover:bg-accent"
                  }`}
                >
                  <input
                    type="radio"
                    name="drift_type"
                    value={dt.value}
                    checked={driftType === dt.value}
                    onChange={(e) => setDriftType(e.target.value)}
                    className="mt-1"
                  />
                  <div>
                    <p className="text-sm font-medium">{dt.label}</p>
                    <p className="text-xs text-muted-foreground">
                      {dt.description}
                    </p>
                  </div>
                </label>
              ))}
            </div>
          </div>
          <div>
            <label className="text-sm font-medium">
              Check Interval (minutes)
            </label>
            <input
              type="number"
              className="mt-1 w-full rounded-md border bg-background px-3 py-2 text-sm"
              value={schedule}
              onChange={(e) => setSchedule(Number(e.target.value))}
              min={1}
            />
          </div>
        </div>
        <div className="mt-6 flex justify-end gap-3">
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button
            onClick={() => {
              onSubmit({
                model_endpoint_id: modelId,
                drift_type: driftType,
                schedule_minutes: schedule,
              });
              onClose();
            }}
            disabled={!modelId}
          >
            Create Monitor
          </Button>
        </div>
      </div>
    </div>
  );
}

export default function MonitorsPage() {
  const [showDialog, setShowDialog] = useState(false);
  const supabase = createClient();

  const { data: monitorsData, mutate: mutateMonitors, isLoading } = useSWR(
    "monitors",
    async () => {
      const { data: { session } } = await supabase.auth.getSession();
      if (!session) return { monitors: [] };
      return listMonitors(session.access_token);
    }
  );

  const { data: modelsData } = useSWR("models-for-monitors", async () => {
    const { data: { session } } = await supabase.auth.getSession();
    if (!session) return { models: [] };
    return listModels(session.access_token);
  });

  const handleCreate = async (formData: {
    model_endpoint_id: string;
    drift_type: string;
    schedule_minutes: number;
  }) => {
    const { data: { session } } = await supabase.auth.getSession();
    if (!session) return;
    await createMonitor(formData, session.access_token);
    mutateMonitors();
  };

  const handleRun = async (monitorId: string) => {
    const { data: { session } } = await supabase.auth.getSession();
    if (!session) return;
    await runDriftDetection(monitorId, session.access_token);
    mutateMonitors();
  };

  const handleDelete = async (id: string) => {
    const { data: { session } } = await supabase.auth.getSession();
    if (!session) return;
    await deleteMonitor(id, session.access_token);
    mutateMonitors();
  };

  const monitors = monitorsData?.monitors || [];
  const models = modelsData?.models || [];

  return (
    <div>
      <Header
        title="Drift Monitors"
        description="Active monitors checking for model drift"
        actions={
          <Button onClick={() => setShowDialog(true)}>
            <Plus className="mr-2 h-4 w-4" />
            Create Monitor
          </Button>
        }
      />
      <div className="p-6">
        {isLoading ? (
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {[1, 2, 3].map((i) => (
              <Card key={i} className="animate-pulse">
                <CardHeader>
                  <div className="h-5 w-32 rounded bg-muted" />
                </CardHeader>
                <CardContent>
                  <div className="h-24 rounded bg-muted" />
                </CardContent>
              </Card>
            ))}
          </div>
        ) : monitors.length === 0 ? (
          <Card className="p-12 text-center">
            <div className="mx-auto max-w-sm">
              <h3 className="text-lg font-semibold">No monitors configured</h3>
              <p className="mt-2 text-sm text-muted-foreground">
                Create a drift monitor to start detecting model drift
                automatically.
              </p>
              <Button className="mt-4" onClick={() => setShowDialog(true)}>
                <Plus className="mr-2 h-4 w-4" />
                Create Your First Monitor
              </Button>
            </div>
          </Card>
        ) : (
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {monitors.map((monitor) => (
              <MonitorCard
                key={monitor.id}
                monitor={monitor}
                onRun={handleRun}
                onDelete={handleDelete}
              />
            ))}
          </div>
        )}
      </div>
      <CreateMonitorDialog
        open={showDialog}
        onClose={() => setShowDialog(false)}
        onSubmit={handleCreate}
        models={models}
      />
    </div>
  );
}

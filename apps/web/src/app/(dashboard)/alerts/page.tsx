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
import { formatDate } from "@/lib/utils";
import {
  Plus,
  Trash2,
  CheckCircle,
  XCircle,
  MessageSquare,
  Mail,
  Bell,
  AlertTriangle,
} from "lucide-react";
import useSWR from "swr";
import {
  listAlertConfigs,
  listAlertHistory,
  listModels,
  createAlertConfig,
  deleteAlertConfig,
  type AlertConfig,
  type AlertHistoryItem,
} from "@/lib/api";
import { createClient } from "@/lib/supabase";

const CHANNEL_ICONS: Record<string, React.ElementType> = {
  slack: MessageSquare,
  pagerduty: AlertTriangle,
  email: Mail,
  sns: Bell,
};

function AlertConfigCard({
  config,
  onDelete,
}: {
  config: AlertConfig;
  onDelete: (id: string) => void;
}) {
  const Icon = CHANNEL_ICONS[config.channel] || Bell;

  return (
    <Card>
      <CardContent className="flex items-center justify-between p-4">
        <div className="flex items-center gap-3">
          <div className="rounded-lg bg-primary/10 p-2">
            <Icon className="h-4 w-4 text-primary" />
          </div>
          <div>
            <p className="text-sm font-medium capitalize">{config.channel}</p>
            <p className="truncate text-xs text-muted-foreground" style={{ maxWidth: "200px" }}>
              {config.destination}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Badge
            variant={
              config.severity_threshold === "critical"
                ? "danger"
                : config.severity_threshold === "warning"
                  ? "warning"
                  : "info"
            }
          >
            {config.severity_threshold}+
          </Badge>
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8 text-red-500"
            onClick={() => onDelete(config.id)}
          >
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function AlertHistoryRow({ item }: { item: AlertHistoryItem }) {
  const Icon = CHANNEL_ICONS[item.channel] || Bell;

  return (
    <tr className="border-b">
      <td className="py-3">
        <div className="flex items-center gap-2">
          <Icon className="h-4 w-4 text-muted-foreground" />
          <span className="capitalize">{item.channel}</span>
        </div>
      </td>
      <td className="py-3">
        <Badge
          variant={
            item.severity === "critical"
              ? "danger"
              : item.severity === "warning"
                ? "warning"
                : "info"
          }
        >
          {item.severity}
        </Badge>
      </td>
      <td className="max-w-xs truncate py-3 text-sm">{item.message}</td>
      <td className="py-3">
        {item.success ? (
          <CheckCircle className="h-4 w-4 text-green-500" />
        ) : (
          <XCircle className="h-4 w-4 text-red-500" />
        )}
      </td>
      <td className="py-3 text-sm text-muted-foreground">
        {formatDate(item.created_at)}
      </td>
    </tr>
  );
}

function CreateAlertDialog({
  open,
  onClose,
  onSubmit,
  models,
}: {
  open: boolean;
  onClose: () => void;
  onSubmit: (data: {
    model_endpoint_id: string;
    channel: string;
    destination: string;
    severity_threshold: string;
  }) => void;
  models: { id: string; name: string }[];
}) {
  const [modelId, setModelId] = useState("");
  const [channel, setChannel] = useState("slack");
  const [destination, setDestination] = useState("");
  const [severity, setSeverity] = useState("warning");

  if (!open) return null;

  const placeholders: Record<string, string> = {
    slack: "https://hooks.slack.com/services/...",
    pagerduty: "your-routing-key",
    email: "alerts@company.com",
    sns: "arn:aws:sns:us-east-1:...",
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="w-full max-w-md rounded-lg border bg-card p-6 shadow-xl">
        <h2 className="text-lg font-semibold">Configure Alert</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Set up a notification channel for drift alerts.
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
                <option key={m.id} value={m.id}>{m.name}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-sm font-medium">Channel</label>
            <select
              className="mt-1 w-full rounded-md border bg-background px-3 py-2 text-sm"
              value={channel}
              onChange={(e) => setChannel(e.target.value)}
            >
              <option value="slack">Slack</option>
              <option value="pagerduty">PagerDuty</option>
              <option value="email">Email</option>
              <option value="sns">AWS SNS</option>
            </select>
          </div>
          <div>
            <label className="text-sm font-medium">Destination</label>
            <input
              type="text"
              className="mt-1 w-full rounded-md border bg-background px-3 py-2 text-sm"
              placeholder={placeholders[channel]}
              value={destination}
              onChange={(e) => setDestination(e.target.value)}
            />
          </div>
          <div>
            <label className="text-sm font-medium">Minimum Severity</label>
            <select
              className="mt-1 w-full rounded-md border bg-background px-3 py-2 text-sm"
              value={severity}
              onChange={(e) => setSeverity(e.target.value)}
            >
              <option value="info">Info</option>
              <option value="warning">Warning</option>
              <option value="critical">Critical</option>
            </select>
          </div>
        </div>
        <div className="mt-6 flex justify-end gap-3">
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button
            onClick={() => {
              onSubmit({
                model_endpoint_id: modelId,
                channel,
                destination,
                severity_threshold: severity,
              });
              onClose();
            }}
            disabled={!modelId || !destination}
          >
            Create Alert
          </Button>
        </div>
      </div>
    </div>
  );
}

export default function AlertsPage() {
  const [showDialog, setShowDialog] = useState(false);
  const supabase = createClient();

  const { data: configsData, mutate: mutateConfigs } = useSWR("alert-configs", async () => {
    const { data: { session } } = await supabase.auth.getSession();
    if (!session) return { configs: [] };
    return listAlertConfigs(session.access_token);
  });

  const { data: historyData } = useSWR("alert-history", async () => {
    const { data: { session } } = await supabase.auth.getSession();
    if (!session) return { history: [] };
    return listAlertHistory({ limit: 50 }, session.access_token);
  });

  const { data: modelsData } = useSWR("models-for-alerts", async () => {
    const { data: { session } } = await supabase.auth.getSession();
    if (!session) return { models: [] };
    return listModels(session.access_token);
  });

  const handleCreate = async (formData: {
    model_endpoint_id: string;
    channel: string;
    destination: string;
    severity_threshold: string;
  }) => {
    const { data: { session } } = await supabase.auth.getSession();
    if (!session) return;
    await createAlertConfig(formData, session.access_token);
    mutateConfigs();
  };

  const handleDelete = async (id: string) => {
    const { data: { session } } = await supabase.auth.getSession();
    if (!session) return;
    await deleteAlertConfig(id, session.access_token);
    mutateConfigs();
  };

  const configs = configsData?.configs || [];
  const history = historyData?.history || [];
  const models = modelsData?.models || [];

  return (
    <div>
      <Header
        title="Alerts"
        description="Alert configurations and delivery history"
        actions={
          <Button onClick={() => setShowDialog(true)}>
            <Plus className="mr-2 h-4 w-4" />
            Add Alert
          </Button>
        }
      />
      <div className="p-6">
        {/* Alert configurations */}
        <div>
          <h2 className="text-base font-semibold">Alert Configurations</h2>
          <p className="text-sm text-muted-foreground">
            Active notification channels for drift alerts
          </p>
          <div className="mt-4 grid gap-3 md:grid-cols-2 lg:grid-cols-3">
            {configs.map((config) => (
              <AlertConfigCard key={config.id} config={config} onDelete={handleDelete} />
            ))}
            {configs.length === 0 && (
              <Card className="p-8 text-center md:col-span-2 lg:col-span-3">
                <p className="text-sm text-muted-foreground">
                  No alert configurations. Add one to get notified about drift.
                </p>
              </Card>
            )}
          </div>
        </div>

        {/* Alert history */}
        <Card className="mt-8">
          <CardHeader>
            <CardTitle className="text-base">Alert History</CardTitle>
            <CardDescription>Recent alert deliveries</CardDescription>
          </CardHeader>
          <CardContent>
            {history.length === 0 ? (
              <p className="py-8 text-center text-sm text-muted-foreground">
                No alerts sent yet
              </p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-left text-muted-foreground">
                      <th className="pb-3 font-medium">Channel</th>
                      <th className="pb-3 font-medium">Severity</th>
                      <th className="pb-3 font-medium">Message</th>
                      <th className="pb-3 font-medium">Status</th>
                      <th className="pb-3 font-medium">Date</th>
                    </tr>
                  </thead>
                  <tbody>
                    {history.map((item) => (
                      <AlertHistoryRow key={item.id} item={item} />
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      <CreateAlertDialog
        open={showDialog}
        onClose={() => setShowDialog(false)}
        onSubmit={handleCreate}
        models={models}
      />
    </div>
  );
}

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
import { platformLabel, formatDate } from "@/lib/utils";
import { Plus, MoreVertical, ExternalLink, Trash2 } from "lucide-react";
import useSWR from "swr";
import { listModels, createModel, deleteModel, type ModelEndpoint } from "@/lib/api";
import { createClient } from "@/lib/supabase";

function ModelCard({ model, onDelete }: { model: ModelEndpoint; onDelete: (id: string) => void }) {
  const [showMenu, setShowMenu] = useState(false);

  return (
    <Card className="relative">
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between">
          <div>
            <CardTitle className="text-base">{model.name}</CardTitle>
            <CardDescription className="mt-1">
              {platformLabel(model.platform)}
            </CardDescription>
          </div>
          <div className="flex items-center gap-2">
            <Badge
              variant={model.status === "active" ? "success" : "secondary"}
            >
              {model.status}
            </Badge>
            <div className="relative">
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8"
                onClick={() => setShowMenu(!showMenu)}
              >
                <MoreVertical className="h-4 w-4" />
              </Button>
              {showMenu && (
                <div className="absolute right-0 top-8 z-10 w-48 rounded-md border bg-card p-1 shadow-lg">
                  <button
                    className="flex w-full items-center gap-2 rounded-sm px-3 py-2 text-sm hover:bg-accent"
                    onClick={() => {
                      setShowMenu(false);
                    }}
                  >
                    <ExternalLink className="h-4 w-4" />
                    View Details
                  </button>
                  <button
                    className="flex w-full items-center gap-2 rounded-sm px-3 py-2 text-sm text-red-600 hover:bg-red-50"
                    onClick={() => {
                      onDelete(model.id);
                      setShowMenu(false);
                    }}
                  >
                    <Trash2 className="h-4 w-4" />
                    Delete
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <p className="text-muted-foreground">Endpoint</p>
            <p className="mt-0.5 truncate font-mono text-xs">
              {model.endpoint_url || "N/A"}
            </p>
          </div>
          <div>
            <p className="text-muted-foreground">API Key</p>
            <p className="mt-0.5 font-mono text-xs">
              {model.api_key?.slice(0, 12)}...
            </p>
          </div>
          <div className="col-span-2">
            <p className="text-muted-foreground">Created</p>
            <p className="mt-0.5">{formatDate(model.created_at)}</p>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function RegisterModelDialog({
  open,
  onClose,
  onSubmit,
}: {
  open: boolean;
  onClose: () => void;
  onSubmit: (data: { name: string; platform: string; endpoint_url?: string }) => void;
}) {
  const [name, setName] = useState("");
  const [platform, setPlatform] = useState("openai");
  const [endpointUrl, setEndpointUrl] = useState("");

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="w-full max-w-md rounded-lg border bg-card p-6 shadow-xl">
        <h2 className="text-lg font-semibold">Register Model Endpoint</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Add a new model endpoint to monitor for drift.
        </p>
        <div className="mt-4 space-y-4">
          <div>
            <label className="text-sm font-medium">Name</label>
            <input
              type="text"
              className="mt-1 w-full rounded-md border bg-background px-3 py-2 text-sm"
              placeholder="My Production Model"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          <div>
            <label className="text-sm font-medium">Platform</label>
            <select
              className="mt-1 w-full rounded-md border bg-background px-3 py-2 text-sm"
              value={platform}
              onChange={(e) => setPlatform(e.target.value)}
            >
              <option value="openai">OpenAI</option>
              <option value="bedrock">AWS Bedrock</option>
              <option value="sagemaker">SageMaker</option>
              <option value="custom">Custom</option>
            </select>
          </div>
          <div>
            <label className="text-sm font-medium">Endpoint URL (optional)</label>
            <input
              type="text"
              className="mt-1 w-full rounded-md border bg-background px-3 py-2 text-sm"
              placeholder="https://api.example.com/v1/predict"
              value={endpointUrl}
              onChange={(e) => setEndpointUrl(e.target.value)}
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
                name,
                platform,
                endpoint_url: endpointUrl || undefined,
              });
              setName("");
              setPlatform("openai");
              setEndpointUrl("");
              onClose();
            }}
            disabled={!name}
          >
            Register
          </Button>
        </div>
      </div>
    </div>
  );
}

export default function ModelsPage() {
  const [showDialog, setShowDialog] = useState(false);
  const supabase = createClient();

  const { data, mutate, isLoading } = useSWR("models", async () => {
    const { data: { session } } = await supabase.auth.getSession();
    if (!session) return { models: [] };
    return listModels(session.access_token);
  });

  const handleCreate = async (formData: { name: string; platform: string; endpoint_url?: string }) => {
    const { data: { session } } = await supabase.auth.getSession();
    if (!session) return;
    await createModel(formData, session.access_token);
    mutate();
  };

  const handleDelete = async (id: string) => {
    const { data: { session } } = await supabase.auth.getSession();
    if (!session) return;
    await deleteModel(id, session.access_token);
    mutate();
  };

  const models = data?.models || [];

  return (
    <div>
      <Header
        title="Model Endpoints"
        description="Registered model endpoints being monitored for drift"
        actions={
          <Button onClick={() => setShowDialog(true)}>
            <Plus className="mr-2 h-4 w-4" />
            Register Model
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
                  <div className="h-4 w-24 rounded bg-muted" />
                </CardHeader>
                <CardContent>
                  <div className="h-20 rounded bg-muted" />
                </CardContent>
              </Card>
            ))}
          </div>
        ) : models.length === 0 ? (
          <Card className="p-12 text-center">
            <div className="mx-auto max-w-sm">
              <h3 className="text-lg font-semibold">No models registered</h3>
              <p className="mt-2 text-sm text-muted-foreground">
                Register a model endpoint to start monitoring for drift.
              </p>
              <Button className="mt-4" onClick={() => setShowDialog(true)}>
                <Plus className="mr-2 h-4 w-4" />
                Register Your First Model
              </Button>
            </div>
          </Card>
        ) : (
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {models.map((model) => (
              <ModelCard key={model.id} model={model} onDelete={handleDelete} />
            ))}
          </div>
        )}
      </div>
      <RegisterModelDialog
        open={showDialog}
        onClose={() => setShowDialog(false)}
        onSubmit={handleCreate}
      />
    </div>
  );
}

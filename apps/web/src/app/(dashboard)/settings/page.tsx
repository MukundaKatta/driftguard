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
import { Save, Key, CreditCard, Users, Shield } from "lucide-react";

function ApiKeysSection() {
  const [showKey, setShowKey] = useState(false);

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <Key className="h-5 w-5 text-muted-foreground" />
          <CardTitle className="text-base">API Keys</CardTitle>
        </div>
        <CardDescription>
          Manage API keys for SDK and direct API access
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="space-y-3">
          <div className="flex items-center justify-between rounded-lg border p-3">
            <div>
              <p className="text-sm font-medium">Production Key</p>
              <p className="mt-0.5 font-mono text-xs text-muted-foreground">
                {showKey ? "dg_prod_a1b2c3d4e5f6g7h8i9j0" : "dg_prod_****...****"}
              </p>
            </div>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setShowKey(!showKey)}
              >
                {showKey ? "Hide" : "Show"}
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  navigator.clipboard.writeText("dg_prod_a1b2c3d4e5f6g7h8i9j0");
                }}
              >
                Copy
              </Button>
            </div>
          </div>
          <Button variant="outline" size="sm">
            Generate New Key
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function BillingSection() {
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <CreditCard className="h-5 w-5 text-muted-foreground" />
          <CardTitle className="text-base">Billing & Plan</CardTitle>
        </div>
        <CardDescription>
          Manage your subscription and billing details
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="space-y-4">
          <div className="flex items-center justify-between rounded-lg border p-4">
            <div>
              <div className="flex items-center gap-2">
                <p className="text-sm font-semibold">Pro Plan</p>
                <Badge variant="default">Current</Badge>
              </div>
              <p className="mt-1 text-sm text-muted-foreground">
                Up to 50 model endpoints, unlimited monitors, all drift types
              </p>
            </div>
            <p className="text-2xl font-bold">
              $99<span className="text-sm font-normal text-muted-foreground">/mo</span>
            </p>
          </div>
          <div className="grid gap-3 md:grid-cols-3">
            <div className="rounded-lg border p-3">
              <p className="text-xs text-muted-foreground">Models Used</p>
              <p className="text-lg font-bold">12 / 50</p>
            </div>
            <div className="rounded-lg border p-3">
              <p className="text-xs text-muted-foreground">Drift Checks (Mo)</p>
              <p className="text-lg font-bold">2,847</p>
            </div>
            <div className="rounded-lg border p-3">
              <p className="text-xs text-muted-foreground">Data Ingested</p>
              <p className="text-lg font-bold">1.2 GB</p>
            </div>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" size="sm">
              Manage Subscription
            </Button>
            <Button variant="outline" size="sm">
              View Invoices
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function WorkspaceSection() {
  const [name, setName] = useState("My Workspace");

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <Shield className="h-5 w-5 text-muted-foreground" />
          <CardTitle className="text-base">Workspace</CardTitle>
        </div>
        <CardDescription>
          General workspace settings
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="space-y-4">
          <div>
            <label className="text-sm font-medium">Workspace Name</label>
            <input
              type="text"
              className="mt-1 w-full rounded-md border bg-background px-3 py-2 text-sm"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          <div>
            <label className="text-sm font-medium">Default Alert Severity</label>
            <select className="mt-1 w-full rounded-md border bg-background px-3 py-2 text-sm">
              <option value="info">Info</option>
              <option value="warning">Warning</option>
              <option value="critical">Critical</option>
            </select>
          </div>
          <div>
            <label className="text-sm font-medium">Data Retention (days)</label>
            <input
              type="number"
              className="mt-1 w-full rounded-md border bg-background px-3 py-2 text-sm"
              defaultValue={90}
              min={7}
              max={365}
            />
          </div>
          <Button size="sm">
            <Save className="mr-2 h-4 w-4" />
            Save Changes
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function TeamSection() {
  const members = [
    { name: "You", email: "admin@company.com", role: "Owner" },
    { name: "Jane Smith", email: "jane@company.com", role: "Admin" },
    { name: "Bob Johnson", email: "bob@company.com", role: "Viewer" },
  ];

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <Users className="h-5 w-5 text-muted-foreground" />
          <CardTitle className="text-base">Team Members</CardTitle>
        </div>
        <CardDescription>
          Manage workspace access
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="space-y-3">
          {members.map((member) => (
            <div key={member.email} className="flex items-center justify-between rounded-lg border p-3">
              <div>
                <p className="text-sm font-medium">{member.name}</p>
                <p className="text-xs text-muted-foreground">{member.email}</p>
              </div>
              <Badge variant="secondary">{member.role}</Badge>
            </div>
          ))}
          <Button variant="outline" size="sm">
            Invite Member
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

export default function SettingsPage() {
  return (
    <div>
      <Header
        title="Settings"
        description="Workspace configuration and account settings"
      />
      <div className="space-y-6 p-6">
        <WorkspaceSection />
        <ApiKeysSection />
        <BillingSection />
        <TeamSection />
      </div>
    </div>
  );
}

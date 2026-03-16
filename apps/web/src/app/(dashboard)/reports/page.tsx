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
import { driftTypeLabel, formatScore } from "@/lib/utils";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  Legend,
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  Radar,
} from "recharts";
import { Download, Calendar } from "lucide-react";
import useSWR from "swr";
import { listModels, getDriftReport, type DriftReport, type ModelEndpoint } from "@/lib/api";
import { createClient } from "@/lib/supabase";

const DRIFT_COLORS = ["#6366F1", "#F59E0B", "#EF4444", "#22C55E", "#3B82F6"];
const PIE_COLORS = ["#22C55E", "#EF4444"];

function ReportOverview({ report }: { report: DriftReport }) {
  const driftRatio = report.total_checks > 0
    ? report.drift_detected_count / report.total_checks
    : 0;

  const healthStatus = driftRatio >= 0.5 ? "critical" : driftRatio >= 0.2 ? "warning" : "healthy";

  return (
    <div className="grid gap-4 md:grid-cols-3">
      <Card>
        <CardContent className="p-4 text-center">
          <p className="text-xs text-muted-foreground">Health Status</p>
          <Badge
            variant={
              healthStatus === "critical"
                ? "danger"
                : healthStatus === "warning"
                  ? "warning"
                  : "success"
            }
            className="mt-2 text-sm"
          >
            {healthStatus.toUpperCase()}
          </Badge>
        </CardContent>
      </Card>
      <Card>
        <CardContent className="p-4 text-center">
          <p className="text-xs text-muted-foreground">Total Checks</p>
          <p className="mt-1 text-3xl font-bold">{report.total_checks}</p>
        </CardContent>
      </Card>
      <Card>
        <CardContent className="p-4 text-center">
          <p className="text-xs text-muted-foreground">Drift Detected</p>
          <p className="mt-1 text-3xl font-bold text-red-500">
            {report.drift_detected_count}
          </p>
          <p className="text-xs text-muted-foreground">
            ({(driftRatio * 100).toFixed(1)}%)
          </p>
        </CardContent>
      </Card>
    </div>
  );
}

function DriftTypeBarChart({ report }: { report: DriftReport }) {
  const chartData = Object.entries(report.by_type).map(([type, info], i) => ({
    name: driftTypeLabel(type),
    checks: info.checks,
    drifted: info.drifted,
    avg_score: info.avg_score,
    fill: DRIFT_COLORS[i % DRIFT_COLORS.length],
  }));

  return (
    <ResponsiveContainer width="100%" height={300}>
      <BarChart data={chartData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
        <XAxis dataKey="name" tick={{ fontSize: 11 }} />
        <YAxis tick={{ fontSize: 11 }} />
        <Tooltip
          contentStyle={{
            backgroundColor: "hsl(var(--card))",
            border: "1px solid hsl(var(--border))",
            borderRadius: "8px",
            fontSize: "12px",
          }}
        />
        <Bar dataKey="checks" name="Total Checks" fill="#6366F1" radius={[4, 4, 0, 0]} />
        <Bar dataKey="drifted" name="Drift Detected" fill="#EF4444" radius={[4, 4, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}

function DriftPieChart({ report }: { report: DriftReport }) {
  const data = [
    { name: "Passed", value: report.total_checks - report.drift_detected_count },
    { name: "Drifted", value: report.drift_detected_count },
  ];

  return (
    <ResponsiveContainer width="100%" height={250}>
      <PieChart>
        <Pie
          data={data}
          cx="50%"
          cy="50%"
          innerRadius={60}
          outerRadius={90}
          paddingAngle={2}
          dataKey="value"
          label={({ name, value }) => `${name}: ${value}`}
        >
          {data.map((_, i) => (
            <Cell key={i} fill={PIE_COLORS[i]} />
          ))}
        </Pie>
        <Legend />
        <Tooltip />
      </PieChart>
    </ResponsiveContainer>
  );
}

function DriftRadarChart({ report }: { report: DriftReport }) {
  const chartData = Object.entries(report.by_type).map(([type, info]) => ({
    type: driftTypeLabel(type).replace(" Drift", ""),
    score: info.avg_score,
    fullMark: 1.0,
  }));

  if (chartData.length === 0) return null;

  return (
    <ResponsiveContainer width="100%" height={300}>
      <RadarChart data={chartData}>
        <PolarGrid className="stroke-muted" />
        <PolarAngleAxis dataKey="type" tick={{ fontSize: 11 }} />
        <PolarRadiusAxis angle={30} domain={[0, 1]} tick={{ fontSize: 10 }} />
        <Radar
          name="Avg Score"
          dataKey="score"
          stroke="#6366F1"
          fill="#6366F1"
          fillOpacity={0.3}
        />
        <Tooltip />
      </RadarChart>
    </ResponsiveContainer>
  );
}

export default function ReportsPage() {
  const [selectedModelId, setSelectedModelId] = useState<string>("");
  const [days, setDays] = useState(30);
  const supabase = createClient();

  const { data: modelsData } = useSWR("models-for-reports", async () => {
    const { data: { session } } = await supabase.auth.getSession();
    if (!session) return { models: [] };
    return listModels(session.access_token);
  });

  const models = modelsData?.models || [];

  const { data: report, isLoading } = useSWR(
    selectedModelId ? `report-${selectedModelId}-${days}` : null,
    async () => {
      const { data: { session } } = await supabase.auth.getSession();
      if (!session) return null;
      return getDriftReport(selectedModelId, days, session.access_token);
    }
  );

  return (
    <div>
      <Header
        title="Drift Reports"
        description="Comprehensive drift analysis reports over time"
      />
      <div className="p-6">
        {/* Controls */}
        <div className="flex flex-wrap items-end gap-4">
          <div>
            <label className="text-sm font-medium">Model Endpoint</label>
            <select
              className="mt-1 block w-64 rounded-md border bg-background px-3 py-2 text-sm"
              value={selectedModelId}
              onChange={(e) => setSelectedModelId(e.target.value)}
            >
              <option value="">Select a model...</option>
              {models.map((m: ModelEndpoint) => (
                <option key={m.id} value={m.id}>{m.name}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-sm font-medium">Period</label>
            <div className="mt-1 flex gap-2">
              {[7, 14, 30, 90].map((d) => (
                <Button
                  key={d}
                  variant={days === d ? "default" : "outline"}
                  size="sm"
                  onClick={() => setDays(d)}
                >
                  <Calendar className="mr-1 h-3 w-3" />
                  {d}d
                </Button>
              ))}
            </div>
          </div>
        </div>

        {!selectedModelId ? (
          <Card className="mt-8 p-12 text-center">
            <p className="text-muted-foreground">
              Select a model endpoint to view its drift report.
            </p>
          </Card>
        ) : isLoading ? (
          <div className="mt-8 space-y-4">
            {[1, 2, 3].map((i) => (
              <Card key={i} className="animate-pulse">
                <CardContent className="h-40" />
              </Card>
            ))}
          </div>
        ) : report ? (
          <div className="mt-6 space-y-6">
            <ReportOverview report={report} />

            <div className="grid gap-6 lg:grid-cols-2">
              <Card>
                <CardHeader>
                  <CardTitle className="text-base">Checks by Drift Type</CardTitle>
                  <CardDescription>Total checks vs drift detected per type</CardDescription>
                </CardHeader>
                <CardContent>
                  <DriftTypeBarChart report={report} />
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle className="text-base">Pass/Fail Ratio</CardTitle>
                  <CardDescription>Overall drift detection outcomes</CardDescription>
                </CardHeader>
                <CardContent>
                  <DriftPieChart report={report} />
                </CardContent>
              </Card>
            </div>

            <Card>
              <CardHeader>
                <CardTitle className="text-base">Drift Score Radar</CardTitle>
                <CardDescription>
                  Average drift score by type (0 = no drift, 1 = severe drift)
                </CardDescription>
              </CardHeader>
              <CardContent>
                <DriftRadarChart report={report} />
              </CardContent>
            </Card>

            {/* Detail table */}
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Drift Type Summary</CardTitle>
              </CardHeader>
              <CardContent>
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-left text-muted-foreground">
                      <th className="pb-3 font-medium">Drift Type</th>
                      <th className="pb-3 font-medium">Checks</th>
                      <th className="pb-3 font-medium">Drifted</th>
                      <th className="pb-3 font-medium">Drift Rate</th>
                      <th className="pb-3 font-medium">Avg Score</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(report.by_type).map(([type, info]) => (
                      <tr key={type} className="border-b">
                        <td className="py-3 font-medium">{driftTypeLabel(type)}</td>
                        <td className="py-3">{info.checks}</td>
                        <td className="py-3">{info.drifted}</td>
                        <td className="py-3">
                          {info.checks > 0
                            ? `${((info.drifted / info.checks) * 100).toFixed(1)}%`
                            : "N/A"}
                        </td>
                        <td className="py-3 font-mono">{formatScore(info.avg_score)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </CardContent>
            </Card>
          </div>
        ) : null}
      </div>
    </div>
  );
}

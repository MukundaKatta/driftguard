"use client";

import { useState } from "react";
import { Header } from "@/components/layout/header";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  driftTypeLabel,
  formatDate,
  formatScore,
  getDriftSeverity,
  getDriftSeverityBg,
  getDriftSeverityColor,
} from "@/lib/utils";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  AreaChart,
  Area,
} from "recharts";
import { AlertTriangle, CheckCircle, TrendingUp, Activity } from "lucide-react";
import useSWR from "swr";
import { listDriftResults, type DriftResult } from "@/lib/api";
import { createClient } from "@/lib/supabase";

function DriftScoreChart({ results }: { results: DriftResult[] }) {
  const chartData = [...results]
    .reverse()
    .map((r) => ({
      time: new Date(r.created_at).toLocaleDateString("en-US", {
        month: "short",
        day: "numeric",
        hour: "2-digit",
      }),
      score: r.score,
      drifted: r.is_drifted ? 1 : 0,
    }));

  return (
    <ResponsiveContainer width="100%" height={300}>
      <AreaChart data={chartData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id="scoreGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="hsl(245, 58%, 51%)" stopOpacity={0.3} />
            <stop offset="95%" stopColor="hsl(245, 58%, 51%)" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
        <XAxis dataKey="time" className="text-xs" tick={{ fontSize: 11 }} />
        <YAxis className="text-xs" tick={{ fontSize: 11 }} domain={[0, 1]} />
        <Tooltip
          contentStyle={{
            backgroundColor: "hsl(var(--card))",
            border: "1px solid hsl(var(--border))",
            borderRadius: "8px",
            fontSize: "12px",
          }}
        />
        <Area
          type="monotone"
          dataKey="score"
          stroke="hsl(245, 58%, 51%)"
          fill="url(#scoreGradient)"
          strokeWidth={2}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}

function DriftTypeBreakdown({ results }: { results: DriftResult[] }) {
  const byType: Record<string, { total: number; drifted: number; avgScore: number; scores: number[] }> = {};
  for (const r of results) {
    if (!byType[r.drift_type]) {
      byType[r.drift_type] = { total: 0, drifted: 0, avgScore: 0, scores: [] };
    }
    byType[r.drift_type].total++;
    if (r.is_drifted) byType[r.drift_type].drifted++;
    byType[r.drift_type].scores.push(r.score);
  }
  for (const info of Object.values(byType)) {
    info.avgScore = info.scores.reduce((a, b) => a + b, 0) / info.scores.length;
  }

  return (
    <div className="space-y-3">
      {Object.entries(byType).map(([type, info]) => {
        const severity = getDriftSeverity(info.avgScore);
        return (
          <div
            key={type}
            className={`flex items-center justify-between rounded-lg border p-3 ${getDriftSeverityBg(severity)}`}
          >
            <div>
              <p className="text-sm font-medium">{driftTypeLabel(type)}</p>
              <p className="text-xs text-muted-foreground">
                {info.drifted}/{info.total} checks detected drift
              </p>
            </div>
            <div className="text-right">
              <p className={`text-lg font-bold ${getDriftSeverityColor(severity)}`}>
                {formatScore(info.avgScore)}
              </p>
              <p className="text-xs text-muted-foreground">avg score</p>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function ResultDetailView({ result }: { result: DriftResult }) {
  const severity = getDriftSeverity(result.score);
  const details = result.details;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="max-h-[80vh] w-full max-w-2xl overflow-y-auto rounded-lg border bg-card p-6 shadow-xl">
        <div className="flex items-start justify-between">
          <div>
            <h2 className="text-lg font-semibold">
              {driftTypeLabel(result.drift_type)} Result
            </h2>
            <p className="text-sm text-muted-foreground">
              {formatDate(result.created_at)}
            </p>
          </div>
          <Badge variant={result.is_drifted ? "danger" : "success"}>
            {result.is_drifted ? "DRIFT DETECTED" : "NO DRIFT"}
          </Badge>
        </div>
        <div className="mt-4 grid grid-cols-3 gap-4">
          <div className="rounded-lg bg-muted/50 p-3 text-center">
            <p className="text-xs text-muted-foreground">Score</p>
            <p className={`text-2xl font-bold ${getDriftSeverityColor(severity)}`}>
              {formatScore(result.score)}
            </p>
          </div>
          <div className="rounded-lg bg-muted/50 p-3 text-center">
            <p className="text-xs text-muted-foreground">Type</p>
            <p className="text-sm font-medium">{driftTypeLabel(result.drift_type)}</p>
          </div>
          <div className="rounded-lg bg-muted/50 p-3 text-center">
            <p className="text-xs text-muted-foreground">Monitor</p>
            <p className="truncate font-mono text-xs">{result.monitor_id.slice(0, 12)}...</p>
          </div>
        </div>
        <div className="mt-4">
          <h3 className="text-sm font-semibold">Details</h3>
          <pre className="mt-2 max-h-60 overflow-auto rounded-lg bg-muted/50 p-3 font-mono text-xs">
            {JSON.stringify(details, null, 2)}
          </pre>
        </div>
      </div>
    </div>
  );
}

export default function DriftPage() {
  const [selectedResult, setSelectedResult] = useState<DriftResult | null>(null);
  const supabase = createClient();

  const { data, isLoading } = useSWR("drift-results", async () => {
    const { data: { session } } = await supabase.auth.getSession();
    if (!session) return { results: [] };
    return listDriftResults({ limit: 100 }, session.access_token);
  });

  const results = data?.results || [];
  const driftedCount = results.filter((r) => r.is_drifted).length;
  const latestScore = results[0]?.score ?? 0;

  return (
    <div>
      <Header
        title="Drift Detection"
        description="Real-time drift detection results and analysis"
      />
      <div className="p-6">
        {/* Summary cards */}
        <div className="grid gap-4 md:grid-cols-4">
          <Card>
            <CardContent className="p-4">
              <div className="flex items-center gap-3">
                <div className="rounded-lg bg-blue-500/10 p-2">
                  <Activity className="h-5 w-5 text-blue-500" />
                </div>
                <div>
                  <p className="text-2xl font-bold">{results.length}</p>
                  <p className="text-xs text-muted-foreground">Total Checks</p>
                </div>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4">
              <div className="flex items-center gap-3">
                <div className="rounded-lg bg-red-500/10 p-2">
                  <AlertTriangle className="h-5 w-5 text-red-500" />
                </div>
                <div>
                  <p className="text-2xl font-bold">{driftedCount}</p>
                  <p className="text-xs text-muted-foreground">Drift Detected</p>
                </div>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4">
              <div className="flex items-center gap-3">
                <div className="rounded-lg bg-green-500/10 p-2">
                  <CheckCircle className="h-5 w-5 text-green-500" />
                </div>
                <div>
                  <p className="text-2xl font-bold">{results.length - driftedCount}</p>
                  <p className="text-xs text-muted-foreground">Passed</p>
                </div>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4">
              <div className="flex items-center gap-3">
                <div className="rounded-lg bg-purple-500/10 p-2">
                  <TrendingUp className="h-5 w-5 text-purple-500" />
                </div>
                <div>
                  <p className="text-2xl font-bold">{formatScore(latestScore)}</p>
                  <p className="text-xs text-muted-foreground">Latest Score</p>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        <div className="mt-6 grid gap-6 lg:grid-cols-3">
          {/* Score trend chart */}
          <Card className="lg:col-span-2">
            <CardHeader>
              <CardTitle className="text-base">Drift Score Trend</CardTitle>
              <CardDescription>Score over time across all monitors</CardDescription>
            </CardHeader>
            <CardContent>
              {results.length > 0 ? (
                <DriftScoreChart results={results} />
              ) : (
                <div className="flex h-[300px] items-center justify-center text-sm text-muted-foreground">
                  No drift results yet
                </div>
              )}
            </CardContent>
          </Card>

          {/* Breakdown by type */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">By Drift Type</CardTitle>
              <CardDescription>Average scores per type</CardDescription>
            </CardHeader>
            <CardContent>
              {results.length > 0 ? (
                <DriftTypeBreakdown results={results} />
              ) : (
                <div className="flex h-40 items-center justify-center text-sm text-muted-foreground">
                  No data
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Results table */}
        <Card className="mt-6">
          <CardHeader>
            <CardTitle className="text-base">Recent Results</CardTitle>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <div className="space-y-3">
                {[1, 2, 3, 4, 5].map((i) => (
                  <div key={i} className="h-12 animate-pulse rounded bg-muted" />
                ))}
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-left text-muted-foreground">
                      <th className="pb-3 font-medium">Type</th>
                      <th className="pb-3 font-medium">Status</th>
                      <th className="pb-3 font-medium">Score</th>
                      <th className="pb-3 font-medium">Monitor</th>
                      <th className="pb-3 font-medium">Date</th>
                    </tr>
                  </thead>
                  <tbody>
                    {results.map((result) => {
                      const severity = getDriftSeverity(result.score);
                      return (
                        <tr
                          key={result.id}
                          className="cursor-pointer border-b transition-colors hover:bg-muted/50"
                          onClick={() => setSelectedResult(result)}
                        >
                          <td className="py-3 font-medium">
                            {driftTypeLabel(result.drift_type)}
                          </td>
                          <td className="py-3">
                            <Badge variant={result.is_drifted ? "danger" : "success"}>
                              {result.is_drifted ? "Drifted" : "Normal"}
                            </Badge>
                          </td>
                          <td className={`py-3 font-mono ${getDriftSeverityColor(severity)}`}>
                            {formatScore(result.score)}
                          </td>
                          <td className="py-3 font-mono text-xs text-muted-foreground">
                            {result.monitor_id.slice(0, 8)}...
                          </td>
                          <td className="py-3 text-muted-foreground">
                            {formatDate(result.created_at)}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {selectedResult && (
        <div onClick={() => setSelectedResult(null)}>
          <ResultDetailView result={selectedResult} />
        </div>
      )}
    </div>
  );
}

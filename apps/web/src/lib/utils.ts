import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatDate(date: string | Date): string {
  const d = typeof date === "string" ? new Date(date) : date;
  return d.toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatScore(score: number): string {
  return score.toFixed(4);
}

export function getDriftSeverity(
  score: number
): "safe" | "warning" | "critical" {
  if (score >= 0.7) return "critical";
  if (score >= 0.3) return "warning";
  return "safe";
}

export function getDriftSeverityColor(severity: string): string {
  switch (severity) {
    case "critical":
      return "text-red-500";
    case "warning":
      return "text-amber-500";
    case "safe":
      return "text-green-500";
    case "info":
      return "text-blue-500";
    default:
      return "text-gray-500";
  }
}

export function getDriftSeverityBg(severity: string): string {
  switch (severity) {
    case "critical":
      return "bg-red-500/10 border-red-500/20";
    case "warning":
      return "bg-amber-500/10 border-amber-500/20";
    case "safe":
      return "bg-green-500/10 border-green-500/20";
    case "info":
      return "bg-blue-500/10 border-blue-500/20";
    default:
      return "bg-gray-500/10 border-gray-500/20";
  }
}

export function driftTypeLabel(type: string): string {
  const labels: Record<string, string> = {
    data_drift: "Data Drift",
    embedding_drift: "Embedding Drift",
    response_drift: "Response Drift",
    confidence_drift: "Confidence Drift",
    query_drift: "Query Pattern Drift",
  };
  return labels[type] || type;
}

export function platformLabel(platform: string): string {
  const labels: Record<string, string> = {
    bedrock: "AWS Bedrock",
    sagemaker: "SageMaker",
    openai: "OpenAI",
    custom: "Custom",
  };
  return labels[platform] || platform;
}

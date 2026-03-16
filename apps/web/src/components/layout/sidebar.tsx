"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import {
  Activity,
  AlertTriangle,
  BarChart3,
  Box,
  FileText,
  Settings,
  Shield,
} from "lucide-react";

const navigation = [
  { name: "Models", href: "/models", icon: Box },
  { name: "Monitors", href: "/monitors", icon: Activity },
  { name: "Drift Detection", href: "/drift", icon: BarChart3 },
  { name: "Alerts", href: "/alerts", icon: AlertTriangle },
  { name: "Reports", href: "/reports", icon: FileText },
  { name: "Settings", href: "/settings", icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="fixed inset-y-0 left-0 z-50 w-64 border-r bg-card">
      <div className="flex h-16 items-center gap-2 border-b px-6">
        <Shield className="h-6 w-6 text-primary" />
        <span className="text-lg font-bold">DriftGuard</span>
      </div>
      <nav className="flex flex-col gap-1 p-4">
        {navigation.map((item) => {
          const isActive =
            pathname === item.href || pathname.startsWith(item.href + "/");
          return (
            <Link
              key={item.name}
              href={item.href}
              className={cn(
                "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                isActive
                  ? "bg-primary/10 text-primary"
                  : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
              )}
            >
              <item.icon className="h-4 w-4" />
              {item.name}
            </Link>
          );
        })}
      </nav>
      <div className="absolute bottom-4 left-4 right-4">
        <div className="rounded-lg border bg-muted/50 p-3">
          <p className="text-xs font-medium text-muted-foreground">
            DriftGuard v1.0
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            ML Model Monitoring
          </p>
        </div>
      </div>
    </aside>
  );
}

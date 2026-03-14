"use client";

import { useState, useEffect, useCallback, useMemo } from "react";
import {
  Loader2,
  RefreshCw,
  Bell,
  BellOff,
  AlertCircle,
  AlertTriangle,
  Info,
  CheckCircle2,
  Clock,
} from "lucide-react";
import { Button } from "@components/ui/button";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface AlertsTabProps {
  secret: string;
  apiUrl: string;
  active?: boolean;
}

interface AlertRule {
  name: string;
  description: string;
  severity: "critical" | "warning" | "info";
  state: "firing" | "resolved";
  last_fired: number | null;
  cooldown_seconds: number;
  labels: Record<string, string>;
}

interface FiredAlert {
  rule_name: string;
  severity: "critical" | "warning" | "info";
  message: string;
  timestamp: number;
  labels: Record<string, string>;
  value: unknown;
}

interface AlertSummary {
  total_rules: number;
  firing_count: number;
  firing_rules: AlertRule[];
  recent_alerts_1h: number;
  recent_alerts: FiredAlert[];
}

interface AlertsData {
  summary: AlertSummary;
  rules: AlertRule[];
  history: FiredAlert[];
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const SEVERITY_CONFIG = {
  critical: {
    icon: AlertCircle,
    bg: "bg-red-500/10",
    border: "border-red-500/40",
    text: "text-red-400",
    badge: "bg-red-500/20 text-red-400",
    dot: "bg-red-500",
  },
  warning: {
    icon: AlertTriangle,
    bg: "bg-yellow-500/10",
    border: "border-yellow-500/40",
    text: "text-yellow-400",
    badge: "bg-yellow-500/20 text-yellow-400",
    dot: "bg-yellow-500",
  },
  info: {
    icon: Info,
    bg: "bg-blue-500/10",
    border: "border-blue-500/40",
    text: "text-blue-400",
    badge: "bg-blue-500/20 text-blue-400",
    dot: "bg-blue-500",
  },
};

// ---------------------------------------------------------------------------
// Helper
// ---------------------------------------------------------------------------

function relativeTime(ts: number): string {
  const diff = Date.now() / 1000 - ts;
  if (diff < 60) return `${Math.floor(diff)}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function AlertsTab({ secret, apiUrl, active }: AlertsTabProps) {
  const [data, setData] = useState<AlertsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [view, setView] = useState<"rules" | "history">("rules");

  const headers = useMemo(
    () => ({ "X-Admin-Secret": secret }),
    [secret],
  );

  const fetchAlerts = useCallback(async () => {
    try {
      const res = await fetch(
        `${apiUrl}/api/v1/admin/observability/alerts`,
        { headers },
      );
      if (res.ok) setData(await res.json());
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, [apiUrl, headers]);

  useEffect(() => {
    fetchAlerts();
  }, [fetchAlerts]);

  // Auto-refresh every 30s when active
  useEffect(() => {
    if (!active) return;
    const interval = setInterval(fetchAlerts, 30000);
    return () => clearInterval(interval);
  }, [active, fetchAlerts]);

  if (loading) {
    return (
      <div className="flex items-center gap-2 py-8 justify-center text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />
        Loading alerts...
      </div>
    );
  }

  if (!data) {
    return (
      <div className="py-8 text-center text-sm text-muted-foreground">
        Failed to load alerts data
      </div>
    );
  }

  const { summary, rules, history } = data;

  return (
    <div className="space-y-6">
      {/* Header + controls */}
      <div className="flex items-center justify-between">
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => setView("rules")}
            className={`px-3 py-1.5 text-sm rounded ${
              view === "rules"
                ? "bg-purple-600/20 text-purple-400 border border-purple-500/40"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            Alert Rules ({rules.length})
          </button>
          <button
            type="button"
            onClick={() => setView("history")}
            className={`px-3 py-1.5 text-sm rounded ${
              view === "history"
                ? "bg-purple-600/20 text-purple-400 border border-purple-500/40"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            History ({history.length})
          </button>
        </div>
        <Button variant="outline" size="sm" onClick={fetchAlerts}>
          <RefreshCw className="h-3 w-3 mr-1" />
          Refresh
        </Button>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="rounded-lg border border-border-subtle bg-card p-4">
          <div className="flex items-center justify-between mb-1">
            <span className="text-xs text-muted-foreground uppercase tracking-wider">
              Total Rules
            </span>
            <Bell className="h-4 w-4 text-muted-foreground" />
          </div>
          <span className="text-2xl font-bold text-foreground">
            {summary.total_rules}
          </span>
        </div>

        <div
          className={`rounded-lg border p-4 ${
            summary.firing_count > 0
              ? "border-red-500/40 bg-red-500/5"
              : "border-green-500/40 bg-green-500/5"
          }`}
        >
          <div className="flex items-center justify-between mb-1">
            <span className="text-xs text-muted-foreground uppercase tracking-wider">
              Currently Firing
            </span>
            {summary.firing_count > 0 ? (
              <AlertCircle className="h-4 w-4 text-red-400" />
            ) : (
              <CheckCircle2 className="h-4 w-4 text-green-400" />
            )}
          </div>
          <span
            className={`text-2xl font-bold ${
              summary.firing_count > 0 ? "text-red-400" : "text-green-400"
            }`}
          >
            {summary.firing_count}
          </span>
        </div>

        <div className="rounded-lg border border-border-subtle bg-card p-4">
          <div className="flex items-center justify-between mb-1">
            <span className="text-xs text-muted-foreground uppercase tracking-wider">
              Alerts (1h)
            </span>
            <Clock className="h-4 w-4 text-muted-foreground" />
          </div>
          <span className="text-2xl font-bold text-foreground">
            {summary.recent_alerts_1h}
          </span>
        </div>

        <div className="rounded-lg border border-border-subtle bg-card p-4">
          <div className="flex items-center justify-between mb-1">
            <span className="text-xs text-muted-foreground uppercase tracking-wider">
              Status
            </span>
            {summary.firing_count > 0 ? (
              <span className="h-2 w-2 rounded-full bg-red-500 animate-pulse" />
            ) : (
              <span className="h-2 w-2 rounded-full bg-green-500" />
            )}
          </div>
          <span
            className={`text-lg font-bold ${
              summary.firing_count > 0 ? "text-red-400" : "text-green-400"
            }`}
          >
            {summary.firing_count > 0 ? "Alerting" : "All Clear"}
          </span>
        </div>
      </div>

      {/* Currently firing alerts banner */}
      {summary.firing_rules.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-sm font-medium text-red-400">
            Active Alerts
          </h3>
          {summary.firing_rules.map((rule) => {
            const cfg = SEVERITY_CONFIG[rule.severity];
            const Icon = cfg.icon;
            return (
              <div
                key={rule.name}
                className={`flex items-start gap-3 rounded-lg border p-3 ${cfg.border} ${cfg.bg}`}
              >
                <Icon className={`h-5 w-5 mt-0.5 shrink-0 ${cfg.text}`} />
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <span className={`font-medium text-sm ${cfg.text}`}>
                      {rule.name.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())}
                    </span>
                    <span className={`px-1.5 py-0.5 rounded text-xs ${cfg.badge}`}>
                      {rule.severity}
                    </span>
                  </div>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    {rule.description}
                  </p>
                  {rule.last_fired && (
                    <p className="text-xs text-muted-foreground mt-1">
                      Last fired: {relativeTime(rule.last_fired)}
                    </p>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Alert Rules view */}
      {view === "rules" && (
        <div className="space-y-2">
          <h3 className="text-sm font-medium text-foreground">
            Configured Alert Rules
          </h3>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border-subtle text-muted-foreground text-left">
                  <th className="py-2 px-3">Status</th>
                  <th className="py-2 px-3">Rule</th>
                  <th className="py-2 px-3">Description</th>
                  <th className="py-2 px-3">Severity</th>
                  <th className="py-2 px-3">Component</th>
                  <th className="py-2 px-3">Cooldown</th>
                  <th className="py-2 px-3">Last Fired</th>
                </tr>
              </thead>
              <tbody>
                {rules.map((rule) => {
                  const cfg = SEVERITY_CONFIG[rule.severity];
                  return (
                    <tr
                      key={rule.name}
                      className="border-b border-border-subtle hover:bg-muted/20"
                    >
                      <td className="py-2 px-3">
                        <span className="flex items-center gap-1.5">
                          <span
                            className={`h-2 w-2 rounded-full ${
                              rule.state === "firing"
                                ? `${cfg.dot} animate-pulse`
                                : "bg-green-500"
                            }`}
                          />
                          <span
                            className={`text-xs ${
                              rule.state === "firing"
                                ? cfg.text
                                : "text-green-400"
                            }`}
                          >
                            {rule.state}
                          </span>
                        </span>
                      </td>
                      <td className="py-2 px-3 text-foreground font-medium">
                        {rule.name.replace(/_/g, " ")}
                      </td>
                      <td className="py-2 px-3 text-muted-foreground max-w-xs truncate">
                        {rule.description}
                      </td>
                      <td className="py-2 px-3">
                        <span
                          className={`px-1.5 py-0.5 rounded text-xs ${cfg.badge}`}
                        >
                          {rule.severity}
                        </span>
                      </td>
                      <td className="py-2 px-3 text-muted-foreground">
                        {rule.labels.component || "-"}
                      </td>
                      <td className="py-2 px-3 text-muted-foreground">
                        {rule.cooldown_seconds}s
                      </td>
                      <td className="py-2 px-3 text-muted-foreground">
                        {rule.last_fired
                          ? relativeTime(rule.last_fired)
                          : "Never"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Alert History view */}
      {view === "history" && (
        <div className="space-y-2">
          <h3 className="text-sm font-medium text-foreground">
            Alert History
          </h3>
          {history.length === 0 ? (
            <div className="py-8 text-center text-sm text-muted-foreground">
              No alerts have been fired yet.
            </div>
          ) : (
            <div className="space-y-1">
              {history.map((alert, i) => {
                const cfg = SEVERITY_CONFIG[alert.severity];
                const Icon = cfg.icon;
                return (
                  <div
                    key={`${alert.timestamp}-${i}`}
                    className={`flex items-center gap-3 rounded border p-2.5 ${cfg.border} ${cfg.bg}`}
                  >
                    <Icon className={`h-4 w-4 shrink-0 ${cfg.text}`} />
                    <div className="flex-1 min-w-0">
                      <span className="text-sm text-foreground">
                        {alert.message}
                      </span>
                    </div>
                    <span className={`px-1.5 py-0.5 rounded text-xs shrink-0 ${cfg.badge}`}>
                      {alert.severity}
                    </span>
                    <span className="text-xs text-muted-foreground shrink-0 w-16 text-right">
                      {relativeTime(alert.timestamp)}
                    </span>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* Grafana integration info */}
      <div className="rounded-lg border border-border-subtle bg-card p-4">
        <h3 className="text-sm font-medium text-foreground mb-2">
          Grafana / Prometheus Integration
        </h3>
        <div className="space-y-2 text-xs text-muted-foreground">
          <p>
            Metrics are exported in Prometheus text format at{" "}
            <code className="px-1 py-0.5 rounded bg-muted/50 text-foreground">
              GET /metrics
            </code>
          </p>
          <p>
            Configure your Prometheus scrape config to point to this endpoint.
            Grafana can then query Prometheus for dashboards and alerting.
          </p>
          <div className="rounded bg-muted/30 p-2 font-mono">
            <pre>{`# prometheus.yml
scrape_configs:
  - job_name: 'chatvote-backend'
    scrape_interval: 15s
    static_configs:
      - targets: ['<backend-host>:8080']
    metrics_path: '/metrics'`}</pre>
          </div>
          <p>
            For Scaleway Cockpit (Grafana), use the Prometheus remote write URL
            from your Cockpit dashboard and configure the scrape above.
          </p>
        </div>
      </div>
    </div>
  );
}

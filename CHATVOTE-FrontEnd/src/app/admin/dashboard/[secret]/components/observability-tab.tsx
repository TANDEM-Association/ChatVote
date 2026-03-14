"use client";

import { useState, useEffect, useCallback, useMemo } from "react";
import {
  Loader2,
  RefreshCw,
  Activity,
  Zap,
  Clock,
  AlertTriangle,
  Server,
  Database,
  Cpu,
  ArrowUpRight,
  ArrowDownRight,
} from "lucide-react";
import { Button } from "@components/ui/button";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  LineChart,
  Line,
  AreaChart,
  Area,
  PieChart,
  Pie,
  Cell,
  ResponsiveContainer,
  Legend,
} from "recharts";

// ---------------------------------------------------------------------------
// Props & Types
// ---------------------------------------------------------------------------

interface ObservabilityTabProps {
  secret: string;
  apiUrl: string;
  active?: boolean;
}

interface MetricsSnapshot {
  timestamp: number;
  uptime_seconds: number;
  counters: Record<string, number | Record<string, number>>;
  histograms: Record<string, Record<string, HistogramStats>>;
  gauges: Record<string, number | Record<string, number>>;
  timeseries?: Record<string, TimeseriesPoint[]>;
}

interface HistogramStats {
  count: number;
  sum: number;
  avg: number;
  min: number;
  max: number;
  p50: number;
  p90: number;
  p95: number;
  p99: number;
}

interface TimeseriesPoint {
  t: number;
  v: number;
}

interface TraceStats {
  total_traces: number;
  active_traces: number;
  error_count?: number;
  error_rate: number;
  avg_duration_ms: number;
  p50_duration_ms?: number;
  p95_duration_ms: number;
  p99_duration_ms?: number;
}

interface TraceSummary {
  trace_id: string;
  root_name: string;
  start_time: number;
  duration_ms: number;
  status: string;
  span_count: number;
  attributes: Record<string, string>;
}

interface TraceDetail {
  trace_id: string;
  root_name: string;
  start_time: number;
  end_time: number;
  duration_ms: number;
  status: string;
  spans: SpanDetail[];
  attributes: Record<string, string>;
}

interface SpanDetail {
  span_id: string;
  name: string;
  start_time: number;
  end_time: number;
  duration_ms: number;
  status: string;
  attributes: Record<string, unknown>;
  parent_span_id?: string;
}

// ---------------------------------------------------------------------------
// Theme constants (match charts-tab.tsx)
// ---------------------------------------------------------------------------

const COLORS = {
  purple1: "#7C3AED",
  purple2: "#6D28D9",
  blue: "#818CF8",
  green: "#22c55e",
  red: "#ef4444",
  yellow: "#eab308",
  cyan: "#06b6d4",
  slate: "#94a3b8",
  orange: "#f97316",
};

const TICK_FILL = "#94a3b8";
const GRID_STROKE = "#1e293b";

// ---------------------------------------------------------------------------
// Helper components
// ---------------------------------------------------------------------------

function StatCard({
  label,
  value,
  unit,
  icon: Icon,
  color = "purple",
  trend,
}: {
  label: string;
  value: string | number;
  unit?: string;
  icon: React.ElementType;
  color?: string;
  trend?: "up" | "down" | null;
}) {
  const colorMap: Record<string, string> = {
    purple: "border-purple-500/40",
    green: "border-green-500/40",
    red: "border-red-500/40",
    blue: "border-blue-500/40",
    yellow: "border-yellow-500/40",
    cyan: "border-cyan-500/40",
    orange: "border-orange-500/40",
  };
  return (
    <div
      className={`rounded-lg border bg-card p-4 ${colorMap[color] || colorMap.purple}`}
    >
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs text-muted-foreground uppercase tracking-wider">
          {label}
        </span>
        <Icon className="h-4 w-4 text-muted-foreground" />
      </div>
      <div className="flex items-baseline gap-1">
        <span className="text-2xl font-bold text-foreground">{value}</span>
        {unit && (
          <span className="text-xs text-muted-foreground">{unit}</span>
        )}
        {trend === "up" && (
          <ArrowUpRight className="h-3 w-3 text-green-500 ml-1" />
        )}
        {trend === "down" && (
          <ArrowDownRight className="h-3 w-3 text-red-500 ml-1" />
        )}
      </div>
    </div>
  );
}

function ChartCard({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-lg border border-border-subtle bg-card p-4">
      <h3 className="text-sm font-medium text-foreground mb-3">{title}</h3>
      {children}
    </div>
  );
}

function DarkTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: Array<{ name: string; value: number; color: string }>;
  label?: string;
}) {
  if (!active || !payload) return null;
  return (
    <div className="rounded border border-border-subtle bg-card px-3 py-2 text-xs shadow-lg">
      {label && <p className="text-muted-foreground mb-1">{label}</p>}
      {payload.map((entry, i) => (
        <p key={i} style={{ color: entry.color }}>
          {entry.name}: {typeof entry.value === "number" ? entry.value.toFixed(1) : entry.value}
        </p>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Waterfall trace viewer
// ---------------------------------------------------------------------------

function TraceWaterfall({ trace }: { trace: TraceDetail }) {
  const traceStart = trace.start_time;
  const totalDuration = trace.duration_ms || 1;

  return (
    <div className="space-y-1">
      <div className="flex items-center gap-2 mb-2">
        <span className="text-xs font-mono text-muted-foreground">
          {trace.trace_id}
        </span>
        <span
          className={`px-1.5 py-0.5 rounded text-xs font-medium ${
            trace.status === "error"
              ? "bg-red-500/20 text-red-400"
              : "bg-green-500/20 text-green-400"
          }`}
        >
          {trace.status}
        </span>
        <span className="text-xs text-muted-foreground">
          {trace.duration_ms.toFixed(0)}ms total
        </span>
      </div>
      {trace.spans.map((span) => {
        const offset =
          ((span.start_time - traceStart) * 1000 / totalDuration) * 100;
        const width = Math.max(
          (span.duration_ms / totalDuration) * 100,
          0.5,
        );
        return (
          <div key={span.span_id} className="flex items-center gap-2 h-6">
            <span className="w-40 truncate text-xs text-muted-foreground text-right shrink-0">
              {span.name}
            </span>
            <div className="flex-1 relative h-4 bg-muted/30 rounded">
              <div
                className={`absolute h-full rounded ${
                  span.status === "error" ? "bg-red-500/70" : "bg-purple-500/70"
                }`}
                style={{
                  left: `${Math.min(offset, 99)}%`,
                  width: `${Math.min(width, 100 - offset)}%`,
                }}
                title={`${span.name}: ${span.duration_ms.toFixed(1)}ms`}
              />
            </div>
            <span className="w-16 text-xs text-muted-foreground text-right shrink-0">
              {span.duration_ms.toFixed(0)}ms
            </span>
          </div>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function ObservabilityTab({
  secret,
  apiUrl,
  active,
}: ObservabilityTabProps) {
  const [loading, setLoading] = useState(true);
  const [metricsData, setMetricsData] = useState<MetricsSnapshot | null>(null);
  const [traceStats, setTraceStats] = useState<TraceStats | null>(null);
  const [traces, setTraces] = useState<TraceSummary[]>([]);
  const [activeTraces, setActiveTraces] = useState<TraceSummary[]>([]);
  const [selectedTrace, setSelectedTrace] = useState<TraceDetail | null>(null);
  const [view, setView] = useState<"metrics" | "traces">("metrics");

  // Time-series data for charts
  const [tsResponseTime, setTsResponseTime] = useState<TimeseriesPoint[]>([]);
  const [tsLlmTime, setTsLlmTime] = useState<TimeseriesPoint[]>([]);

  const headers = useMemo(
    () => ({ "X-Admin-Secret": secret }),
    [secret],
  );

  const fetchData = useCallback(async () => {
    try {
      const since = Math.floor(Date.now() / 1000) - 3600; // last 1h of timeseries

      const [metricsRes, tracesRes, tsResponseRes, tsLlmRes] =
        await Promise.all([
          fetch(
            `${apiUrl}/api/v1/admin/observability/metrics`,
            { headers },
          ),
          fetch(
            `${apiUrl}/api/v1/admin/observability/traces?limit=20`,
            { headers },
          ),
          fetch(
            `${apiUrl}/api/v1/admin/observability/timeseries/chat_response_time_ms?since=${since}`,
            { headers },
          ),
          fetch(
            `${apiUrl}/api/v1/admin/observability/timeseries/llm_response_time_ms?since=${since}`,
            { headers },
          ),
        ]);

      if (metricsRes.ok) setMetricsData(await metricsRes.json());
      if (tracesRes.ok) {
        const data = await tracesRes.json();
        setTraceStats(data.stats);
        setTraces(data.traces);
        setActiveTraces(data.active);
      }
      if (tsResponseRes.ok) {
        const data = await tsResponseRes.json();
        setTsResponseTime(data.data || []);
      }
      if (tsLlmRes.ok) {
        const data = await tsLlmRes.json();
        setTsLlmTime(data.data || []);
      }
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, [apiUrl, headers]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Auto-refresh every 10s when active
  useEffect(() => {
    if (!active) return;
    const interval = setInterval(fetchData, 10000);
    return () => clearInterval(interval);
  }, [active, fetchData]);

  const fetchTraceDetail = useCallback(
    async (traceId: string) => {
      try {
        const res = await fetch(
          `${apiUrl}/api/v1/admin/observability/traces/${traceId}`,
          { headers },
        );
        if (res.ok) setSelectedTrace(await res.json());
      } catch {
        // ignore
      }
    },
    [apiUrl, headers],
  );

  if (loading) {
    return (
      <div className="flex items-center gap-2 py-8 justify-center text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />
        Loading observability data...
      </div>
    );
  }

  // Extract counter values helper
  const getCounter = (name: string): number => {
    const val = metricsData?.counters?.[name];
    if (typeof val === "number") return val;
    if (typeof val === "object") {
      return Object.values(val).reduce((a, b) => a + b, 0);
    }
    return 0;
  };

  const getGauge = (name: string): number => {
    const val = metricsData?.gauges?.[name];
    if (typeof val === "number") return val;
    return 0;
  };

  const getHistogram = (name: string): HistogramStats | null => {
    const hist = metricsData?.histograms?.[name];
    if (!hist) return null;
    // Return global stats or first label set
    return hist["global"] || Object.values(hist)[0] || null;
  };

  // Format uptime
  const formatUptime = (s: number) => {
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    return h > 0 ? `${h}h ${m}m` : `${m}m`;
  };

  // Prepare latency distribution data for chart
  const latencyHist = getHistogram("chat_response_time_ms");
  const latencyChartData = latencyHist
    ? [
        { name: "Min", value: latencyHist.min, fill: COLORS.green },
        { name: "P50", value: latencyHist.p50, fill: COLORS.blue },
        { name: "P90", value: latencyHist.p90, fill: COLORS.yellow },
        { name: "P95", value: latencyHist.p95, fill: COLORS.orange },
        { name: "P99", value: latencyHist.p99, fill: COLORS.red },
        { name: "Max", value: latencyHist.max, fill: COLORS.red },
      ]
    : [];

  // Prepare LLM model breakdown
  const llmHist = metricsData?.histograms?.["llm_response_time_ms"] || {};
  const llmModelData = Object.entries(llmHist)
    .filter(([k]) => k !== "global")
    .map(([label, stats]) => ({
      name: label.replace("model=", ""),
      avg: stats.avg,
      p95: stats.p95,
      count: stats.count,
    }));

  // Prepare time-series chart data
  const responseTimeChartData = tsResponseTime.map((p) => ({
    time: new Date(p.t * 1000).toLocaleTimeString("fr-FR", {
      hour: "2-digit",
      minute: "2-digit",
    }),
    value: p.v,
  }));

  // Error rate
  const totalRequests = getCounter("chat_requests_total");
  const totalErrors = getCounter("chat_requests_errors_total");
  const errorRate =
    totalRequests > 0
      ? ((totalErrors / totalRequests) * 100).toFixed(1)
      : "0.0";

  // Cache hit ratio
  const cacheHits = getCounter("rag_cache_hits_total");
  const cacheMisses = getCounter("rag_cache_misses_total");
  const cacheTotal = cacheHits + cacheMisses;
  const cacheHitRate =
    cacheTotal > 0 ? ((cacheHits / cacheTotal) * 100).toFixed(1) : "N/A";

  return (
    <div className="space-y-6">
      {/* View toggle + refresh */}
      <div className="flex items-center justify-between">
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => setView("metrics")}
            className={`px-3 py-1.5 text-sm rounded ${
              view === "metrics"
                ? "bg-purple-600/20 text-purple-400 border border-purple-500/40"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            Metrics
          </button>
          <button
            type="button"
            onClick={() => setView("traces")}
            className={`px-3 py-1.5 text-sm rounded ${
              view === "traces"
                ? "bg-purple-600/20 text-purple-400 border border-purple-500/40"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            Traces
          </button>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => {
            setLoading(true);
            fetchData();
          }}
        >
          <RefreshCw className="h-3 w-3 mr-1" />
          Refresh
        </Button>
      </div>

      {view === "metrics" && (
        <>
          {/* Key stat cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
            <StatCard
              label="Uptime"
              value={formatUptime(metricsData?.uptime_seconds || 0)}
              icon={Server}
              color="green"
            />
            <StatCard
              label="Active Connections"
              value={getGauge("active_connections")}
              icon={Activity}
              color="blue"
            />
            <StatCard
              label="Total Requests"
              value={totalRequests}
              icon={Zap}
              color="purple"
            />
            <StatCard
              label="Error Rate"
              value={`${errorRate}%`}
              icon={AlertTriangle}
              color={Number(errorRate) > 5 ? "red" : "green"}
            />
            <StatCard
              label="Avg Response"
              value={latencyHist?.avg?.toFixed(0) || "0"}
              unit="ms"
              icon={Clock}
              color="cyan"
            />
            <StatCard
              label="Cache Hit Rate"
              value={cacheHitRate === "N/A" ? cacheHitRate : `${cacheHitRate}%`}
              icon={Database}
              color="yellow"
            />
          </div>

          {/* Additional stat cards row */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <StatCard
              label="LLM Requests"
              value={getCounter("llm_requests_total")}
              icon={Cpu}
              color="purple"
            />
            <StatCard
              label="LLM Errors"
              value={getCounter("llm_errors_total")}
              icon={AlertTriangle}
              color={getCounter("llm_errors_total") > 0 ? "red" : "green"}
            />
            <StatCard
              label="LLM Failovers"
              value={getCounter("llm_failovers_total")}
              icon={ArrowUpRight}
              color="orange"
            />
            <StatCard
              label="Active Streams"
              value={getGauge("active_streams")}
              icon={Activity}
              color="cyan"
            />
          </div>

          {/* Charts row */}
          <div className="grid lg:grid-cols-2 gap-4">
            {/* Response time distribution */}
            <ChartCard title="Response Time Distribution (ms)">
              <ResponsiveContainer width="100%" height={250}>
                <BarChart data={latencyChartData} layout="vertical">
                  <CartesianGrid
                    strokeDasharray="3 3"
                    stroke={GRID_STROKE}
                    horizontal={false}
                  />
                  <XAxis
                    type="number"
                    tick={{ fill: TICK_FILL, fontSize: 11 }}
                  />
                  <YAxis
                    dataKey="name"
                    type="category"
                    tick={{ fill: TICK_FILL, fontSize: 11 }}
                    width={40}
                  />
                  <Tooltip content={<DarkTooltip />} />
                  <Bar dataKey="value" name="ms" radius={[0, 4, 4, 0]}>
                    {latencyChartData.map((entry, i) => (
                      <Cell key={i} fill={entry.fill} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </ChartCard>

            {/* Response time over time */}
            <ChartCard title="Response Time Over Time">
              <ResponsiveContainer width="100%" height={250}>
                <AreaChart data={responseTimeChartData}>
                  <CartesianGrid
                    strokeDasharray="3 3"
                    stroke={GRID_STROKE}
                  />
                  <XAxis
                    dataKey="time"
                    tick={{ fill: TICK_FILL, fontSize: 10 }}
                    interval="preserveStartEnd"
                  />
                  <YAxis
                    tick={{ fill: TICK_FILL, fontSize: 11 }}
                    label={{
                      value: "ms",
                      angle: -90,
                      position: "insideLeft",
                      fill: TICK_FILL,
                      fontSize: 11,
                    }}
                  />
                  <Tooltip content={<DarkTooltip />} />
                  <Area
                    type="monotone"
                    dataKey="value"
                    name="Response Time"
                    stroke={COLORS.purple1}
                    fill={COLORS.purple1}
                    fillOpacity={0.2}
                  />
                </AreaChart>
              </ResponsiveContainer>
            </ChartCard>
          </div>

          {/* LLM model breakdown */}
          {llmModelData.length > 0 && (
            <ChartCard title="LLM Response Time by Model">
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={llmModelData}>
                  <CartesianGrid
                    strokeDasharray="3 3"
                    stroke={GRID_STROKE}
                  />
                  <XAxis
                    dataKey="name"
                    tick={{ fill: TICK_FILL, fontSize: 10 }}
                  />
                  <YAxis tick={{ fill: TICK_FILL, fontSize: 11 }} />
                  <Tooltip content={<DarkTooltip />} />
                  <Legend />
                  <Bar
                    dataKey="avg"
                    name="Avg (ms)"
                    fill={COLORS.blue}
                    radius={[4, 4, 0, 0]}
                  />
                  <Bar
                    dataKey="p95"
                    name="P95 (ms)"
                    fill={COLORS.orange}
                    radius={[4, 4, 0, 0]}
                  />
                </BarChart>
              </ResponsiveContainer>
            </ChartCard>
          )}

          {/* RAG pipeline metrics */}
          <div className="grid lg:grid-cols-3 gap-4">
            {["rag_search_time_ms", "rag_rerank_time_ms", "ttfb_ms"].map(
              (metric) => {
                const h = getHistogram(metric);
                const label = metric
                  .replace("_ms", "")
                  .replace(/_/g, " ")
                  .replace(/\b\w/g, (c) => c.toUpperCase());
                return (
                  <ChartCard key={metric} title={label}>
                    <div className="space-y-2">
                      {h && h.count > 0 ? (
                        <>
                          <div className="flex justify-between text-xs text-muted-foreground">
                            <span>Count: {h.count}</span>
                            <span>Avg: {h.avg.toFixed(0)}ms</span>
                          </div>
                          <div className="flex justify-between text-xs text-muted-foreground">
                            <span>P50: {h.p50.toFixed(0)}ms</span>
                            <span>P95: {h.p95.toFixed(0)}ms</span>
                            <span>P99: {h.p99.toFixed(0)}ms</span>
                          </div>
                          <div className="flex justify-between text-xs text-muted-foreground">
                            <span>Min: {h.min.toFixed(0)}ms</span>
                            <span>Max: {h.max.toFixed(0)}ms</span>
                          </div>
                        </>
                      ) : (
                        <p className="text-xs text-muted-foreground">
                          No data yet
                        </p>
                      )}
                    </div>
                  </ChartCard>
                );
              },
            )}
          </div>
        </>
      )}

      {view === "traces" && (
        <>
          {/* Trace stats */}
          {traceStats && (
            <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
              <StatCard
                label="Total Traces"
                value={traceStats.total_traces}
                icon={Activity}
                color="purple"
              />
              <StatCard
                label="Active"
                value={traceStats.active_traces}
                icon={Zap}
                color="blue"
              />
              <StatCard
                label="Error Rate"
                value={`${traceStats.error_rate}%`}
                icon={AlertTriangle}
                color={traceStats.error_rate > 5 ? "red" : "green"}
              />
              <StatCard
                label="Avg Duration"
                value={traceStats.avg_duration_ms.toFixed(0)}
                unit="ms"
                icon={Clock}
                color="cyan"
              />
              <StatCard
                label="P95 Duration"
                value={traceStats.p95_duration_ms.toFixed(0)}
                unit="ms"
                icon={Clock}
                color="orange"
              />
            </div>
          )}

          {/* Active traces */}
          {activeTraces.length > 0 && (
            <div>
              <h3 className="text-sm font-medium text-foreground mb-2">
                Active Traces ({activeTraces.length})
              </h3>
              <div className="space-y-1">
                {activeTraces.map((t) => (
                  <div
                    key={t.trace_id}
                    className="flex items-center gap-3 px-3 py-2 rounded border border-blue-500/30 bg-blue-500/5 text-sm"
                  >
                    <span className="h-2 w-2 rounded-full bg-blue-500 animate-pulse" />
                    <span className="font-mono text-xs text-muted-foreground w-32 truncate">
                      {t.trace_id}
                    </span>
                    <span className="text-foreground">{t.root_name}</span>
                    <span className="text-muted-foreground ml-auto">
                      {t.duration_ms.toFixed(0)}ms
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Trace list */}
          <div>
            <h3 className="text-sm font-medium text-foreground mb-2">
              Recent Traces
            </h3>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border-subtle text-muted-foreground text-left">
                    <th className="py-2 px-2">Time</th>
                    <th className="py-2 px-2">Trace ID</th>
                    <th className="py-2 px-2">Name</th>
                    <th className="py-2 px-2">Spans</th>
                    <th className="py-2 px-2">Duration</th>
                    <th className="py-2 px-2">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {traces.map((t) => (
                    <tr
                      key={t.trace_id}
                      onClick={() => fetchTraceDetail(t.trace_id)}
                      className="border-b border-border-subtle hover:bg-muted/30 cursor-pointer"
                    >
                      <td className="py-2 px-2 text-xs text-muted-foreground whitespace-nowrap">
                        {new Date(t.start_time * 1000).toLocaleTimeString(
                          "fr-FR",
                        )}
                      </td>
                      <td className="py-2 px-2 font-mono text-xs">
                        {t.trace_id}
                      </td>
                      <td className="py-2 px-2 text-foreground">
                        {t.root_name}
                      </td>
                      <td className="py-2 px-2 text-center">{t.span_count}</td>
                      <td className="py-2 px-2 text-right whitespace-nowrap">
                        {t.duration_ms.toFixed(0)}ms
                      </td>
                      <td className="py-2 px-2">
                        <span
                          className={`px-1.5 py-0.5 rounded text-xs ${
                            t.status === "error"
                              ? "bg-red-500/20 text-red-400"
                              : "bg-green-500/20 text-green-400"
                          }`}
                        >
                          {t.status}
                        </span>
                      </td>
                    </tr>
                  ))}
                  {traces.length === 0 && (
                    <tr>
                      <td
                        colSpan={6}
                        className="py-8 text-center text-muted-foreground"
                      >
                        No traces recorded yet. Traces appear when chat
                        requests are processed.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

          {/* Selected trace detail (waterfall) */}
          {selectedTrace && (
            <div className="rounded-lg border border-border-subtle bg-card p-4">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-medium text-foreground">
                  Trace Waterfall: {selectedTrace.root_name}
                </h3>
                <button
                  type="button"
                  onClick={() => setSelectedTrace(null)}
                  className="text-xs text-muted-foreground hover:text-foreground"
                >
                  Close
                </button>
              </div>
              <TraceWaterfall trace={selectedTrace} />
            </div>
          )}
        </>
      )}
    </div>
  );
}

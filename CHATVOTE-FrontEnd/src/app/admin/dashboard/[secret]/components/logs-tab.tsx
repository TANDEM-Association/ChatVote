"use client";

import { useState, useEffect, useCallback, useRef, useMemo } from "react";
import {
  Loader2,
  RefreshCw,
  Search,
  Pause,
  Play,
  ChevronDown,
  ChevronRight,
  Download,
  Filter,
} from "lucide-react";
import { Button } from "@components/ui/button";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface LogsTabProps {
  secret: string;
  apiUrl: string;
  active?: boolean;
}

interface LogEntry {
  timestamp: number;
  time: string;
  level: string;
  logger: string;
  message: string;
  service: string;
  env: string;
  correlation_id?: string;
  source?: {
    file: string;
    line: number;
    function: string;
  };
  data?: Record<string, unknown>;
  exception?: {
    type: string;
    message: string;
    traceback: string;
  };
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const LEVEL_COLORS: Record<string, string> = {
  DEBUG: "text-slate-400 bg-slate-500/10",
  INFO: "text-blue-400 bg-blue-500/10",
  WARNING: "text-yellow-400 bg-yellow-500/10",
  ERROR: "text-red-400 bg-red-500/10",
  CRITICAL: "text-red-300 bg-red-600/20 font-bold",
};

const LEVEL_OPTIONS = ["ALL", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"];

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function LogsTab({ secret, apiUrl, active }: LogsTabProps) {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [selectedLevel, setSelectedLevel] = useState("ALL");
  const [searchQuery, setSearchQuery] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [expandedRows, setExpandedRows] = useState<Set<number>>(new Set());
  const [selectedCorrelationId, setSelectedCorrelationId] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const [isScrolledToBottom, setIsScrolledToBottom] = useState(true);

  const headers = useMemo(
    () => ({ "X-Admin-Secret": secret }),
    [secret],
  );

  const fetchLogs = useCallback(async () => {
    try {
      const params = new URLSearchParams({ limit: "500" });
      if (selectedLevel !== "ALL") params.set("level", selectedLevel);
      if (searchQuery) params.set("search", searchQuery);
      if (selectedCorrelationId)
        params.set("correlation_id", selectedCorrelationId);

      const res = await fetch(
        `${apiUrl}/api/v1/admin/observability/logs?${params}`,
        { headers },
      );
      if (res.ok) {
        const data = await res.json();
        setLogs(data.logs || []);
      }
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, [apiUrl, headers, selectedLevel, searchQuery, selectedCorrelationId]);

  useEffect(() => {
    fetchLogs();
  }, [fetchLogs]);

  // Auto-refresh every 3s when active and auto-refresh enabled
  useEffect(() => {
    if (!active || !autoRefresh) return;
    const interval = setInterval(fetchLogs, 3000);
    return () => clearInterval(interval);
  }, [active, autoRefresh, fetchLogs]);

  // Auto-scroll to bottom when new logs arrive
  useEffect(() => {
    if (isScrolledToBottom && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [logs, isScrolledToBottom]);

  const handleScroll = useCallback(() => {
    if (!scrollRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = scrollRef.current;
    setIsScrolledToBottom(scrollHeight - scrollTop - clientHeight < 50);
  }, []);

  const toggleRow = useCallback((index: number) => {
    setExpandedRows((prev) => {
      const next = new Set(prev);
      if (next.has(index)) next.delete(index);
      else next.add(index);
      return next;
    });
  }, []);

  const handleSearch = useCallback(() => {
    setSearchQuery(searchInput);
  }, [searchInput]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Enter") handleSearch();
    },
    [handleSearch],
  );

  const exportLogs = useCallback(() => {
    const json = JSON.stringify(logs, null, 2);
    const blob = new Blob([json], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `chatvote-logs-${new Date().toISOString().slice(0, 19)}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }, [logs]);

  const clearCorrelationFilter = useCallback(() => {
    setSelectedCorrelationId(null);
  }, []);

  if (loading) {
    return (
      <div className="flex items-center gap-2 py-8 justify-center text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />
        Loading logs...
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {/* Controls bar */}
      <div className="flex flex-wrap items-center gap-2">
        {/* Level filter */}
        <div className="flex items-center gap-1">
          <Filter className="h-3.5 w-3.5 text-muted-foreground" />
          <select
            value={selectedLevel}
            onChange={(e) => setSelectedLevel(e.target.value)}
            className="rounded border border-border-subtle px-2 py-1 text-xs bg-card text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
          >
            {LEVEL_OPTIONS.map((level) => (
              <option key={level} value={level}>
                {level}
              </option>
            ))}
          </select>
        </div>

        {/* Search */}
        <div className="flex items-center gap-1 flex-1 min-w-48">
          <div className="relative flex-1">
            <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
            <input
              type="text"
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Search logs..."
              className="w-full rounded border border-border-subtle bg-card px-7 py-1 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
            />
          </div>
          <Button variant="outline" size="sm" onClick={handleSearch}>
            <Search className="h-3 w-3" />
          </Button>
        </div>

        {/* Correlation ID filter */}
        {selectedCorrelationId && (
          <div className="flex items-center gap-1 rounded border border-purple-500/40 bg-purple-500/10 px-2 py-1 text-xs text-purple-400">
            <span>Corr: {selectedCorrelationId}</span>
            <button
              type="button"
              onClick={clearCorrelationFilter}
              className="hover:text-purple-300 ml-1"
            >
              &times;
            </button>
          </div>
        )}

        <div className="flex items-center gap-1 ml-auto">
          {/* Auto-refresh toggle */}
          <Button
            variant="outline"
            size="sm"
            onClick={() => setAutoRefresh(!autoRefresh)}
            title={autoRefresh ? "Pause auto-refresh" : "Resume auto-refresh"}
          >
            {autoRefresh ? (
              <Pause className="h-3 w-3" />
            ) : (
              <Play className="h-3 w-3" />
            )}
          </Button>

          {/* Export */}
          <Button variant="outline" size="sm" onClick={exportLogs} title="Export logs as JSON">
            <Download className="h-3 w-3" />
          </Button>

          {/* Refresh */}
          <Button variant="outline" size="sm" onClick={fetchLogs}>
            <RefreshCw className="h-3 w-3" />
          </Button>
        </div>
      </div>

      {/* Status bar */}
      <div className="flex items-center gap-3 text-xs text-muted-foreground">
        <span>{logs.length} entries</span>
        {autoRefresh && (
          <span className="flex items-center gap-1">
            <span className="h-1.5 w-1.5 rounded-full bg-green-500 animate-pulse" />
            Live (3s)
          </span>
        )}
      </div>

      {/* Log viewer */}
      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="rounded-lg border border-border-subtle bg-black/30 font-mono text-xs overflow-auto"
        style={{ maxHeight: "calc(100vh - 320px)", minHeight: "400px" }}
      >
        <table className="w-full">
          <thead className="sticky top-0 bg-card/95 backdrop-blur z-10">
            <tr className="border-b border-border-subtle text-left text-muted-foreground">
              <th className="py-1.5 px-2 w-5" />
              <th className="py-1.5 px-2 w-20">Time</th>
              <th className="py-1.5 px-2 w-16">Level</th>
              <th className="py-1.5 px-2 w-32">Logger</th>
              <th className="py-1.5 px-2">Message</th>
              <th className="py-1.5 px-2 w-28">Correlation</th>
            </tr>
          </thead>
          <tbody>
            {logs.map((log, i) => {
              const expanded = expandedRows.has(i);
              const levelClass =
                LEVEL_COLORS[log.level] || LEVEL_COLORS["INFO"];
              const hasDetails =
                log.data || log.exception || log.source;

              return (
                <tr
                  key={`${log.timestamp}-${i}`}
                  className={`border-b border-border-subtle/50 hover:bg-muted/20 ${
                    log.level === "ERROR" || log.level === "CRITICAL"
                      ? "bg-red-500/5"
                      : ""
                  }`}
                >
                  <td className="py-1 px-2">
                    {hasDetails && (
                      <button
                        type="button"
                        onClick={() => toggleRow(i)}
                        className="text-muted-foreground hover:text-foreground"
                      >
                        {expanded ? (
                          <ChevronDown className="h-3 w-3" />
                        ) : (
                          <ChevronRight className="h-3 w-3" />
                        )}
                      </button>
                    )}
                  </td>
                  <td className="py-1 px-2 text-muted-foreground whitespace-nowrap">
                    {log.time?.slice(11, 23) || ""}
                  </td>
                  <td className="py-1 px-2">
                    <span
                      className={`px-1.5 py-0.5 rounded text-xs ${levelClass}`}
                    >
                      {log.level}
                    </span>
                  </td>
                  <td className="py-1 px-2 text-muted-foreground truncate max-w-32">
                    {log.logger?.split(".").pop() || ""}
                  </td>
                  <td className="py-1 px-2 text-foreground">
                    <div className="truncate max-w-xl">{log.message}</div>
                    {/* Expanded details */}
                    {expanded && (
                      <div className="mt-2 mb-1 space-y-2">
                        {/* Source location */}
                        {log.source && (
                          <div className="text-muted-foreground">
                            <span className="text-blue-400">
                              {log.source.file}:{log.source.line}
                            </span>{" "}
                            in{" "}
                            <span className="text-purple-400">
                              {log.source.function}
                            </span>
                          </div>
                        )}
                        {/* Data payload */}
                        {log.data && (
                          <pre className="rounded bg-muted/30 p-2 text-xs overflow-x-auto text-muted-foreground max-h-40 overflow-y-auto">
                            {JSON.stringify(log.data, null, 2)}
                          </pre>
                        )}
                        {/* Exception */}
                        {log.exception && (
                          <div className="rounded border border-red-500/30 bg-red-500/5 p-2">
                            <p className="text-red-400 font-medium">
                              {log.exception.type}: {log.exception.message}
                            </p>
                            <pre className="mt-1 text-xs text-muted-foreground whitespace-pre-wrap max-h-40 overflow-y-auto">
                              {log.exception.traceback}
                            </pre>
                          </div>
                        )}
                      </div>
                    )}
                  </td>
                  <td className="py-1 px-2">
                    {log.correlation_id && (
                      <button
                        type="button"
                        onClick={() =>
                          setSelectedCorrelationId(
                            log.correlation_id === selectedCorrelationId
                              ? null
                              : log.correlation_id!,
                          )
                        }
                        className={`font-mono text-xs truncate max-w-24 block ${
                          log.correlation_id === selectedCorrelationId
                            ? "text-purple-400"
                            : "text-muted-foreground hover:text-purple-400"
                        }`}
                        title={`Filter by correlation ID: ${log.correlation_id}`}
                      >
                        {log.correlation_id}
                      </button>
                    )}
                  </td>
                </tr>
              );
            })}
            {logs.length === 0 && (
              <tr>
                <td
                  colSpan={6}
                  className="py-12 text-center text-muted-foreground"
                >
                  No logs matching filters. Try adjusting the level or search
                  query.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

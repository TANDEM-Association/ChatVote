"use client";

import { useState, useEffect, useCallback, useRef, Fragment } from "react";
import { Loader2, RefreshCw, ChevronDown, ChevronRight } from "lucide-react";
import { Button } from "@components/ui/button";
import ChatDetailPanel from "./chat-detail-panel";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ChatSessionsTabProps {
  secret: string;
  apiUrl: string;
  timeRange: number;
}

interface ChatSession {
  session_id: string;
  municipality_code?: string;
  municipality_name?: string;
  created_at?: string;
  updated_at?: string;
  question_count?: number;
  debug?: {
    response_time_ms?: number;
    source_count?: number;
    model_used?: string;
    status?: "success" | "error" | "partial";
    error_messages?: string[];
    total_tokens?: number;
  };
}

interface SessionsResponse {
  sessions: ChatSession[];
  total: number;
  has_more: boolean;
  offset: number;
  limit: number;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const POLL_INTERVAL_MS = 10_000;
const PAGE_SIZE = 50;

type StatusFilter = "all" | "success" | "error" | "partial";

function StatusDot({ status }: { status?: string }) {
  if (status === "success")
    return <span className="size-2.5 rounded-full bg-green-500 shrink-0" />;
  if (status === "error")
    return <span className="size-2.5 rounded-full bg-red-500/100 shrink-0" />;
  if (status === "partial")
    return <span className="size-2.5 rounded-full bg-yellow-500/100 shrink-0" />;
  return <span className="size-2.5 rounded-full bg-gray-300 shrink-0" />;
}

function formatTime(ts?: string): string {
  if (!ts) return "—";
  return new Date(ts).toLocaleString("fr-FR", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function formatMs(ms?: number): string {
  if (ms === undefined || ms === 0) return "—";
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

// ---------------------------------------------------------------------------
// Chat Sessions Tab
// ---------------------------------------------------------------------------

export default function ChatSessionsTab({
  secret,
  apiUrl,
  timeRange,
}: ChatSessionsTabProps) {
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [offset, setOffset] = useState(0);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [expandedSession, setExpandedSession] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const fetchRef = useRef<() => void>(() => {});

  const fetchSessions = useCallback(
    async (resetOffset = false) => {
      const currentOffset = resetOffset ? 0 : offset;
      try {
        const params = new URLSearchParams({
          limit: String(PAGE_SIZE),
          offset: String(currentOffset),
          order: "desc",
          sort_by: "updated_at",
        });
        if (statusFilter !== "all") params.set("status", statusFilter);
        if (timeRange > 0) {
          const since = new Date(
            Date.now() - timeRange * 60 * 60 * 1000,
          ).toISOString();
          params.set("since", since);
        }

        const res = await fetch(
          `${apiUrl}/api/v1/admin/chat-sessions?${params}`,
          {
            headers: { "X-Admin-Secret": secret },
            cache: "no-store",
          },
        );
        if (!res.ok) throw new Error(`Status ${res.status}`);
        const data: SessionsResponse = await res.json();

        if (resetOffset) {
          setSessions(data.sessions);
          setOffset(0);
        } else {
          setSessions((prev) =>
            currentOffset === 0 ? data.sessions : [...prev, ...data.sessions],
          );
        }
        setHasMore(data.has_more);
        setError(null);
      } catch (err: any) {
        setError(err.message || "Failed to fetch sessions");
      } finally {
        setLoading(false);
      }
    },
    [secret, apiUrl, statusFilter, timeRange, offset],
  );

  // Initial load + filter/timeRange changes
  useEffect(() => {
    setLoading(true);
    setSessions([]);
    setOffset(0);
    fetchSessions(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statusFilter, timeRange, secret, apiUrl]);

  // Polling
  fetchRef.current = () => fetchSessions(true);

  useEffect(() => {
    pollRef.current = setInterval(() => fetchRef.current(), POLL_INTERVAL_MS);
    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, []);

  function loadMore() {
    const next = offset + PAGE_SIZE;
    setOffset(next);
    fetchSessions(false);
  }

  function toggleExpand(sessionId: string) {
    setExpandedSession((prev) => (prev === sessionId ? null : sessionId));
  }

  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2">
          <label
            htmlFor="status-filter"
            className="text-xs font-medium text-muted-foreground"
          >
            Status:
          </label>
          <select
            id="status-filter"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value as StatusFilter)}
            className="rounded border border-border-subtle bg-card px-2.5 py-1.5 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
          >
            <option value="all">All</option>
            <option value="success">Success</option>
            <option value="error">Error</option>
            <option value="partial">Partial</option>
          </select>
        </div>

        <div className="ml-auto flex items-center gap-2">
          {loading && (
            <Loader2 className="size-4 animate-spin text-muted-foreground" />
          )}
          <span className="text-xs text-muted-foreground">
            {sessions.length} session{sessions.length !== 1 ? "s" : ""}
          </span>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => fetchSessions(true)}
            className="h-8 gap-1.5 text-xs"
          >
            <RefreshCw className="size-3.5" />
            Refresh
          </Button>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="rounded-md border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400">
          {error}
        </div>
      )}

      {/* Table */}
      {!loading && sessions.length === 0 && !error && (
        <div className="rounded-xl border border-border-subtle bg-card py-16 text-center text-sm text-muted-foreground">
          No chat sessions found.
        </div>
      )}

      {sessions.length > 0 && (
        <div className="overflow-hidden rounded-xl border border-border-subtle bg-card">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border-subtle text-left bg-background">
                  <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground w-8" />
                  <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                    Timestamp
                  </th>
                  <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                    Session ID
                  </th>
                  <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                    Commune
                  </th>
                  <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground text-right">
                    Sources
                  </th>
                  <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground text-center">
                    Status
                  </th>
                  <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground text-right">
                    Resp. time
                  </th>
                  <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                    Model
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border-subtle">
                {sessions.map((session) => (
                  <Fragment key={session.session_id}>
                    <tr
                      className="cursor-pointer hover:bg-surface-elevated transition-colors"
                      onClick={() => toggleExpand(session.session_id)}
                    >
                      <td className="px-4 py-3 text-muted-foreground">
                        {expandedSession === session.session_id ? (
                          <ChevronDown className="size-3.5" />
                        ) : (
                          <ChevronRight className="size-3.5" />
                        )}
                      </td>
                      <td className="px-4 py-3 text-xs text-muted-foreground whitespace-nowrap">
                        {formatTime(session.updated_at ?? session.created_at)}
                      </td>
                      <td className="px-4 py-3">
                        <span className="font-mono text-xs text-muted-foreground">
                          {session.session_id.slice(0, 12)}…
                        </span>
                      </td>
                      <td className="px-4 py-3 text-xs text-muted-foreground">
                        {session.municipality_name ?? "—"}
                        {session.municipality_code && (
                          <span className="ml-1 font-mono text-[10px] text-muted-foreground">
                            {session.municipality_code}
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-right text-xs text-muted-foreground tabular-nums">
                        {session.debug?.source_count ?? "—"}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center justify-center gap-1.5">
                          <StatusDot status={session.debug?.status} />
                          <span className="text-xs text-muted-foreground">
                            {session.debug?.status ?? "—"}
                          </span>
                        </div>
                      </td>
                      <td className="px-4 py-3 text-right text-xs text-muted-foreground tabular-nums whitespace-nowrap">
                        {formatMs(session.debug?.response_time_ms)}
                      </td>
                      <td className="px-4 py-3 text-xs text-muted-foreground font-mono truncate max-w-[120px]">
                        {session.debug?.model_used ?? "—"}
                      </td>
                    </tr>

                    {expandedSession === session.session_id && (
                      <tr key={`${session.session_id}-detail`}>
                        <td colSpan={8} className="p-0">
                          <ChatDetailPanel
                            sessionId={session.session_id}
                            secret={secret}
                            apiUrl={apiUrl}
                            onClose={() => setExpandedSession(null)}
                          />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>

          {/* Load more */}
          {hasMore && (
            <div className="border-t border-border-subtle px-4 py-3 text-center">
              <Button
                size="sm"
                variant="outline"
                onClick={loadMore}
                className="text-xs"
              >
                Load more
              </Button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

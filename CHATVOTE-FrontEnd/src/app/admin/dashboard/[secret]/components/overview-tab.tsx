"use client";

import { useState, useEffect, useCallback } from "react";
import { Loader2, RefreshCw } from "lucide-react";
import { Button } from "@components/ui/button";
import WarningCard, { type Warning } from "./warning-card";

interface OverviewTabProps {
  secret: string;
  apiUrl: string;
  timeRange: number;
  onWarningCounts: (counts: {
    critical: number;
    warning: number;
    info: number;
  }) => void;
}

interface WarningsResponse {
  data: Warning[];
  ops: Warning[];
  chat: Warning[];
  counts: { critical: number; warning: number; info: number };
}

export default function OverviewTab({
  secret,
  apiUrl,
  timeRange,
  onWarningCounts,
}: OverviewTabProps) {
  const [warnings, setWarnings] = useState<WarningsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchWarnings = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const hoursParam = timeRange > 0 ? `?hours=${timeRange}` : "?hours=8760";
      const res = await fetch(
        `${apiUrl}/api/v1/admin/dashboard/warnings${hoursParam}`,
        {
          headers: { "X-Admin-Secret": secret },
          cache: "no-store",
        },
      );
      if (!res.ok) throw new Error(`Status ${res.status}`);
      const data: WarningsResponse = await res.json();
      setWarnings(data);
      onWarningCounts(data.counts);
    } catch (err: any) {
      setError(err.message || "Failed to fetch warnings");
    } finally {
      setLoading(false);
    }
  }, [secret, apiUrl, timeRange, onWarningCounts]);

  useEffect(() => {
    fetchWarnings();
  }, [fetchWarnings]);

  function handleView(tabLink: string) {
    // Navigate via URL — parent page handles tab switching via URL
    const url = new URL(window.location.href);
    url.searchParams.set("tab", tabLink);
    window.location.href = url.toString();
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="size-5 animate-spin text-muted-foreground" />
        <span className="ml-2 text-sm text-muted-foreground">Loading warnings...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-6 text-center">
        <p className="text-sm text-red-400">{error}</p>
        <Button
          size="sm"
          variant="outline"
          onClick={fetchWarnings}
          className="mt-3"
        >
          Retry
        </Button>
      </div>
    );
  }

  const totalWarnings =
    (warnings?.data.length ?? 0) +
    (warnings?.ops.length ?? 0) +
    (warnings?.chat.length ?? 0);

  return (
    <div className="space-y-6">
      {/* Summary counts */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          {warnings?.counts.critical !== undefined &&
            warnings.counts.critical > 0 && (
              <span className="flex items-center gap-1.5 rounded-full bg-red-500/15 px-3 py-1 text-sm font-medium text-red-400">
                <span className="size-2 rounded-full bg-red-500/100" />
                {warnings.counts.critical} critical
              </span>
            )}
          {warnings?.counts.warning !== undefined &&
            warnings.counts.warning > 0 && (
              <span className="flex items-center gap-1.5 rounded-full bg-yellow-500/15 px-3 py-1 text-sm font-medium text-yellow-400">
                <span className="size-2 rounded-full bg-yellow-500/100" />
                {warnings.counts.warning} warning
              </span>
            )}
          {warnings?.counts.info !== undefined &&
            warnings.counts.info > 0 && (
              <span className="flex items-center gap-1.5 rounded-full bg-blue-500/15 px-3 py-1 text-sm font-medium text-blue-400">
                <span className="size-2 rounded-full bg-blue-500/100" />
                {warnings.counts.info} info
              </span>
            )}
          {totalWarnings === 0 && (
            <span className="text-sm text-muted-foreground">
              No warnings — all systems healthy
            </span>
          )}
        </div>
        <Button
          size="sm"
          variant="ghost"
          onClick={fetchWarnings}
          className="h-8 gap-1.5 text-xs"
        >
          <RefreshCw className="size-3.5" />
          Refresh
        </Button>
      </div>

      {/* Data Completeness */}
      <section>
        <div className="mb-3 flex items-center gap-3">
          <span className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
            Data Completeness
          </span>
          <div className="flex-1 border-t border-border-subtle" />
        </div>
        {warnings?.data.length === 0 ? (
          <p className="text-sm text-muted-foreground italic">No issues detected.</p>
        ) : (
          <div className="space-y-2">
            {warnings?.data.map((w, i) => (
              <WarningCard key={i} warning={w} onView={handleView} />
            ))}
          </div>
        )}
      </section>

      {/* Operational */}
      <section>
        <div className="mb-3 flex items-center gap-3">
          <span className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
            Operational
          </span>
          <div className="flex-1 border-t border-border-subtle" />
        </div>
        {warnings?.ops.length === 0 ? (
          <p className="text-sm text-muted-foreground italic">No issues detected.</p>
        ) : (
          <div className="space-y-2">
            {warnings?.ops.map((w, i) => (
              <WarningCard key={i} warning={w} onView={handleView} />
            ))}
          </div>
        )}
      </section>

      {/* Chat Quality */}
      <section>
        <div className="mb-3 flex items-center gap-3">
          <span className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
            Chat Quality
          </span>
          <div className="flex-1 border-t border-border-subtle" />
        </div>
        {warnings?.chat.length === 0 ? (
          <p className="text-sm text-muted-foreground italic">No issues detected.</p>
        ) : (
          <div className="space-y-2">
            {warnings?.chat.map((w, i) => (
              <WarningCard key={i} warning={w} onView={handleView} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

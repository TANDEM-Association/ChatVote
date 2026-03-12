"use client";

import { useState, useEffect, useCallback } from "react";
import { Loader2, RefreshCw } from "lucide-react";
import { Button } from "@components/ui/button";

import type {
  CoverageResponse,
} from "../../../../api/coverage/route";
import CoverageTablesClient from "../../../../experiment/coverage/coverage-tables-client";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface CoverageTabProps {
  secret: string;
  apiUrl: string;
}

// ---------------------------------------------------------------------------
// Stat Card
// ---------------------------------------------------------------------------

function StatCard({
  value,
  label,
  accentColor,
}: {
  value: number | string;
  label: string;
  accentColor: string;
}) {
  return (
    <div className="overflow-hidden rounded-xl border border-border-subtle bg-card flex-1 min-w-0">
      <div className="h-[3px] w-full" style={{ backgroundColor: accentColor }} />
      <div className="p-4 pt-3">
        <p className="text-2xl font-bold tabular-nums text-foreground leading-none">
          {typeof value === "number" ? value.toLocaleString() : value}
        </p>
        <p className="mt-1 text-xs uppercase tracking-wider text-muted-foreground">
          {label}
        </p>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Coverage Tab
// ---------------------------------------------------------------------------

export default function CoverageTab({ secret, apiUrl }: CoverageTabProps) {
  const [data, setData] = useState<CoverageResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchCoverage = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/coverage`);
      if (!res.ok) throw new Error(`Status ${res.status}`);
      const json: CoverageResponse = await res.json();
      setData(json);
    } catch (err: any) {
      setError(err.message || "Failed to fetch coverage data");
    } finally {
      setLoading(false);
    }
  }, [secret, apiUrl]);

  useEffect(() => {
    fetchCoverage();
  }, [fetchCoverage]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="size-5 animate-spin text-muted-foreground" />
        <span className="ml-2 text-sm text-muted-foreground">
          Loading coverage data...
        </span>
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
          onClick={fetchCoverage}
          className="mt-3"
        >
          Retry
        </Button>
      </div>
    );
  }

  if (!data) return null;

  const { summary, communes, parties, candidates } = data;

  return (
    <div className="space-y-6">
      {/* Summary stats */}
      <div className="flex items-center justify-between">
        <div className="flex gap-3 flex-wrap sm:flex-nowrap flex-1">
          <StatCard value={`${summary.total_communes} / ${summary.total_all_communes?.toLocaleString() ?? "?"}`} label="Scraped Communes" accentColor="#7C3AED" />
          <StatCard value={summary.total_parties} label="Parties" accentColor="#A78BFA" />
          <StatCard value={summary.total_candidates} label="Candidates" accentColor="#94A3B8" />
          <StatCard value={summary.total_lists} label="Electoral Lists" accentColor="#F59E0B" />
          <StatCard value={summary.total_questions} label="Questions" accentColor="#818CF8" />
          <StatCard value={summary.total_chunks} label="Indexed Chunks" accentColor="#6D28D9" />
          <StatCard value={summary.scraped_candidates} label="With Website" accentColor="#22c55e" />
          <StatCard value={summary.indexed_candidates} label="Indexed in RAG" accentColor="#6D28D9" />
        </div>
        <Button
          size="sm"
          variant="ghost"
          onClick={fetchCoverage}
          className="ml-4 h-8 gap-1.5 text-xs shrink-0"
        >
          <RefreshCw className="size-3.5" />
          Refresh
        </Button>
      </div>

      {/* Rich tables with scores, filters, expandable rows */}
      <CoverageTablesClient
        communes={communes}
        parties={parties}
        candidates={candidates}
      />
    </div>
  );
}

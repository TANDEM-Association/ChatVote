"use client";

import { useCallback, useEffect, useState } from "react";

import { Button } from "@components/ui/button";
import { Loader2, RefreshCw } from "lucide-react";

import { type CoverageResponse } from "../../../../api/coverage/route";
import CoverageTablesClient from "./coverage-tables-client";

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
    <div className="border-border-subtle bg-card min-w-0 flex-1 overflow-hidden rounded-xl border">
      <div
        className="h-[3px] w-full"
        style={{ backgroundColor: accentColor }}
      />
      <div className="p-4 pt-3">
        <p className="text-foreground text-2xl leading-none font-bold tabular-nums">
          {typeof value === "number" ? value.toLocaleString() : value}
        </p>
        <p className="text-muted-foreground mt-1 text-xs tracking-wider uppercase">
          {label}
        </p>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Coverage Tab
// ---------------------------------------------------------------------------

export default function CoverageTab({
  secret: _secret,
  apiUrl: _apiUrl,
}: CoverageTabProps) {
  const [data, setData] = useState<CoverageResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchCoverage = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/coverage`, { cache: "no-store" });
      if (!res.ok) throw new Error(`Status ${res.status}`);
      const json: CoverageResponse = await res.json();
      setData(json);
    } catch (err: unknown) {
      setError(
        err instanceof Error ? err.message : "Failed to fetch coverage data",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchCoverage();
  }, [fetchCoverage]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="text-muted-foreground size-5 animate-spin" />
        <span className="text-muted-foreground ml-2 text-sm">
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

  const { summary, communes, parties, candidates, charts } = data;

  return (
    <div className="space-y-6">
      {/* Summary stats */}
      <div className="flex items-center justify-between">
        <div className="flex flex-1 flex-wrap gap-3 sm:flex-nowrap">
          <StatCard
            value={`${summary.total_communes} / ${summary.total_all_communes?.toLocaleString() ?? "?"}`}
            label="Scraped Communes"
            accentColor="#7C3AED"
          />
          <StatCard
            value={summary.total_parties}
            label="Parties"
            accentColor="#A78BFA"
          />
          <StatCard
            value={summary.total_candidates}
            label="Candidates"
            accentColor="#94A3B8"
          />
          <StatCard
            value={summary.total_lists}
            label="Electoral Lists"
            accentColor="#F59E0B"
          />
          <StatCard
            value={summary.total_questions}
            label="Questions"
            accentColor="#818CF8"
          />
          <StatCard
            value={summary.total_chunks}
            label="Indexed Chunks"
            accentColor="#6D28D9"
          />
          <StatCard
            value={summary.scraped_candidates}
            label="With Website"
            accentColor="#22c55e"
          />
          <StatCard
            value={summary.indexed_candidates}
            label="Indexed in RAG"
            accentColor="#6D28D9"
          />
        </div>
        <Button
          size="sm"
          variant="ghost"
          onClick={fetchCoverage}
          className="ml-4 h-8 shrink-0 gap-1.5 text-xs"
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
        coverageByCommune={charts?.coverageByCommune ?? {}}
      />
    </div>
  );
}

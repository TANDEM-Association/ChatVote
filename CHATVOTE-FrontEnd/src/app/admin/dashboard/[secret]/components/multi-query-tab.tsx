"use client";

import { useState, useCallback, useEffect } from "react";
import {
  Search,
  ChevronDown,
  ChevronRight,
  CheckCircle2,
  XCircle,
  Loader2,
  X,
  Clock,
} from "lucide-react";
import { Button } from "@components/ui/button";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface CandidateDetail {
  candidate_id: string;
  candidate_name: string;
  chunk_count: number;
  chunks_preview: string[];
}

interface CommuneResult {
  municipality_code: string;
  municipality_name: string;
  total_candidates: number;
  candidates_with_chunks: number;
  candidates_without_chunks: number;
  manifesto_chunks: number;
  candidate_chunks: number;
  candidate_details: CandidateDetail[];
  elapsed_seconds?: number;
  error?: string;
}

interface AggregateStats {
  communes_with_manifesto: number;
  communes_with_candidates: number;
  communes_with_no_data: number;
  total_manifesto_chunks: number;
  total_candidate_chunks: number;
  avg_manifesto_chunks: number;
  avg_candidate_chunks: number;
  errors: number;
}

interface MultiQueryResult {
  query: string;
  total_communes: number;
  results: CommuneResult[];
  aggregate?: AggregateStats;
}

interface Municipality {
  code: string;
  name: string;
  population: number;
}

interface MultiQueryTabProps {
  secret: string;
  apiUrl: string;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function StatCard({
  label,
  value,
  color,
}: {
  label: string;
  value: number | string;
  color?: "green" | "red" | "yellow";
}) {
  const colorClass =
    color === "green"
      ? "text-green-400"
      : color === "red"
        ? "text-red-400"
        : color === "yellow"
          ? "text-yellow-400"
          : "text-foreground";
  return (
    <div className="rounded-lg border border-border-subtle bg-background p-3">
      <p className={`text-xl font-bold tabular-nums ${colorClass}`}>{value}</p>
      <p className="text-xs uppercase text-muted-foreground mt-1">{label}</p>
    </div>
  );
}

function formatPop(pop: number): string {
  if (pop >= 1_000_000) return `${(pop / 1_000_000).toFixed(1)}M`;
  if (pop >= 1_000) return `${(pop / 1_000).toFixed(0)}k`;
  return String(pop);
}

// ---------------------------------------------------------------------------
// Multi Query Tab
// ---------------------------------------------------------------------------

export default function MultiQueryTab({ secret, apiUrl }: MultiQueryTabProps) {
  const [query, setQuery] = useState(
    "quelles sont les propositions des candidats ?",
  );
  const [scoreThreshold, setScoreThreshold] = useState(0.5);
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState<MultiQueryResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [expandedCommunes, setExpandedCommunes] = useState<Set<string>>(
    new Set(),
  );

  // Commune selector state
  const [allMunicipalities, setAllMunicipalities] = useState<Municipality[]>(
    [],
  );
  const [selectedCodes, setSelectedCodes] = useState<Set<string>>(new Set());
  const [communeSearch, setCommuneSearch] = useState("");
  const [loadingMunicipalities, setLoadingMunicipalities] = useState(false);

  // Fetch municipalities on mount (sorted by population desc from backend)
  useEffect(() => {
    setLoadingMunicipalities(true);
    fetch(`${apiUrl}/api/v1/admin/municipalities`, {
      headers: { "X-Admin-Secret": secret },
    })
      .then((r) => r.json())
      .then((data) => setAllMunicipalities(data.municipalities || []))
      .catch(() => {})
      .finally(() => setLoadingMunicipalities(false));
  }, [apiUrl, secret]);

  const toggleSelect = (code: string) => {
    setSelectedCodes((prev) => {
      const next = new Set(prev);
      if (next.has(code)) next.delete(code);
      else next.add(code);
      return next;
    });
  };

  const selectTopN = (n: number) => {
    // Already sorted by population desc from backend
    const top = allMunicipalities.slice(0, n);
    setSelectedCodes(new Set(top.map((m) => m.code)));
  };

  const selectAll = () =>
    setSelectedCodes(new Set(allMunicipalities.map((m) => m.code)));
  const clearSelection = () => setSelectedCodes(new Set());

  const filteredMunicipalities = communeSearch.trim()
    ? allMunicipalities.filter(
        (m) =>
          m.name.toLowerCase().includes(communeSearch.toLowerCase()) ||
          m.code.includes(communeSearch),
      )
    : allMunicipalities;

  const runQuery = useCallback(async () => {
    setLoading(true);
    setError(null);
    setResults(null);
    setExpandedCommunes(new Set());
    try {
      const body: Record<string, unknown> = {
        query,
        score_threshold: scoreThreshold,
      };
      if (selectedCodes.size > 0) {
        body.municipality_codes = Array.from(selectedCodes);
      }
      const res = await fetch(`${apiUrl}/api/v1/admin/multi-query`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Admin-Secret": secret,
        },
        body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error(`Status ${res.status}`);
      const json: MultiQueryResult = await res.json();
      setResults(json);
    } catch (err: unknown) {
      setError(
        err instanceof Error ? err.message : "Failed to run multi-query",
      );
    } finally {
      setLoading(false);
    }
  }, [apiUrl, secret, query, scoreThreshold, selectedCodes]);

  const toggleCommune = (code: string) => {
    setExpandedCommunes((prev) => {
      const next = new Set(prev);
      if (next.has(code)) next.delete(code);
      else next.add(code);
      return next;
    });
  };

  // Per-candidate summary stats
  const summary = results
    ? {
        totalCommunes: results.total_communes,
        totalCandidates: results.results.reduce(
          (acc, c) => acc + (c.total_candidates || 0),
          0,
        ),
        withChunks: results.results.reduce(
          (acc, c) => acc + (c.candidates_with_chunks || 0),
          0,
        ),
        withoutChunks: results.results.reduce(
          (acc, c) => acc + (c.candidates_without_chunks || 0),
          0,
        ),
      }
    : null;

  const successRate =
    summary && summary.totalCandidates > 0
      ? Math.round((summary.withChunks / summary.totalCandidates) * 100)
      : 0;

  const agg = results?.aggregate;

  return (
    <div className="space-y-4">
      {/* Input section */}
      <div className="rounded-lg border border-border-subtle bg-card p-4 space-y-4">
        <h2 className="text-foreground font-semibold">Multi Query</h2>
        <p className="text-muted-foreground text-sm">
          Run a RAG query against selected communes to check which candidates
          have indexed chunks and what comes back.
        </p>

        <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
          <div className="flex-1 space-y-1">
            <label className="text-xs uppercase text-muted-foreground">
              Query
            </label>
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="w-full rounded border border-border-subtle bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
              placeholder="Enter query..."
            />
          </div>
          <div className="space-y-1 sm:w-40">
            <label className="text-xs uppercase text-muted-foreground">
              Score Threshold
            </label>
            <input
              type="number"
              value={scoreThreshold}
              onChange={(e) => setScoreThreshold(Number(e.target.value))}
              step={0.05}
              min={0}
              max={1}
              className="w-full rounded border border-border-subtle bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
            />
          </div>
          <Button
            onClick={runQuery}
            disabled={loading || !query.trim() || selectedCodes.size === 0}
            className="flex items-center gap-2 shrink-0"
          >
            {loading ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Running...
              </>
            ) : (
              <>
                <Search className="h-4 w-4" />
                Run Query
              </>
            )}
          </Button>
        </div>

        {/* Commune selector */}
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <label className="text-xs uppercase text-muted-foreground">
              Communes{" "}
              {selectedCodes.size > 0
                ? `(${selectedCodes.size} selected)`
                : "(none)"}
            </label>
            <div className="flex items-center gap-2">
              {[10, 20, 50].map((n) => (
                <button
                  key={n}
                  type="button"
                  onClick={() => selectTopN(n)}
                  className="rounded border border-border-subtle px-2.5 py-1 text-xs text-muted-foreground hover:bg-background/60 hover:text-foreground transition-colors"
                >
                  Top {n}
                </button>
              ))}
              <span className="text-border-subtle">|</span>
              <button
                type="button"
                onClick={selectAll}
                className="text-xs text-blue-400 hover:underline"
              >
                All
              </button>
              <button
                type="button"
                onClick={clearSelection}
                className="text-xs text-muted-foreground hover:underline"
              >
                Clear
              </button>
            </div>
          </div>

          {/* Selected chips */}
          {selectedCodes.size > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {Array.from(selectedCodes).map((code) => {
                const muni = allMunicipalities.find((m) => m.code === code);
                return (
                  <span
                    key={code}
                    className="inline-flex items-center gap-1 rounded-full bg-blue-500/20 px-2.5 py-0.5 text-xs text-blue-300"
                  >
                    {muni?.name || code}
                    <button type="button" onClick={() => toggleSelect(code)}>
                      <X className="h-3 w-3" />
                    </button>
                  </span>
                );
              })}
            </div>
          )}

          {/* Search + list */}
          <input
            type="text"
            value={communeSearch}
            onChange={(e) => setCommuneSearch(e.target.value)}
            className="w-full rounded border border-border-subtle bg-background px-3 py-1.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
            placeholder="Search communes..."
          />
          <div className="max-h-40 overflow-y-auto rounded border border-border-subtle bg-background">
            {loadingMunicipalities ? (
              <div className="flex items-center justify-center p-3">
                <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
              </div>
            ) : filteredMunicipalities.length === 0 ? (
              <p className="p-3 text-xs text-muted-foreground">
                No communes found.
              </p>
            ) : (
              filteredMunicipalities.map((m) => (
                <button
                  key={m.code}
                  type="button"
                  onClick={() => toggleSelect(m.code)}
                  className={`flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm transition-colors hover:bg-background/60 ${
                    selectedCodes.has(m.code)
                      ? "bg-blue-500/10 text-blue-300"
                      : "text-foreground"
                  }`}
                >
                  <span
                    className={`h-3.5 w-3.5 shrink-0 rounded border ${
                      selectedCodes.has(m.code)
                        ? "border-blue-400 bg-blue-400"
                        : "border-border-subtle"
                    }`}
                  />
                  <span className="truncate">{m.name}</span>
                  <span className="ml-auto text-xs text-muted-foreground">
                    {m.population ? formatPop(m.population) : ""} · {m.code}
                  </span>
                </button>
              ))
            )}
          </div>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400">
          {error}
        </div>
      )}

      {/* Loading progress */}
      {loading && (
        <div className="rounded-lg border border-border-subtle bg-card p-6 flex items-center justify-center gap-3">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          <span className="text-muted-foreground text-sm">
            Querying {selectedCodes.size} communes...
          </span>
        </div>
      )}

      {/* Results */}
      {results && summary && (
        <div className="space-y-4">
          {/* Aggregate stats (from backend) */}
          {agg && (
            <div className="rounded-lg border border-border-subtle bg-card p-4">
              <h3 className="text-foreground font-semibold mb-3">
                RAG Coverage Stats
              </h3>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-8">
                <StatCard label="Communes" value={results.total_communes} />
                <StatCard
                  label="With Manifesto"
                  value={agg.communes_with_manifesto}
                  color="green"
                />
                <StatCard
                  label="With Candidates"
                  value={agg.communes_with_candidates}
                  color="green"
                />
                <StatCard
                  label="No Data"
                  value={agg.communes_with_no_data}
                  color={agg.communes_with_no_data > 0 ? "red" : undefined}
                />
                <StatCard
                  label="Avg Manifesto"
                  value={agg.avg_manifesto_chunks}
                />
                <StatCard
                  label="Avg Candidate"
                  value={agg.avg_candidate_chunks}
                />
                <StatCard
                  label="Total Chunks"
                  value={
                    agg.total_manifesto_chunks + agg.total_candidate_chunks
                  }
                />
                <StatCard
                  label="Errors"
                  value={agg.errors}
                  color={agg.errors > 0 ? "red" : undefined}
                />
              </div>
            </div>
          )}

          {/* Per-candidate summary */}
          <div className="rounded-lg border border-border-subtle bg-card p-4">
            <h3 className="text-foreground font-semibold mb-3">
              Candidate Coverage
            </h3>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
              <StatCard label="Communes" value={summary.totalCommunes} />
              <StatCard
                label="Total Candidates"
                value={summary.totalCandidates}
              />
              <StatCard
                label="With Chunks"
                value={summary.withChunks}
                color="green"
              />
              <StatCard
                label="Without Chunks"
                value={summary.withoutChunks}
                color={summary.withoutChunks > 0 ? "red" : undefined}
              />
              <StatCard label="Success Rate" value={`${successRate}%`} />
            </div>
          </div>

          {/* Results table */}
          <div className="rounded-lg border border-border-subtle bg-card overflow-hidden">
            <div className="px-4 py-3 border-b border-border-subtle">
              <h3 className="text-foreground font-semibold">
                Results for &ldquo;{results.query}&rdquo;
              </h3>
            </div>
            {/* Table header */}
            <div className="grid grid-cols-[1fr_auto_auto_auto_auto_auto_auto_auto] gap-x-4 px-4 py-2 border-b border-border-subtle bg-background/50">
              <span className="text-xs uppercase text-muted-foreground">
                Commune
              </span>
              <span className="text-xs uppercase text-muted-foreground text-right">
                Candidates
              </span>
              <span className="text-xs uppercase text-muted-foreground text-right">
                With
              </span>
              <span className="text-xs uppercase text-muted-foreground text-right">
                Without
              </span>
              <span className="text-xs uppercase text-muted-foreground text-right">
                Manifesto
              </span>
              <span className="text-xs uppercase text-muted-foreground text-right">
                Candidate
              </span>
              <span className="text-xs uppercase text-muted-foreground text-right">
                Time
              </span>
              <span className="text-xs uppercase text-muted-foreground text-right" />
            </div>

            {/* Rows */}
            <div className="divide-y divide-border-subtle">
              {results.results.map((commune) => {
                const isExpanded = expandedCommunes.has(
                  commune.municipality_code,
                );
                const hasError = !!commune.error;
                const hasNoData =
                  !hasError &&
                  commune.manifesto_chunks === 0 &&
                  commune.candidate_chunks === 0;
                const hasIssues =
                  hasError || hasNoData || commune.candidates_without_chunks > 0;

                return (
                  <div key={commune.municipality_code}>
                    {/* Row */}
                    <button
                      type="button"
                      onClick={() => toggleCommune(commune.municipality_code)}
                      className="w-full grid grid-cols-[1fr_auto_auto_auto_auto_auto_auto_auto] gap-x-4 px-4 py-3 text-left hover:bg-background/40 transition-colors items-center"
                    >
                      <div className="flex items-center gap-2 min-w-0">
                        {hasError ? (
                          <XCircle className="h-4 w-4 shrink-0 text-red-400" />
                        ) : hasNoData ? (
                          <XCircle className="h-4 w-4 shrink-0 text-yellow-400" />
                        ) : hasIssues ? (
                          <XCircle className="h-4 w-4 shrink-0 text-yellow-400" />
                        ) : (
                          <CheckCircle2 className="h-4 w-4 shrink-0 text-green-400" />
                        )}
                        <span className="text-sm text-foreground font-medium truncate">
                          {commune.municipality_name ||
                            commune.municipality_code}
                        </span>
                        <span className="text-xs text-muted-foreground shrink-0">
                          {commune.municipality_code}
                        </span>
                      </div>
                      <span className="text-sm text-foreground tabular-nums text-right">
                        {commune.total_candidates ?? "-"}
                      </span>
                      <span className="text-sm text-green-400 tabular-nums text-right">
                        {commune.candidates_with_chunks ?? "-"}
                      </span>
                      <span
                        className={`text-sm tabular-nums text-right ${(commune.candidates_without_chunks ?? 0) > 0 ? "text-red-400" : "text-muted-foreground"}`}
                      >
                        {commune.candidates_without_chunks ?? "-"}
                      </span>
                      <span
                        className={`text-sm tabular-nums text-right ${commune.manifesto_chunks === 0 ? "text-yellow-400" : "text-muted-foreground"}`}
                      >
                        {commune.manifesto_chunks ?? "-"}
                      </span>
                      <span
                        className={`text-sm tabular-nums text-right ${commune.candidate_chunks === 0 ? "text-yellow-400" : "text-muted-foreground"}`}
                      >
                        {commune.candidate_chunks ?? "-"}
                      </span>
                      <span className="text-sm text-muted-foreground tabular-nums text-right flex items-center justify-end gap-1">
                        <Clock className="h-3 w-3" />
                        {commune.elapsed_seconds != null
                          ? `${commune.elapsed_seconds.toFixed(1)}s`
                          : "-"}
                      </span>
                      <span className="text-muted-foreground">
                        {isExpanded ? (
                          <ChevronDown className="h-4 w-4" />
                        ) : (
                          <ChevronRight className="h-4 w-4" />
                        )}
                      </span>
                    </button>

                    {/* Expanded candidate details */}
                    {isExpanded && (
                      <div className="bg-background/30 border-t border-border-subtle px-4 py-3 space-y-2">
                        {hasError ? (
                          <p className="text-xs text-red-400">
                            Error: {commune.error}
                          </p>
                        ) : commune.candidate_details.length === 0 ? (
                          <p className="text-xs text-muted-foreground">
                            No candidate details available.
                          </p>
                        ) : (
                          commune.candidate_details.map((candidate) => (
                            <div
                              key={candidate.candidate_id}
                              className={`rounded-lg border p-3 space-y-1 ${
                                candidate.chunk_count === 0
                                  ? "border-red-500/30 bg-red-500/5"
                                  : "border-border-subtle bg-card"
                              }`}
                            >
                              <div className="flex items-center justify-between gap-2">
                                <div className="flex items-center gap-2">
                                  {candidate.chunk_count === 0 ? (
                                    <XCircle className="h-3.5 w-3.5 shrink-0 text-red-400" />
                                  ) : (
                                    <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-green-400" />
                                  )}
                                  <span className="text-sm font-medium text-foreground">
                                    {candidate.candidate_name}
                                  </span>
                                  <span className="text-xs text-muted-foreground">
                                    {candidate.candidate_id}
                                  </span>
                                </div>
                                <span
                                  className={`text-xs font-semibold ${candidate.chunk_count === 0 ? "text-red-400" : "text-green-400"}`}
                                >
                                  {candidate.chunk_count} chunk
                                  {candidate.chunk_count !== 1 ? "s" : ""}
                                </span>
                              </div>
                              {candidate.chunks_preview.length > 0 && (
                                <p className="text-xs text-muted-foreground line-clamp-2 pl-5">
                                  {candidate.chunks_preview[0]}
                                </p>
                              )}
                            </div>
                          ))
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

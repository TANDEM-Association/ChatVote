"use client";

import { useState, useCallback, useEffect } from "react";
import { Search, ChevronDown, ChevronRight, CheckCircle2, XCircle, Loader2, X } from "lucide-react";
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
}

interface MultiQueryResult {
  query: string;
  total_communes: number;
  results: CommuneResult[];
}

interface Municipality {
  code: string;
  name: string;
}

interface MultiQueryTabProps {
  secret: string;
  apiUrl: string;
}

// ---------------------------------------------------------------------------
// Multi Query Tab
// ---------------------------------------------------------------------------

export default function MultiQueryTab({ secret, apiUrl }: MultiQueryTabProps) {
  const [query, setQuery] = useState("quels sont les manifestos des candidat");
  const [scoreThreshold, setScoreThreshold] = useState(0.5);
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState<MultiQueryResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [expandedCommunes, setExpandedCommunes] = useState<Set<string>>(new Set());

  // Commune selector state
  const [allMunicipalities, setAllMunicipalities] = useState<Municipality[]>([]);
  const [selectedCodes, setSelectedCodes] = useState<Set<string>>(new Set());
  const [communeSearch, setCommuneSearch] = useState("");
  const [loadingMunicipalities, setLoadingMunicipalities] = useState(false);

  // Fetch municipalities on mount
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

  const selectAll = () => setSelectedCodes(new Set(allMunicipalities.map((m) => m.code)));
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
      const body: Record<string, unknown> = { query, score_threshold: scoreThreshold };
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
      setError(err instanceof Error ? err.message : "Failed to run multi-query");
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

  // Summary stats
  const summary = results
    ? {
        totalCommunes: results.total_communes,
        totalCandidates: results.results.reduce((acc, c) => acc + c.total_candidates, 0),
        withChunks: results.results.reduce((acc, c) => acc + c.candidates_with_chunks, 0),
        withoutChunks: results.results.reduce((acc, c) => acc + c.candidates_without_chunks, 0),
      }
    : null;

  const successRate =
    summary && summary.totalCandidates > 0
      ? Math.round((summary.withChunks / summary.totalCandidates) * 100)
      : 0;

  return (
    <div className="space-y-4">
      {/* Input section */}
      <div className="rounded-lg border border-border-subtle bg-card p-4 space-y-4">
        <h2 className="text-foreground font-semibold">Multi Query</h2>
        <p className="text-muted-foreground text-sm">
          Run a query against selected communes to check which candidates have indexed chunks.
        </p>

        <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
          <div className="flex-1 space-y-1">
            <label className="text-xs uppercase text-muted-foreground">Query</label>
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="w-full rounded border border-border-subtle bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
              placeholder="Enter query..."
            />
          </div>
          <div className="space-y-1 sm:w-40">
            <label className="text-xs uppercase text-muted-foreground">Score Threshold</label>
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
            disabled={loading || !query.trim()}
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
              Communes {selectedCodes.size > 0 ? `(${selectedCodes.size} selected)` : "(all)"}
            </label>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={selectAll}
                className="text-xs text-blue-400 hover:underline"
              >
                Select all
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
              <p className="p-3 text-xs text-muted-foreground">No communes found.</p>
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
                  <span className="ml-auto text-xs text-muted-foreground">{m.code}</span>
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
            Querying {selectedCodes.size || "all"} communes...
          </span>
        </div>
      )}

      {/* Results */}
      {results && summary && (
        <div className="space-y-4">
          {/* Summary bar */}
          <div className="rounded-lg border border-border-subtle bg-card p-4">
            <h3 className="text-foreground font-semibold mb-3">Summary</h3>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
              <div className="rounded-lg border border-border-subtle bg-background p-3">
                <p className="text-xl font-bold tabular-nums text-foreground">{summary.totalCommunes}</p>
                <p className="text-xs uppercase text-muted-foreground mt-1">Communes</p>
              </div>
              <div className="rounded-lg border border-border-subtle bg-background p-3">
                <p className="text-xl font-bold tabular-nums text-foreground">{summary.totalCandidates}</p>
                <p className="text-xs uppercase text-muted-foreground mt-1">Total Candidates</p>
              </div>
              <div className="rounded-lg border border-border-subtle bg-background p-3">
                <p className="text-xl font-bold tabular-nums text-green-400">{summary.withChunks}</p>
                <p className="text-xs uppercase text-muted-foreground mt-1">With Chunks</p>
              </div>
              <div className="rounded-lg border border-border-subtle bg-background p-3">
                <p className="text-xl font-bold tabular-nums text-red-400">{summary.withoutChunks}</p>
                <p className="text-xs uppercase text-muted-foreground mt-1">Without Chunks</p>
              </div>
              <div className="rounded-lg border border-border-subtle bg-background p-3">
                <p className="text-xl font-bold tabular-nums text-foreground">{successRate}%</p>
                <p className="text-xs uppercase text-muted-foreground mt-1">Success Rate</p>
              </div>
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
            <div className="grid grid-cols-[1fr_auto_auto_auto_auto_auto_auto] gap-x-4 px-4 py-2 border-b border-border-subtle bg-background/50">
              <span className="text-xs uppercase text-muted-foreground">Commune</span>
              <span className="text-xs uppercase text-muted-foreground text-right">Candidates</span>
              <span className="text-xs uppercase text-muted-foreground text-right">With Chunks</span>
              <span className="text-xs uppercase text-muted-foreground text-right">Without Chunks</span>
              <span className="text-xs uppercase text-muted-foreground text-right">Manifesto</span>
              <span className="text-xs uppercase text-muted-foreground text-right">Candidate</span>
              <span className="text-xs uppercase text-muted-foreground text-right"></span>
            </div>

            {/* Rows */}
            <div className="divide-y divide-border-subtle">
              {results.results.map((commune) => {
                const isExpanded = expandedCommunes.has(commune.municipality_code);
                const hasIssues = commune.candidates_without_chunks > 0;

                return (
                  <div key={commune.municipality_code}>
                    {/* Row */}
                    <button
                      type="button"
                      onClick={() => toggleCommune(commune.municipality_code)}
                      className="w-full grid grid-cols-[1fr_auto_auto_auto_auto_auto_auto] gap-x-4 px-4 py-3 text-left hover:bg-background/40 transition-colors items-center"
                    >
                      <div className="flex items-center gap-2 min-w-0">
                        {hasIssues ? (
                          <XCircle className="h-4 w-4 shrink-0 text-yellow-400" />
                        ) : (
                          <CheckCircle2 className="h-4 w-4 shrink-0 text-green-400" />
                        )}
                        <span className="text-sm text-foreground font-medium truncate">
                          {commune.municipality_name}
                        </span>
                        <span className="text-xs text-muted-foreground shrink-0">
                          {commune.municipality_code}
                        </span>
                      </div>
                      <span className="text-sm text-foreground tabular-nums text-right">
                        {commune.total_candidates}
                      </span>
                      <span className="text-sm text-green-400 tabular-nums text-right">
                        {commune.candidates_with_chunks}
                      </span>
                      <span className={`text-sm tabular-nums text-right ${commune.candidates_without_chunks > 0 ? "text-red-400" : "text-muted-foreground"}`}>
                        {commune.candidates_without_chunks}
                      </span>
                      <span className="text-sm text-muted-foreground tabular-nums text-right">
                        {commune.manifesto_chunks}
                      </span>
                      <span className="text-sm text-muted-foreground tabular-nums text-right">
                        {commune.candidate_chunks}
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
                        {commune.candidate_details.length === 0 ? (
                          <p className="text-xs text-muted-foreground">No candidate details available.</p>
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
                                <span className={`text-xs font-semibold ${candidate.chunk_count === 0 ? "text-red-400" : "text-green-400"}`}>
                                  {candidate.chunk_count} chunk{candidate.chunk_count !== 1 ? "s" : ""}
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

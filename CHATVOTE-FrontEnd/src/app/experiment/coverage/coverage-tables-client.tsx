"use client";

import { Fragment, useState, useMemo, useRef, useCallback } from "react";

import {
  CheckIcon,
  XIcon,
  ArrowUpDownIcon,
  SearchIcon,
  AlertTriangleIcon,
  FilterIcon,
  ChevronRightIcon,
} from "lucide-react";

import { useVirtualizer } from "@tanstack/react-virtual";

import { type CandidateCoverage, type CommuneCoverage, type PartyCoverage, type ChartAggregations } from "../../api/coverage/route";

type CommuneAggEntry = ChartAggregations["coverageByCommune"][string];

// ---------------------------------------------------------------------------
// Two-score system: Coverage (data completeness) + Ingestion (scrape/index)
// Scores are pre-computed server-side via ChartAggregations.coverageByCommune
// ---------------------------------------------------------------------------

type CommuneWithScore = CommuneCoverage & { coverage: number; ingestion: number };

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type CommuneSortKey = "name" | "population" | "list_count" | "candidate_count" | "question_count" | "coverage" | "ingestion";
type PartySortKey = "name" | "chunk_count";
type CandidateSortKey = "name" | "commune_name" | "party_label";
type SortDir = "asc" | "desc";
type CompletenessFilter = "all" | "complete" | "partial" | "missing";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function CoverageBar({ value, max }: { value: number; max: number }) {
  const pct = max > 0 ? Math.round((value / max) * 100) : 0;
  return (
    <div className="flex items-center gap-2 min-w-0">
      <div className="flex-1 h-2 bg-border-subtle/40 rounded-full overflow-hidden">
        <div
          className="h-full rounded-full"
          style={{
            width: `${pct}%`,
            background: "linear-gradient(90deg, #381AF3, #8B5CF6)",
          }}
        />
      </div>
      <span className="w-8 text-right text-xs text-muted-foreground shrink-0 tabular-nums">
        {value}
      </span>
    </div>
  );
}

function SortButton({
  label,
  active,
  dir,
  onClick,
}: {
  label: string;
  active: boolean;
  dir: SortDir;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex items-center gap-1 text-xs font-semibold uppercase tracking-wider transition-colors ${
        active ? "text-foreground" : "text-muted-foreground hover:text-foreground"
      }`}
    >
      {label}
      <ArrowUpDownIcon
        className={`size-3 shrink-0 ${active ? (dir === "desc" ? "rotate-180" : "") : ""}`}
      />
    </button>
  );
}

function ToggleChip({
  label,
  active,
  onClick,
  count,
  color,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
  count?: number;
  color?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-medium transition-all border ${
        active
          ? "bg-foreground/10 border-foreground/20 text-foreground"
          : "bg-transparent border-border-subtle text-muted-foreground hover:border-foreground/20"
      }`}
    >
      {color && (
        <span
          className="inline-block size-2 rounded-full shrink-0"
          style={{ backgroundColor: color }}
        />
      )}
      {label}
      {count !== undefined && (
        <span className="text-[10px] tabular-nums opacity-60">{count}</span>
      )}
    </button>
  );
}

function getScoreStatus(score: number): CompletenessFilter {
  if (score >= 75) return "complete";
  if (score > 0) return "partial";
  return "missing";
}

// ---------------------------------------------------------------------------
// Warning banner
// ---------------------------------------------------------------------------

function WarningBanner({ warnings }: { warnings: string[] }) {
  if (warnings.length === 0) return null;
  return (
    <div className="bg-amber-500/10 border border-amber-500/20 rounded-lg px-4 py-3 flex gap-3">
      <AlertTriangleIcon className="size-4 text-amber-500 shrink-0 mt-0.5" />
      <div className="space-y-1">
        {warnings.map((w) => (
          <p key={w} className="text-xs text-amber-200/80">{w}</p>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Communes table
// ---------------------------------------------------------------------------

function ScoreBar({ score, gradient }: { score: number; gradient?: string }) {
  const color = gradient ?? (score >= 75 ? "#22c55e" : score > 0 ? "#eab308" : "#ef4444");
  return (
    <div className="flex items-center gap-2 min-w-0">
      <div className="flex-1 h-2 bg-border-subtle/40 rounded-full overflow-hidden">
        <div
          className="h-full rounded-full transition-all"
          style={{ width: `${score}%`, backgroundColor: color }}
        />
      </div>
      <span className="w-8 text-right text-xs text-muted-foreground shrink-0 tabular-nums">
        {score}%
      </span>
    </div>
  );
}

function ScoreBreakdown({
  commune,
  agg,
}: {
  commune: CommuneWithScore;
  agg: CommuneAggEntry | undefined;
}) {
  const total = agg?.total ?? 0;
  const withWebsite = agg?.hasWebsite ?? 0;
  const withManifesto = agg?.hasManifesto ?? 0;
  const withScraped = agg?.hasScraped ?? 0;
  const withIndexed = agg?.hasIndexed ?? 0;

  const coverageItems = [
    {
      label: "Electoral lists",
      ok: commune.list_count > 0,
      detail: commune.list_count > 0 ? `${commune.list_count} lists` : "missing",
      pct: commune.list_count > 0 ? 100 : 0,
    },
    {
      label: "Candidates with website",
      ok: total > 0 && withWebsite === total,
      detail: total > 0 ? `${withWebsite} / ${total}` : "—",
      pct: total > 0 ? Math.round(100 * (withWebsite / total)) : 0,
    },
    {
      label: "Candidates with profession de foi",
      ok: total > 0 && withManifesto === total,
      detail: total > 0 ? `${withManifesto} / ${total}` : "—",
      pct: total > 0 ? Math.round(100 * (withManifesto / total)) : 0,
    },
  ];

  const ingestionItems = [
    {
      label: "Scraped successfully",
      ok: withWebsite > 0 && withScraped === withWebsite,
      detail: withWebsite > 0 ? `${withScraped} / ${withWebsite}` : "—",
      pct: withWebsite > 0 ? Math.round(100 * (withScraped / withWebsite)) : 0,
    },
    {
      label: "Indexed in RAG",
      ok: withWebsite > 0 && withIndexed >= withWebsite,
      detail: withWebsite > 0 ? `${withIndexed} / ${withWebsite}` : "—",
      pct: withWebsite > 0 ? Math.round(100 * (withIndexed / withWebsite)) : 0,
    },
  ];

  function renderItems(items: typeof coverageItems) {
    return (
      <div className="grid grid-cols-2 gap-x-8 gap-y-1.5">
        {items.map((item) => (
          <div key={item.label} className="flex items-center gap-2 text-xs">
            {item.ok ? (
              <CheckIcon className="size-3.5 text-green-500 shrink-0" />
            ) : item.pct > 0 ? (
              <span className="size-3.5 shrink-0 text-center text-yellow-500 font-bold">~</span>
            ) : (
              <XIcon className="size-3.5 text-red-400 shrink-0" />
            )}
            <span className="text-muted-foreground">{item.label}</span>
            <span className="ml-auto tabular-nums text-foreground font-medium">
              {item.pct}%
            </span>
            <span className="text-muted-foreground/60 w-16 text-right">{item.detail}</span>
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="px-8 py-4 space-y-4">
      {/* Coverage breakdown */}
      <div>
        <div className="flex items-center gap-2 mb-2">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
            Coverage
          </p>
          <span className="text-[11px] tabular-nums font-medium text-blue-400">{commune.coverage}%</span>
        </div>
        {renderItems(coverageItems)}
      </div>

      {/* Ingestion breakdown */}
      <div>
        <div className="flex items-center gap-2 mb-2">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
            Ingestion
          </p>
          <span className="text-[11px] tabular-nums font-medium text-violet-400">{commune.ingestion}%</span>
        </div>
        {renderItems(ingestionItems)}
      </div>

      {total > 0 && (
        <p className="text-[11px] text-muted-foreground/60">
          {total} candidates — {withWebsite} with website · {withManifesto} with manifesto · {withIndexed} indexed in RAG
        </p>
      )}
    </div>
  );
}

function CommunesTable({
  communes,
  coverageByCommune,
}: {
  communes: CommuneCoverage[];
  coverageByCommune: ChartAggregations["coverageByCommune"];
}) {
  const [sortKey, setSortKey] = useState<CommuneSortKey>("coverage");
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  const [statusFilter, setStatusFilter] = useState<CompletenessFilter>("all");
  const [hideEmpty, setHideEmpty] = useState(false);
  const [expandedCode, setExpandedCode] = useState<string | null>(null);

  const scrollContainerRef = useRef<HTMLDivElement>(null);

  // Use pre-computed scores from server-side aggregates
  const communesWithScores: CommuneWithScore[] = useMemo(() => {
    return communes.map((c) => {
      const agg = coverageByCommune[c.code];
      return {
        ...c,
        coverage: agg?.score ?? 0,
        ingestion: agg?.ingestionScore ?? 0,
      };
    });
  }, [communes, coverageByCommune]);

  const counts = useMemo(() => {
    let complete = 0, partial = 0, missing = 0;
    for (const c of communesWithScores) {
      const s = getScoreStatus(c.coverage);
      if (s === "complete") complete++;
      else if (s === "partial") partial++;
      else missing++;
    }
    return { complete, partial, missing };
  }, [communesWithScores]);

  const filtered = useMemo(() => {
    return communesWithScores.filter((c) => {
      if (hideEmpty && c.list_count === 0 && c.candidate_count === 0 && c.question_count === 0) {
        return false;
      }
      if (statusFilter !== "all" && getScoreStatus(c.coverage) !== statusFilter) {
        return false;
      }
      return true;
    });
  }, [communesWithScores, statusFilter, hideEmpty]);

  const maxQuestions = Math.max(...filtered.map((c) => c.question_count), 1);
  const maxLists = Math.max(...filtered.map((c) => c.list_count), 1);
  const maxCandidates = Math.max(...filtered.map((c) => c.candidate_count), 1);

  function handleSort(key: CommuneSortKey) {
    if (sortKey === key) {
      setSortDir((d) => (d === "desc" ? "asc" : "desc"));
    } else {
      setSortKey(key);
      setSortDir("desc");
    }
  }

  const sorted = [...filtered].sort((a, b) => {
    const mul = sortDir === "desc" ? -1 : 1;
    if (sortKey === "name") return mul * a.name.localeCompare(b.name);
    if (sortKey === "coverage") return mul * (a.coverage - b.coverage);
    if (sortKey === "ingestion") return mul * (a.ingestion - b.ingestion);
    return mul * (a[sortKey] - b[sortKey]);
  });

  // estimateSize returns a larger value for expanded rows so the virtualizer
  // reserves space and avoids layout jumps when the panel opens.
  const rowVirtualizer = useVirtualizer({
    count: sorted.length,
    getScrollElement: () => scrollContainerRef.current,
    estimateSize: useCallback(
      (index: number) => {
        const commune = sorted[index];
        if (!commune) return 48;
        return expandedCode === commune.code ? 400 : 48;
      },
      // eslint-disable-next-line react-hooks/exhaustive-deps
      [sorted, expandedCode],
    ),
    overscan: 10,
  });

  const virtualItems = rowVirtualizer.getVirtualItems();

  return (
    <div className="bg-surface border border-border-subtle rounded-xl overflow-hidden">
      {/* Header */}
      <div className="px-5 pt-4 pb-3 border-b border-border-subtle space-y-3">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <p className="font-semibold text-foreground text-sm">
            Communes ({filtered.length}{filtered.length !== communes.length ? ` / ${communes.length}` : ""})
          </p>
          <div className="flex items-center gap-4">
            <SortButton label="Coverage" active={sortKey === "coverage"} dir={sortDir} onClick={() => handleSort("coverage")} />
            <SortButton label="Ingestion" active={sortKey === "ingestion"} dir={sortDir} onClick={() => handleSort("ingestion")} />
            <SortButton label="Name" active={sortKey === "name"} dir={sortDir} onClick={() => handleSort("name")} />
            <SortButton label="Population" active={sortKey === "population"} dir={sortDir} onClick={() => handleSort("population")} />
            <SortButton label="Lists" active={sortKey === "list_count"} dir={sortDir} onClick={() => handleSort("list_count")} />
            <SortButton label="Candidates" active={sortKey === "candidate_count"} dir={sortDir} onClick={() => handleSort("candidate_count")} />
            <SortButton label="Questions" active={sortKey === "question_count"} dir={sortDir} onClick={() => handleSort("question_count")} />
          </div>
        </div>
        {/* Filters row */}
        <div className="flex items-center gap-2 flex-wrap">
          <FilterIcon className="size-3 text-muted-foreground" />
          <ToggleChip label="All" active={statusFilter === "all"} onClick={() => setStatusFilter("all")} count={communes.length} />
          <ToggleChip label="Complete" active={statusFilter === "complete"} onClick={() => setStatusFilter("complete")} count={counts.complete} color="#22c55e" />
          <ToggleChip label="Partial" active={statusFilter === "partial"} onClick={() => setStatusFilter("partial")} count={counts.partial} color="#eab308" />
          <ToggleChip label="Missing" active={statusFilter === "missing"} onClick={() => setStatusFilter("missing")} count={counts.missing} color="#ef4444" />
          <span className="mx-1 w-px h-4 bg-border-subtle" />
          <ToggleChip
            label="Hide empty"
            active={hideEmpty}
            onClick={() => setHideEmpty((v) => !v)}
          />
        </div>
      </div>

      {/* Virtualized table — uses multiple <tbody> groups so measureElement
          captures both the data row and any expanded detail row together,
          giving the virtualizer accurate heights for variable-size items. */}
      <div
        ref={scrollContainerRef}
        className="overflow-auto max-h-[600px]"
      >
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-surface z-10">
            <tr className="border-b border-border-subtle text-left">
              <th className="px-5 py-2.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground w-10">#</th>
              <th className="px-3 py-2.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground">Commune</th>
              <th className="px-3 py-2.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground w-24 text-right">Population</th>
              <th className="px-3 py-2.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground min-w-[120px]">Coverage</th>
              <th className="px-3 py-2.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground min-w-[120px]">Ingestion</th>
              <th className="px-3 py-2.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground w-20 text-right">Lists</th>
              <th className="px-3 py-2.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground min-w-[120px]">Candidates</th>
              <th className="px-3 py-2.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground min-w-[180px]">Questions</th>
            </tr>
          </thead>

          <tbody className="divide-y divide-border-subtle/50">
            {sorted.length === 0 && (
              <tr>
                <td colSpan={8} className="px-5 py-8 text-center text-muted-foreground text-sm">
                  {communes.length === 0 ? "No communes found." : "No communes match current filters."}
                </td>
              </tr>
            )}

            {/* Top padding row */}
            {virtualItems.length > 0 && virtualItems[0]!.start > 0 && (
              <tr style={{ height: `${virtualItems[0]!.start}px` }} />
            )}

            {virtualItems.map((virtualRow) => {
              const commune = sorted[virtualRow.index];
              if (!commune) return null;
              const isExpanded = expandedCode === commune.code;
              return (
                <Fragment key={commune.code}>
                  <tr
                    className="hover:bg-border-subtle/10 transition-colors cursor-pointer select-none"
                    onClick={() => setExpandedCode(isExpanded ? null : commune.code)}
                  >
                    <td className="px-5 py-3 text-xs text-muted-foreground tabular-nums">
                      <ChevronRightIcon
                        className={`size-3.5 inline-block transition-transform duration-150 ${isExpanded ? "rotate-90" : ""}`}
                      />
                    </td>
                    <td className="px-3 py-3">
                      <span className="font-medium text-foreground">{commune.name}</span>
                      <span className="ml-2 text-[10px] text-muted-foreground font-mono">{commune.code}</span>
                    </td>
                    <td className="px-3 py-3 text-right text-muted-foreground tabular-nums text-xs">
                      {commune.population > 0 ? commune.population.toLocaleString("fr-FR") : "—"}
                    </td>
                    <td className="px-3 py-3">
                      <ScoreBar score={commune.coverage} />
                    </td>
                    <td className="px-3 py-3">
                      <ScoreBar score={commune.ingestion} gradient="#8B5CF6" />
                    </td>
                    <td className="px-3 py-3 text-right text-muted-foreground tabular-nums">
                      {commune.list_count > 0 ? (
                        <CoverageBar value={commune.list_count} max={maxLists} />
                      ) : (
                        <span className="text-xs text-red-400/70">missing</span>
                      )}
                    </td>
                    <td className="px-3 py-3">
                      {commune.candidate_count > 0 ? (
                        <CoverageBar value={commune.candidate_count} max={maxCandidates} />
                      ) : (
                        <span className="text-xs text-red-400/70">missing</span>
                      )}
                    </td>
                    <td className="px-3 py-3">
                      {commune.question_count > 0 ? (
                        <CoverageBar value={commune.question_count} max={maxQuestions} />
                      ) : (
                        <span className="text-xs text-muted-foreground">—</span>
                      )}
                    </td>
                  </tr>
                  {isExpanded && (
                    <tr className="bg-border-subtle/5">
                      <td colSpan={8}>
                        <ScoreBreakdown
                          commune={commune}
                          agg={coverageByCommune[commune.code]}
                        />
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}

            {/* Bottom padding row */}
            {virtualItems.length > 0 && (() => {
              const last = virtualItems[virtualItems.length - 1]!;
              const pad = rowVirtualizer.getTotalSize() - last.end;
              return pad > 0 ? <tr style={{ height: `${pad}px` }} /> : null;
            })()}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Parties table
// ---------------------------------------------------------------------------

function PartiesTable({ parties }: { parties: PartyCoverage[] }) {
  const [sortKey, setSortKey] = useState<PartySortKey>("chunk_count");
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  const [hideIndexed, setHideIndexed] = useState(false);

  const maxChunks = Math.max(...parties.map((p) => p.chunk_count), 1);

  const noManifesto = parties.filter((p) => !p.has_manifesto).length;
  const notIndexed = parties.filter((p) => p.chunk_count === 0).length;

  function handleSort(key: PartySortKey) {
    if (sortKey === key) {
      setSortDir((d) => (d === "desc" ? "asc" : "desc"));
    } else {
      setSortKey(key);
      setSortDir("desc");
    }
  }

  const filtered = useMemo(() => {
    if (!hideIndexed) return parties;
    return parties.filter((p) => p.chunk_count === 0 || !p.has_manifesto);
  }, [parties, hideIndexed]);

  const sorted = [...filtered].sort((a, b) => {
    const mul = sortDir === "desc" ? -1 : 1;
    if (sortKey === "name") return mul * a.name.localeCompare(b.name);
    return mul * (a.chunk_count - b.chunk_count);
  });

  const warnings: string[] = [];
  if (noManifesto > 0) warnings.push(`${noManifesto} ${noManifesto === 1 ? "party has" : "parties have"} no manifesto uploaded`);
  if (notIndexed > 0) warnings.push(`${notIndexed} ${notIndexed === 1 ? "party has" : "parties have"} 0 indexed chunks — RAG won't return results for them`);

  return (
    <div className="space-y-3">
      <WarningBanner warnings={warnings} />
      <div className="bg-surface border border-border-subtle rounded-xl overflow-hidden">
        {/* Header */}
        <div className="px-5 pt-4 pb-3 border-b border-border-subtle space-y-3">
          <div className="flex items-center justify-between gap-2">
            <p className="font-semibold text-foreground text-sm">
              Parties ({filtered.length}{filtered.length !== parties.length ? ` / ${parties.length}` : ""})
            </p>
            <div className="flex items-center gap-4">
              <SortButton label="Name" active={sortKey === "name"} dir={sortDir} onClick={() => handleSort("name")} />
              <SortButton label="Chunks" active={sortKey === "chunk_count"} dir={sortDir} onClick={() => handleSort("chunk_count")} />
            </div>
          </div>
          <div className="flex items-center gap-2">
            <FilterIcon className="size-3 text-muted-foreground" />
            <ToggleChip
              label="Only missing data"
              active={hideIndexed}
              onClick={() => setHideIndexed((v) => !v)}
              count={noManifesto + notIndexed > 0 ? parties.filter((p) => p.chunk_count === 0 || !p.has_manifesto).length : undefined}
            />
          </div>
        </div>

        {/* Table */}
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border-subtle text-left">
                <th className="px-5 py-2.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground w-10">#</th>
                <th className="px-3 py-2.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground">Party</th>
                <th className="px-3 py-2.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground w-24 text-center">Manifesto</th>
                <th className="px-3 py-2.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground min-w-[220px]">Indexed chunks</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border-subtle/50">
              {sorted.length === 0 && (
                <tr>
                  <td colSpan={4} className="px-5 py-8 text-center text-muted-foreground text-sm">
                    {parties.length === 0 ? "No parties found." : "All parties have data — nothing to show."}
                  </td>
                </tr>
              )}
              {sorted.map((party, i) => (
                <tr
                  key={party.party_id}
                  className={`hover:bg-border-subtle/10 transition-colors ${
                    !party.has_manifesto || party.chunk_count === 0 ? "bg-red-500/[0.03]" : ""
                  }`}
                >
                  <td className="px-5 py-3 text-xs text-muted-foreground tabular-nums">{i + 1}.</td>
                  <td className="px-3 py-3">
                    <span className="font-medium text-foreground">{party.name}</span>
                    {party.short_name && party.short_name !== party.name && (
                      <span className="ml-2 text-[10px] bg-primary/10 text-primary border border-primary/20 rounded px-1.5 py-0.5 font-mono">
                        {party.short_name}
                      </span>
                    )}
                  </td>
                  <td className="px-3 py-3 text-center">
                    {party.has_manifesto ? (
                      <CheckIcon className="size-4 text-green-500 mx-auto" />
                    ) : (
                      <span className="inline-flex items-center gap-1 text-red-400 text-[11px]">
                        <XIcon className="size-3.5" /> missing
                      </span>
                    )}
                  </td>
                  <td className="px-3 py-3">
                    {party.chunk_count > 0 ? (
                      <CoverageBar value={party.chunk_count} max={maxChunks} />
                    ) : (
                      <span className="text-xs text-red-400/70">Not indexed</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Candidates table
// ---------------------------------------------------------------------------

function CandidatesTable({ candidates }: { candidates: CandidateCoverage[] }) {
  const [sortKey, setSortKey] = useState<CandidateSortKey>("name");
  const [sortDir, setSortDir] = useState<SortDir>("asc");
  const [search, setSearch] = useState("");
  const [onlyMissing, setOnlyMissing] = useState(false);

  const scrollContainerRef = useRef<HTMLDivElement>(null);

  const missingWebsite = candidates.filter((c) => !c.has_website).length;
  const missingManifesto = candidates.filter((c) => !c.has_manifesto).length;

  function handleSort(key: CandidateSortKey) {
    if (sortKey === key) {
      setSortDir((d) => (d === "desc" ? "asc" : "desc"));
    } else {
      setSortKey(key);
      setSortDir("asc");
    }
  }

  const filtered = useMemo(() => {
    return candidates.filter((c) => {
      if (onlyMissing && c.has_website && c.has_manifesto) return false;
      if (!search) return true;
      const q = search.toLowerCase();
      return (
        c.name.toLowerCase().includes(q) ||
        c.commune_name.toLowerCase().includes(q) ||
        c.party_label.toLowerCase().includes(q)
      );
    });
  }, [candidates, search, onlyMissing]);

  const sorted = [...filtered].sort((a, b) => {
    const mul = sortDir === "desc" ? -1 : 1;
    return mul * (a[sortKey] ?? "").localeCompare(b[sortKey] ?? "");
  });

  const notIndexed = candidates.filter((c) => c.has_website && c.chunk_count === 0).length;

  const warnings: string[] = [];
  if (missingWebsite > 0) warnings.push(`${missingWebsite} ${missingWebsite === 1 ? "candidate" : "candidates"} without a website — can't scrape content`);
  if (missingManifesto > 0) warnings.push(`${missingManifesto} ${missingManifesto === 1 ? "candidate" : "candidates"} without a manifesto document`);
  if (notIndexed > 0) warnings.push(`${notIndexed} ${notIndexed === 1 ? "candidate has" : "candidates have"} a website but no indexed content — run the scraper + indexer pipeline`);

  const rowVirtualizer = useVirtualizer({
    count: sorted.length,
    getScrollElement: () => scrollContainerRef.current,
    estimateSize: () => 48,
    overscan: 10,
  });

  const virtualItems = rowVirtualizer.getVirtualItems();

  return (
    <div className="space-y-3">
      <WarningBanner warnings={warnings} />
      <div className="bg-surface border border-border-subtle rounded-xl overflow-hidden">
        <div className="px-5 pt-4 pb-3 border-b border-border-subtle space-y-3">
          <div className="flex items-center justify-between gap-2 flex-wrap">
            <p className="font-semibold text-foreground text-sm">
              Candidates ({filtered.length}{filtered.length !== candidates.length ? ` / ${candidates.length}` : ""})
            </p>
            <div className="flex items-center gap-4">
              <div className="relative">
                <SearchIcon className="absolute left-2.5 top-1/2 -translate-y-1/2 size-3.5 text-muted-foreground pointer-events-none" />
                <input
                  type="text"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Search name, commune, party..."
                  className="pl-8 pr-3 py-1.5 text-xs rounded-lg border border-border-subtle bg-background text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary/40 w-56"
                />
              </div>
              <SortButton label="Name" active={sortKey === "name"} dir={sortDir} onClick={() => handleSort("name")} />
              <SortButton label="Commune" active={sortKey === "commune_name"} dir={sortDir} onClick={() => handleSort("commune_name")} />
              <SortButton label="Party" active={sortKey === "party_label"} dir={sortDir} onClick={() => handleSort("party_label")} />
            </div>
          </div>
          <div className="flex items-center gap-2">
            <FilterIcon className="size-3 text-muted-foreground" />
            <ToggleChip
              label="Only missing data"
              active={onlyMissing}
              onClick={() => setOnlyMissing((v) => !v)}
              count={candidates.filter((c) => !c.has_website || !c.has_manifesto).length}
            />
          </div>
        </div>
        <div ref={scrollContainerRef} className="max-h-[500px] overflow-y-auto">
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-surface z-10">
              <tr className="border-b border-border-subtle text-left">
                <th className="px-5 py-2.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground w-10">#</th>
                <th className="px-3 py-2.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground">Candidate</th>
                <th className="px-3 py-2.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground">Commune</th>
                <th className="px-3 py-2.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground">List / Party</th>
                <th className="px-3 py-2.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground w-20 text-center">Website</th>
                <th className="px-3 py-2.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground w-24 text-center">Manifesto</th>
                <th className="px-3 py-2.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground w-24 text-center">Indexed</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border-subtle/50">
              {sorted.length === 0 && (
                <tr>
                  <td colSpan={7} className="px-5 py-8 text-center text-muted-foreground text-sm">
                    {candidates.length === 0 ? "No candidates found." : "No candidates match current filters."}
                  </td>
                </tr>
              )}

              {/* Top padding row */}
              {virtualItems.length > 0 && virtualItems[0]!.start > 0 && (
                <tr style={{ height: `${virtualItems[0]!.start}px` }} />
              )}

              {virtualItems.map((virtualRow) => {
                const c = sorted[virtualRow.index];
                if (!c) return null;
                return (
                  <tr
                    key={c.candidate_id}
                    className={`hover:bg-border-subtle/10 transition-colors ${
                      !c.has_website || !c.has_manifesto ? "bg-red-500/[0.03]" : ""
                    }`}
                  >
                    <td className="px-5 py-3 text-xs text-muted-foreground tabular-nums">{virtualRow.index + 1}.</td>
                    <td className="px-3 py-3">
                      <span className="font-medium text-foreground">{c.name}</span>
                    </td>
                    <td className="px-3 py-3 text-muted-foreground">
                      {c.commune_name || "—"}
                      {c.commune_code && (
                        <span className="ml-1.5 text-[10px] font-mono text-muted-foreground/60">{c.commune_code}</span>
                      )}
                    </td>
                    <td className="px-3 py-3 text-muted-foreground text-xs">{c.party_label || "—"}</td>
                    <td className="px-3 py-3 text-center">
                      {c.has_website ? (
                        <CheckIcon className="size-4 text-green-500 mx-auto" />
                      ) : (
                        <span className="inline-flex items-center gap-0.5 text-red-400 text-[11px] justify-center">
                          <XIcon className="size-3.5" />
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-3 text-center">
                      {c.has_manifesto ? (
                        <CheckIcon className="size-4 text-green-500 mx-auto" />
                      ) : (
                        <span className="inline-flex items-center gap-0.5 text-red-400 text-[11px] justify-center">
                          <XIcon className="size-3.5" />
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-3 text-center">
                      {c.chunk_count > 0 ? (
                        <span className="inline-flex items-center gap-1 text-green-500 text-[11px]">
                          <CheckIcon className="size-3.5" />
                          <span className="tabular-nums">{c.chunk_count}</span>
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-0.5 text-red-400 text-[11px] justify-center">
                          <XIcon className="size-3.5" />
                        </span>
                      )}
                    </td>
                  </tr>
                );
              })}

              {/* Bottom padding row */}
              {virtualItems.length > 0 && (() => {
                const last = virtualItems[virtualItems.length - 1]!;
                const pad = rowVirtualizer.getTotalSize() - last.end;
                return pad > 0 ? <tr style={{ height: `${pad}px` }} /> : null;
              })()}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Combined export (all tables)
// ---------------------------------------------------------------------------

export default function CoverageTablesClient({
  communes,
  parties,
  candidates,
  coverageByCommune,
}: {
  communes: CommuneCoverage[];
  parties: PartyCoverage[];
  candidates: CandidateCoverage[];
  coverageByCommune: ChartAggregations["coverageByCommune"];
}) {
  return (
    <div className="space-y-8">
      <CommunesTable communes={communes} coverageByCommune={coverageByCommune} />

      <div>
        <div className="flex items-center gap-3 mb-4">
          <span className="text-xs font-semibold uppercase tracking-widest text-muted-foreground whitespace-nowrap">
            Parties — Knowledge Base Coverage
          </span>
          <div className="flex-1 border-t border-border-subtle" />
        </div>
        <PartiesTable parties={parties} />
      </div>

      <div>
        <div className="flex items-center gap-3 mb-4">
          <span className="text-xs font-semibold uppercase tracking-widest text-muted-foreground whitespace-nowrap">
            Candidates — Data Availability
          </span>
          <div className="flex-1 border-t border-border-subtle" />
        </div>
        <CandidatesTable candidates={candidates} />
      </div>
    </div>
  );
}

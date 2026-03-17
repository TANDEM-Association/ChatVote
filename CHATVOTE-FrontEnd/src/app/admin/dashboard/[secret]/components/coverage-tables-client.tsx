"use client";

import {
  Fragment,
  memo,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { useVirtualizer } from "@tanstack/react-virtual";
import {
  AlertTriangleIcon,
  ArrowUpDownIcon,
  CheckIcon,
  ChevronRightIcon,
  ExternalLinkIcon,
  FilterIcon,
  Loader2Icon,
  SearchIcon,
  XIcon,
} from "lucide-react";

import {
  type CandidateCoverage,
  type ChartAggregations,
  type CommuneCoverage,
  type PartyCoverage,
} from "../../../../api/coverage/route";

type CommuneAggEntry = ChartAggregations["coverageByCommune"][string];

// ---------------------------------------------------------------------------
// Two-score system: Coverage (data completeness) + Ingestion (scrape/index)
// Scores are pre-computed server-side via ChartAggregations.coverageByCommune
// ---------------------------------------------------------------------------

type CommuneWithScore = CommuneCoverage & {
  coverage: number;
  ingestion: number;
};

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type CommuneSortKey =
  | "name"
  | "population"
  | "list_count"
  | "candidate_count"
  | "question_count"
  | "coverage"
  | "ingestion";
type PartySortKey = "name" | "chunk_count";
type CandidateSortKey = "name" | "commune_name" | "party_label";
type SortDir = "asc" | "desc";
type CompletenessFilter = "all" | "complete" | "partial" | "missing";

// ---------------------------------------------------------------------------
// Candidate chunks types (per-commune detail panel)
// ---------------------------------------------------------------------------

type CandidateChunkDetail = {
  candidate_id: string;
  name: string;
  party_label: string;
  is_tete_de_liste: boolean;
  website_url: string;
  manifesto_url: string;
  manifesto_pdf_path: string;
  has_manifesto: boolean;
  has_scraped: boolean;
  scrape_chars: number;
  total_chunks: number;
  manifesto_chunks: number;
  website_chunks: number;
  good_count: number;
  junk_count: number;
  themes: Record<string, number>;
  sources: Record<string, number>;
  urls: string[];
  junk_samples: Array<{ reason: string; preview: string }>;
  debug_links: {
    qdrant_collection: string;
    qdrant_points: string;
    firestore_doc: string;
    drive_folder: string;
  };
};

type CandidateChunksResponse = {
  commune_code: string;
  candidates: CandidateChunkDetail[];
  summary: {
    total_candidates: number;
    total_chunks: number;
    manifesto_chunks: number;
    website_chunks: number;
    good_chunks: number;
    junk_chunks: number;
  };
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function CoverageBar({ value, max }: { value: number; max: number }) {
  const pct = max > 0 ? Math.round((value / max) * 100) : 0;
  return (
    <div className="flex min-w-0 items-center gap-2">
      <div className="bg-border-subtle/40 h-2 flex-1 overflow-hidden rounded-full">
        <div
          className="h-full rounded-full"
          style={{
            width: `${pct}%`,
            background: "linear-gradient(90deg, #381AF3, #8B5CF6)",
          }}
        />
      </div>
      <span className="text-muted-foreground w-8 shrink-0 text-right text-xs tabular-nums">
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
      className={`flex items-center gap-1 text-xs font-semibold tracking-wider uppercase transition-colors ${
        active
          ? "text-foreground"
          : "text-muted-foreground hover:text-foreground"
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
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-medium transition-all ${
        active
          ? "bg-foreground/10 border-foreground/20 text-foreground"
          : "border-border-subtle text-muted-foreground hover:border-foreground/20 bg-transparent"
      }`}
    >
      {color && (
        <span
          className="inline-block size-2 shrink-0 rounded-full"
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
    <div className="flex gap-3 rounded-lg border border-amber-500/20 bg-amber-500/10 px-4 py-3">
      <AlertTriangleIcon className="mt-0.5 size-4 shrink-0 text-amber-500" />
      <div className="space-y-1">
        {warnings.map((w) => (
          <p key={w} className="text-xs text-amber-200/80">
            {w}
          </p>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Communes table
// ---------------------------------------------------------------------------

function ScoreBar({ score, gradient }: { score: number; gradient?: string }) {
  const color =
    gradient ?? (score >= 75 ? "#22c55e" : score > 0 ? "#eab308" : "#ef4444");
  return (
    <div className="flex min-w-0 items-center gap-2">
      <div className="bg-border-subtle/40 h-2 flex-1 overflow-hidden rounded-full">
        <div
          className="h-full rounded-full transition-all"
          style={{ width: `${score}%`, backgroundColor: color }}
        />
      </div>
      <span className="text-muted-foreground w-8 shrink-0 text-right text-xs tabular-nums">
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
  const withWebsiteIndexed = agg?.hasWebsiteIndexed ?? 0;
  const withManifestoIndexed = agg?.hasManifestoIndexed ?? 0;

  const coverageItems = [
    {
      label: "Electoral lists",
      ok: commune.list_count > 0,
      detail:
        commune.list_count > 0 ? `${commune.list_count} lists` : "missing",
      pct: commune.list_count > 0 ? 100 : 0,
    },
    {
      label: "Candidates with website",
      ok: total > 0 && withWebsite === total,
      detail: total > 0 ? `${withWebsite} / ${total}` : "—",
      pct: total > 0 ? Math.round(100 * (withWebsite / total)) : 0,
    },
    {
      label: "Candidates with manifesto",
      ok: total > 0 && withManifesto === total,
      detail: total > 0 ? `${withManifesto} / ${total}` : "—",
      pct: total > 0 ? Math.round(100 * (withManifesto / total)) : 0,
    },
  ];

  const ingestionItems = [
    // — Manifesto pipeline —
    {
      label: "Manifesto downloaded",
      ok: total > 0 && withManifesto === total,
      detail: total > 0 ? `${withManifesto} / ${total}` : "—",
      pct: total > 0 ? Math.round(100 * (withManifesto / total)) : 0,
    },
    {
      label: "Manifesto indexed in RAG",
      ok: total > 0 && withManifestoIndexed === total,
      detail: total > 0 ? `${withManifestoIndexed} / ${total}` : "—",
      pct: total > 0 ? Math.round(100 * (withManifestoIndexed / total)) : 0,
    },
    // — Website pipeline —
    {
      label: "Website scraped",
      ok: withWebsite > 0 && withScraped === withWebsite,
      detail: withWebsite > 0 ? `${withScraped} / ${withWebsite}` : "—",
      pct:
        withWebsite > 0
          ? Math.min(Math.round(100 * (withScraped / withWebsite)), 100)
          : 0,
    },
    {
      label: "Website indexed in RAG",
      ok: withWebsite > 0 && withWebsiteIndexed === withWebsite,
      detail: withWebsite > 0 ? `${withWebsiteIndexed} / ${withWebsite}` : "—",
      pct:
        withWebsite > 0
          ? Math.min(Math.round(100 * (withWebsiteIndexed / withWebsite)), 100)
          : 0,
    },
  ];

  function renderItems(items: typeof coverageItems) {
    return (
      <div className="grid grid-cols-2 gap-x-8 gap-y-1.5">
        {items.map((item) => (
          <div key={item.label} className="flex items-center gap-2 text-xs">
            {item.ok ? (
              <CheckIcon className="size-3.5 shrink-0 text-green-500" />
            ) : item.pct > 0 ? (
              <span className="size-3.5 shrink-0 text-center font-bold text-yellow-500">
                ~
              </span>
            ) : (
              <XIcon className="size-3.5 shrink-0 text-red-400" />
            )}
            <span className="text-muted-foreground">{item.label}</span>
            <span className="text-foreground ml-auto font-medium tabular-nums">
              {item.pct}%
            </span>
            <span className="text-muted-foreground/60 w-16 text-right">
              {item.detail}
            </span>
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-4 px-8 py-4">
      {/* Coverage breakdown */}
      <div>
        <div className="mb-2 flex items-center gap-2">
          <p className="text-muted-foreground text-[11px] font-semibold tracking-wider uppercase">
            Coverage
          </p>
          <span className="text-[11px] font-medium text-blue-400 tabular-nums">
            {commune.coverage}%
          </span>
        </div>
        {renderItems(coverageItems)}
      </div>

      {/* Ingestion breakdown */}
      <div>
        <div className="mb-2 flex items-center gap-2">
          <p className="text-muted-foreground text-[11px] font-semibold tracking-wider uppercase">
            Ingestion
          </p>
          <span className="text-[11px] font-medium text-violet-400 tabular-nums">
            {commune.ingestion}%
          </span>
        </div>
        {renderItems(ingestionItems)}
      </div>

      {total > 0 && (
        <p className="text-muted-foreground/60 text-[11px]">
          {total} candidates — {withWebsite} with website · {withManifesto} with
          manifesto · {withWebsiteIndexed} website indexed · {withManifestoIndexed} manifesto indexed
        </p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// CandidateChunksPanel — fetches & renders per-commune candidate details
// ---------------------------------------------------------------------------

const BACKEND_URL =
  process.env.NEXT_PUBLIC_API_URL ||
  process.env.NEXT_PUBLIC_SOCKET_URL ||
  "http://localhost:8080";

const CandidateSubRow = memo(function CandidateSubRow({
  candidate,
  index,
}: {
  candidate: CandidateChunkDetail;
  index: number;
}) {
  const [expanded, setExpanded] = useState(false);
  const junkPct =
    candidate.total_chunks > 0
      ? Math.round((candidate.junk_count / candidate.total_chunks) * 100)
      : 0;

  return (
    <Fragment>
      <tr
        className="cursor-pointer transition-colors select-none hover:bg-violet-500/5"
        onClick={() => setExpanded((v) => !v)}
      >
        {/* # */}
        <td className="text-muted-foreground px-3 py-2 text-xs tabular-nums">
          <div className="flex items-center gap-1">
            <ChevronRightIcon
              className={`size-3 transition-transform duration-150 ${expanded ? "rotate-90" : ""}`}
            />
            {index + 1}.
          </div>
        </td>
        {/* Candidate */}
        <td className="px-3 py-2">
          <span className="text-foreground text-xs font-medium">
            {candidate.is_tete_de_liste && (
              <span className="mr-1 text-amber-400">★</span>
            )}
            {candidate.name}
          </span>
          <span className="text-muted-foreground/60 ml-1.5 font-mono text-[10px]">
            {candidate.candidate_id.slice(0, 8)}
          </span>
        </td>
        {/* Party */}
        <td className="text-muted-foreground px-3 py-2 text-xs">
          {candidate.party_label || "—"}
        </td>
        {/* Website */}
        <td className="px-3 py-2 text-center">
          {candidate.website_url ? (
            <a
              href={candidate.website_url}
              target="_blank"
              rel="noopener noreferrer"
              onClick={(e) => e.stopPropagation()}
              className="inline-flex items-center gap-0.5 text-[11px] text-green-500 hover:underline"
              title={candidate.website_url}
            >
              <CheckIcon className="size-3" />
              <ExternalLinkIcon className="size-2.5" />
            </a>
          ) : (
            <span className="text-muted-foreground text-[11px]">—</span>
          )}
        </td>
        {/* Manifesto */}
        <td className="px-3 py-2 text-center">
          {candidate.manifesto_url || candidate.manifesto_pdf_path ? (
            <a
              href={candidate.manifesto_url || candidate.manifesto_pdf_path}
              target="_blank"
              rel="noopener noreferrer"
              onClick={(e) => e.stopPropagation()}
              className="inline-flex items-center gap-0.5 text-[11px] text-green-500 hover:underline"
              title={candidate.manifesto_url || candidate.manifesto_pdf_path}
            >
              <CheckIcon className="size-3" />
              <ExternalLinkIcon className="size-2.5" />
            </a>
          ) : candidate.manifesto_chunks > 0 ? (
            <span className="text-[11px] text-green-500" title="Manifesto indexed (no URL available)">
              <CheckIcon className="size-3 inline" />
            </span>
          ) : (
            <span className="text-muted-foreground text-[11px]">—</span>
          )}
        </td>
        {/* Chunks: X site · X manifesto */}
        <td className="px-3 py-2">
          <span className="inline-flex items-center gap-1.5 text-[11px] tabular-nums">
            <span
              className={
                candidate.website_url && candidate.website_chunks === 0
                  ? "font-medium text-red-400"
                  : candidate.website_chunks > 0
                    ? "text-green-500"
                    : "text-muted-foreground"
              }
            >
              {candidate.website_url ? candidate.website_chunks : "—"}
            </span>
            <span className="text-muted-foreground/50">site</span>
            <span className="text-muted-foreground/30">·</span>
            <span
              className={
                (candidate.has_manifesto || candidate.manifesto_chunks > 0) && candidate.manifesto_chunks === 0
                  ? "font-medium text-red-400"
                  : candidate.manifesto_chunks > 0
                    ? "text-green-500"
                    : "text-muted-foreground"
              }
            >
              {candidate.has_manifesto || candidate.manifesto_chunks > 0 ? candidate.manifesto_chunks : "—"}
            </span>
            <span className="text-muted-foreground/50">manifesto</span>
          </span>
        </td>
        {/* Good */}
        <td className="px-3 py-2 text-center">
          <span className="text-[11px] text-green-500 tabular-nums">
            {candidate.good_count}
          </span>
        </td>
        {/* Junk */}
        <td className="px-3 py-2 text-center">
          {candidate.junk_count > 0 ? (
            <span
              className={`text-[11px] tabular-nums ${junkPct > 30 ? "text-red-400" : "text-amber-400"}`}
            >
              {candidate.junk_count}
              <span className="text-muted-foreground/60 ml-0.5">
                ({junkPct}%)
              </span>
            </span>
          ) : (
            <span className="text-muted-foreground/40 text-[11px]">0</span>
          )}
        </td>
      </tr>

      {expanded && (
        <tr className="bg-violet-500/[0.03]">
          <td colSpan={8} className="py-3 pr-6 pl-10">
            <div className="space-y-3 border-l-2 border-violet-500/15 pl-4 text-xs">
              {/* Links */}
              <div className="flex flex-wrap gap-x-4 gap-y-1">
                {candidate.website_url && (
                  <a
                    href={candidate.website_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 text-blue-400 hover:underline"
                  >
                    <ExternalLinkIcon className="size-3" /> Website
                  </a>
                )}
                {candidate.manifesto_url && (
                  <a
                    href={candidate.manifesto_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 text-blue-400 hover:underline"
                  >
                    <ExternalLinkIcon className="size-3" /> Manifesto PDF
                  </a>
                )}
                <a
                  href={candidate.debug_links.qdrant_points}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-orange-400 hover:underline"
                >
                  <ExternalLinkIcon className="size-3" /> Qdrant
                </a>
                <a
                  href={candidate.debug_links.firestore_doc}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-yellow-400 hover:underline"
                >
                  <ExternalLinkIcon className="size-3" /> Firestore
                </a>
                <a
                  href={candidate.debug_links.drive_folder}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-emerald-400 hover:underline"
                >
                  <ExternalLinkIcon className="size-3" /> Drive
                </a>
                {candidate.has_scraped && (
                  <span className="text-green-500/70">
                    Scraped ({(candidate.scrape_chars / 1000).toFixed(1)}k
                    chars)
                  </span>
                )}
              </div>

              {/* Chunks breakdown */}
              <div className="flex gap-4">
                <span className="text-muted-foreground">
                  Manifesto:{" "}
                  <span className="text-green-400">
                    {candidate.manifesto_chunks}
                  </span>
                </span>
                <span className="text-muted-foreground">
                  Website:{" "}
                  <span className="text-blue-400">
                    {candidate.website_chunks}
                  </span>
                </span>
              </div>

              {/* Themes */}
              {Object.keys(candidate.themes).length > 0 && (
                <div>
                  <p className="text-muted-foreground mb-1 text-[10px] font-semibold tracking-wider uppercase">
                    Themes
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    {Object.entries(candidate.themes)
                      .sort((a, b) => b[1] - a[1])
                      .map(([theme, count]) => (
                        <span
                          key={theme}
                          className="rounded border border-violet-500/20 bg-violet-500/10 px-1.5 py-0.5 text-[10px] text-violet-300"
                        >
                          {theme}
                          <span className="text-muted-foreground/60 ml-1">
                            {count}
                          </span>
                        </span>
                      ))}
                  </div>
                </div>
              )}

              {/* Sources */}
              {Object.keys(candidate.sources).length > 0 && (
                <div>
                  <p className="text-muted-foreground mb-1 text-[10px] font-semibold tracking-wider uppercase">
                    Sources
                  </p>
                  <div className="flex flex-wrap gap-3">
                    {Object.entries(candidate.sources).map(([src, count]) => (
                      <span key={src} className="text-muted-foreground">
                        {src}:{" "}
                        <span className="text-foreground tabular-nums">
                          {count}
                        </span>
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* URLs from chunks */}
              {candidate.urls.length > 0 && (
                <div>
                  <p className="text-muted-foreground mb-1 text-[10px] font-semibold tracking-wider uppercase">
                    Indexed URLs ({candidate.urls.length})
                  </p>
                  <div className="space-y-0.5">
                    {candidate.urls.slice(0, 5).map((url) => (
                      <a
                        key={url}
                        href={url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-muted-foreground/70 block truncate text-[10px] hover:text-blue-400 hover:underline"
                      >
                        {url}
                      </a>
                    ))}
                    {candidate.urls.length > 5 && (
                      <span className="text-muted-foreground/40 text-[10px]">
                        +{candidate.urls.length - 5} more
                      </span>
                    )}
                  </div>
                </div>
              )}

              {/* Junk samples */}
              {candidate.junk_samples.length > 0 && (
                <div>
                  <p className="text-muted-foreground mb-1 text-[10px] font-semibold tracking-wider uppercase">
                    Junk samples
                  </p>
                  <div className="space-y-1">
                    {candidate.junk_samples.slice(0, 3).map((s, i) => (
                      <div key={i} className="flex gap-2">
                        <span className="shrink-0 rounded border border-red-500/20 bg-red-500/10 px-1 py-0.5 text-[10px] text-red-400">
                          {s.reason}
                        </span>
                        <span className="text-muted-foreground/60 truncate text-[10px]">
                          {s.preview}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </td>
        </tr>
      )}
    </Fragment>
  );
});

type PanelState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "done"; data: CandidateChunksResponse };

function CandidateChunksPanel({ communeCode }: { communeCode: string }) {
  const [state, setState] = useState<PanelState>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;

    fetch(
      `${BACKEND_URL}/api/v1/commune/${encodeURIComponent(communeCode)}/candidate-chunks`,
    )
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
        return res.json() as Promise<CandidateChunksResponse>;
      })
      .then((json) => {
        if (!cancelled) setState({ status: "done", data: json });
      })
      .catch((err: unknown) => {
        if (!cancelled)
          setState({
            status: "error",
            message: err instanceof Error ? err.message : String(err),
          });
      });

    return () => {
      cancelled = true;
    };
  }, [communeCode]);

  if (state.status === "loading") {
    return (
      <div className="text-muted-foreground flex items-center gap-2 px-8 py-4 text-xs">
        <Loader2Icon className="size-3.5 animate-spin" />
        Loading candidate chunks…
      </div>
    );
  }

  if (state.status === "error") {
    return (
      <div className="px-8 py-3 text-xs text-red-400">
        Failed to load candidate chunks: {state.message}
      </div>
    );
  }

  const { data } = state;

  if (data.candidates.length === 0) {
    return (
      <div className="text-muted-foreground/60 px-8 py-3 text-xs">
        No candidate chunk data available for this commune.
      </div>
    );
  }

  const { summary } = data;

  return (
    <div className="border-border-subtle/30 ml-6 border-l-2 border-t border-l-violet-500/20 pl-4 pr-4 py-3">
      <p className="text-muted-foreground mb-2 text-[11px] font-semibold tracking-wider uppercase">
        Candidates — Chunk Details
      </p>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-border-subtle/30 border-b text-left">
              <th className="text-muted-foreground w-12 px-3 py-1.5 text-[10px] font-semibold tracking-wider uppercase">
                #
              </th>
              <th className="text-muted-foreground px-3 py-1.5 text-[10px] font-semibold tracking-wider uppercase">
                Candidate
              </th>
              <th className="text-muted-foreground px-3 py-1.5 text-[10px] font-semibold tracking-wider uppercase">
                Party
              </th>
              <th className="text-muted-foreground w-16 px-3 py-1.5 text-center text-[10px] font-semibold tracking-wider uppercase">
                Website
              </th>
              <th className="text-muted-foreground w-16 px-3 py-1.5 text-center text-[10px] font-semibold tracking-wider uppercase">
                Manifesto
              </th>
              <th className="text-muted-foreground min-w-[120px] px-3 py-1.5 text-[10px] font-semibold tracking-wider uppercase">
                Chunks
              </th>
              <th className="text-muted-foreground w-14 px-3 py-1.5 text-center text-[10px] font-semibold tracking-wider uppercase">
                Good
              </th>
              <th className="text-muted-foreground w-20 px-3 py-1.5 text-center text-[10px] font-semibold tracking-wider uppercase">
                Junk
              </th>
            </tr>
          </thead>
          <tbody className="divide-border-subtle/20 divide-y">
            {data.candidates.map((candidate, i) => (
              <CandidateSubRow
                key={candidate.candidate_id}
                candidate={candidate}
                index={i}
              />
            ))}
          </tbody>
          {/* Summary row */}
          <tfoot>
            <tr className="border-border-subtle/30 border-t">
              <td
                colSpan={5}
                className="text-muted-foreground px-3 py-1.5 text-[10px]"
              >
                Total — {summary.total_candidates} candidates
              </td>
              <td className="px-3 py-1.5">
                <span className="text-foreground text-[11px] font-medium tabular-nums">
                  {summary.total_chunks}
                </span>
                <span className="text-muted-foreground/60 ml-1 text-[10px]">
                  ({summary.manifesto_chunks} manifesto +{" "}
                  {summary.website_chunks} web)
                </span>
              </td>
              <td className="px-3 py-1.5 text-center">
                <span className="text-[11px] font-medium text-green-500 tabular-nums">
                  {summary.good_chunks}
                </span>
              </td>
              <td className="px-3 py-1.5 text-center">
                <span
                  className={`text-[11px] font-medium tabular-nums ${summary.junk_chunks > 0 ? "text-amber-400" : "text-muted-foreground/40"}`}
                >
                  {summary.junk_chunks}
                </span>
              </td>
            </tr>
          </tfoot>
        </table>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// CandidatesStatusCell — compact status line for the Candidates column
// ---------------------------------------------------------------------------

function CandidatesStatusCell({
  agg,
  candidateCount,
  maxCandidates,
}: {
  agg: CommuneAggEntry | undefined;
  candidateCount: number;
  maxCandidates: number;
}) {
  if (!agg || candidateCount === 0) {
    return <span className="text-xs text-red-400/70">missing</span>;
  }

  const { total, hasWebsite, hasManifestoIndexed, hasWebsiteIndexed } = agg;

  const manifestoIdxPct = total > 0 ? Math.round((hasManifestoIndexed / total) * 100) : 0;
  const websiteIdxPct = hasWebsite > 0 ? Math.round((hasWebsiteIndexed / hasWebsite) * 100) : 0;

  const manifestoColor =
    manifestoIdxPct === 100
      ? "text-green-500"
      : manifestoIdxPct > 0
        ? "text-amber-400"
        : "text-red-400";
  const websiteColor =
    websiteIdxPct === 100
      ? "text-green-500"
      : websiteIdxPct > 0
        ? "text-amber-400"
        : "text-red-400";

  return (
    <div className="space-y-0.5">
      <div className="flex items-center gap-1.5">
        <CoverageBar value={candidateCount} max={maxCandidates} />
      </div>
      <div className="flex gap-2 text-[10px]">
        <span className={manifestoColor}>
          {hasManifestoIndexed}/{total} manifesto
        </span>
        <span className={websiteColor}>
          {hasWebsiteIndexed}/{hasWebsite} web
        </span>
      </div>
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
    let complete = 0,
      partial = 0,
      missing = 0;
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
      if (
        hideEmpty &&
        c.list_count === 0 &&
        c.candidate_count === 0 &&
        c.question_count === 0
      ) {
        return false;
      }
      if (
        statusFilter !== "all" &&
        getScoreStatus(c.coverage) !== statusFilter
      ) {
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
        return expandedCode === commune.code ? 600 : 48;
      },

      [sorted, expandedCode],
    ),
    overscan: 10,
  });

  const virtualItems = rowVirtualizer.getVirtualItems();

  return (
    <div className="bg-surface border-border-subtle overflow-hidden rounded-xl border">
      {/* Header */}
      <div className="border-border-subtle space-y-3 border-b px-5 pt-4 pb-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-foreground text-sm font-semibold">
            Communes ({filtered.length}
            {filtered.length !== communes.length ? ` / ${communes.length}` : ""}
            )
          </p>
          <div className="flex items-center gap-4">
            <SortButton
              label="Coverage"
              active={sortKey === "coverage"}
              dir={sortDir}
              onClick={() => handleSort("coverage")}
            />
            <SortButton
              label="Ingestion"
              active={sortKey === "ingestion"}
              dir={sortDir}
              onClick={() => handleSort("ingestion")}
            />
            <SortButton
              label="Name"
              active={sortKey === "name"}
              dir={sortDir}
              onClick={() => handleSort("name")}
            />
            <SortButton
              label="Population"
              active={sortKey === "population"}
              dir={sortDir}
              onClick={() => handleSort("population")}
            />
            <SortButton
              label="Lists"
              active={sortKey === "list_count"}
              dir={sortDir}
              onClick={() => handleSort("list_count")}
            />
            <SortButton
              label="Candidates"
              active={sortKey === "candidate_count"}
              dir={sortDir}
              onClick={() => handleSort("candidate_count")}
            />
            <SortButton
              label="Questions"
              active={sortKey === "question_count"}
              dir={sortDir}
              onClick={() => handleSort("question_count")}
            />
          </div>
        </div>
        {/* Filters row */}
        <div className="flex flex-wrap items-center gap-2">
          <FilterIcon className="text-muted-foreground size-3" />
          <ToggleChip
            label="All"
            active={statusFilter === "all"}
            onClick={() => setStatusFilter("all")}
            count={communes.length}
          />
          <ToggleChip
            label="Complete"
            active={statusFilter === "complete"}
            onClick={() => setStatusFilter("complete")}
            count={counts.complete}
            color="#22c55e"
          />
          <ToggleChip
            label="Partial"
            active={statusFilter === "partial"}
            onClick={() => setStatusFilter("partial")}
            count={counts.partial}
            color="#eab308"
          />
          <ToggleChip
            label="Missing"
            active={statusFilter === "missing"}
            onClick={() => setStatusFilter("missing")}
            count={counts.missing}
            color="#ef4444"
          />
          <span className="bg-border-subtle mx-1 h-4 w-px" />
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
      <div ref={scrollContainerRef} className="max-h-[600px] overflow-auto">
        <table className="w-full text-sm">
          <thead className="bg-surface sticky top-0 z-10">
            <tr className="border-border-subtle border-b text-left">
              <th className="text-muted-foreground w-10 px-5 py-2.5 text-xs font-semibold tracking-wider uppercase">
                #
              </th>
              <th className="text-muted-foreground px-3 py-2.5 text-xs font-semibold tracking-wider uppercase">
                Commune
              </th>
              <th className="text-muted-foreground w-24 px-3 py-2.5 text-right text-xs font-semibold tracking-wider uppercase">
                Population
              </th>
              <th className="text-muted-foreground min-w-[120px] px-3 py-2.5 text-xs font-semibold tracking-wider uppercase">
                Coverage
              </th>
              <th className="text-muted-foreground min-w-[120px] px-3 py-2.5 text-xs font-semibold tracking-wider uppercase">
                Ingestion
              </th>
              <th className="text-muted-foreground w-20 px-3 py-2.5 text-right text-xs font-semibold tracking-wider uppercase">
                Lists
              </th>
              <th className="text-muted-foreground min-w-[160px] px-3 py-2.5 text-xs font-semibold tracking-wider uppercase">
                Candidates
              </th>
              <th className="text-muted-foreground min-w-[180px] px-3 py-2.5 text-xs font-semibold tracking-wider uppercase">
                Questions
              </th>
            </tr>
          </thead>

          <tbody className="divide-border-subtle/50 divide-y">
            {sorted.length === 0 && (
              <tr>
                <td
                  colSpan={8}
                  className="text-muted-foreground px-5 py-8 text-center text-sm"
                >
                  {communes.length === 0
                    ? "No communes found."
                    : "No communes match current filters."}
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
                    className="hover:bg-border-subtle/10 cursor-pointer transition-colors select-none"
                    onClick={() =>
                      setExpandedCode(isExpanded ? null : commune.code)
                    }
                  >
                    <td className="text-muted-foreground px-5 py-3 text-xs tabular-nums">
                      <ChevronRightIcon
                        className={`inline-block size-3.5 transition-transform duration-150 ${isExpanded ? "rotate-90" : ""}`}
                      />
                    </td>
                    <td className="px-3 py-3">
                      <span className="text-foreground font-medium">
                        {commune.name}
                      </span>
                      <span className="text-muted-foreground ml-2 font-mono text-[10px]">
                        {commune.code}
                      </span>
                    </td>
                    <td className="text-muted-foreground px-3 py-3 text-right text-xs tabular-nums">
                      {commune.population > 0
                        ? commune.population.toLocaleString("fr-FR")
                        : "—"}
                    </td>
                    <td className="px-3 py-3">
                      <ScoreBar score={commune.coverage} />
                    </td>
                    <td className="px-3 py-3">
                      <ScoreBar score={commune.ingestion} gradient="#8B5CF6" />
                    </td>
                    <td className="text-muted-foreground px-3 py-3 text-right tabular-nums">
                      {commune.list_count > 0 ? (
                        <CoverageBar
                          value={commune.list_count}
                          max={maxLists}
                        />
                      ) : (
                        <span className="text-xs text-red-400/70">missing</span>
                      )}
                    </td>
                    <td className="px-3 py-3">
                      <CandidatesStatusCell
                        agg={coverageByCommune[commune.code]}
                        candidateCount={commune.candidate_count}
                        maxCandidates={maxCandidates}
                      />
                    </td>
                    <td className="px-3 py-3">
                      {commune.question_count > 0 ? (
                        <CoverageBar
                          value={commune.question_count}
                          max={maxQuestions}
                        />
                      ) : (
                        <span className="text-muted-foreground text-xs">—</span>
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
                        <CandidateChunksPanel
                          communeCode={commune.code}
                          // Pass cache ref down via a key trick — the cache lives
                          // in the parent so it persists across expand/collapse.
                          // The panel itself manages loading state internally.
                          key={commune.code}
                        />
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}

            {/* Bottom padding row */}
            {virtualItems.length > 0 &&
              (() => {
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
  if (noManifesto > 0)
    warnings.push(
      `${noManifesto} ${noManifesto === 1 ? "party has" : "parties have"} no manifesto uploaded`,
    );
  if (notIndexed > 0)
    warnings.push(
      `${notIndexed} ${notIndexed === 1 ? "party has" : "parties have"} 0 indexed chunks — RAG won't return results for them`,
    );

  return (
    <div className="space-y-3">
      <WarningBanner warnings={warnings} />
      <div className="bg-surface border-border-subtle overflow-hidden rounded-xl border">
        {/* Header */}
        <div className="border-border-subtle space-y-3 border-b px-5 pt-4 pb-3">
          <div className="flex items-center justify-between gap-2">
            <p className="text-foreground text-sm font-semibold">
              Parties ({filtered.length}
              {filtered.length !== parties.length ? ` / ${parties.length}` : ""}
              )
            </p>
            <div className="flex items-center gap-4">
              <SortButton
                label="Name"
                active={sortKey === "name"}
                dir={sortDir}
                onClick={() => handleSort("name")}
              />
              <SortButton
                label="Chunks"
                active={sortKey === "chunk_count"}
                dir={sortDir}
                onClick={() => handleSort("chunk_count")}
              />
            </div>
          </div>
          <div className="flex items-center gap-2">
            <FilterIcon className="text-muted-foreground size-3" />
            <ToggleChip
              label="Only missing data"
              active={hideIndexed}
              onClick={() => setHideIndexed((v) => !v)}
              count={
                noManifesto + notIndexed > 0
                  ? parties.filter(
                      (p) => p.chunk_count === 0 || !p.has_manifesto,
                    ).length
                  : undefined
              }
            />
          </div>
        </div>

        {/* Table */}
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-border-subtle border-b text-left">
                <th className="text-muted-foreground w-10 px-5 py-2.5 text-xs font-semibold tracking-wider uppercase">
                  #
                </th>
                <th className="text-muted-foreground px-3 py-2.5 text-xs font-semibold tracking-wider uppercase">
                  Party
                </th>
                <th className="text-muted-foreground w-24 px-3 py-2.5 text-center text-xs font-semibold tracking-wider uppercase">
                  Manifesto
                </th>
                <th className="text-muted-foreground min-w-[220px] px-3 py-2.5 text-xs font-semibold tracking-wider uppercase">
                  Indexed chunks
                </th>
              </tr>
            </thead>
            <tbody className="divide-border-subtle/50 divide-y">
              {sorted.length === 0 && (
                <tr>
                  <td
                    colSpan={4}
                    className="text-muted-foreground px-5 py-8 text-center text-sm"
                  >
                    {parties.length === 0
                      ? "No parties found."
                      : "All parties have data — nothing to show."}
                  </td>
                </tr>
              )}
              {sorted.map((party, i) => (
                <tr
                  key={party.party_id}
                  className={`hover:bg-border-subtle/10 transition-colors ${
                    !party.has_manifesto || party.chunk_count === 0
                      ? "bg-red-500/[0.03]"
                      : ""
                  }`}
                >
                  <td className="text-muted-foreground px-5 py-3 text-xs tabular-nums">
                    {i + 1}.
                  </td>
                  <td className="px-3 py-3">
                    <span className="text-foreground font-medium">
                      {party.name}
                    </span>
                    {party.short_name && party.short_name !== party.name && (
                      <span className="bg-primary/10 text-primary border-primary/20 ml-2 rounded border px-1.5 py-0.5 font-mono text-[10px]">
                        {party.short_name}
                      </span>
                    )}
                  </td>
                  <td className="px-3 py-3 text-center">
                    {party.has_manifesto ? (
                      <CheckIcon className="mx-auto size-4 text-green-500" />
                    ) : (
                      <span className="inline-flex items-center gap-1 text-[11px] text-red-400">
                        <XIcon className="size-3.5" /> missing
                      </span>
                    )}
                  </td>
                  <td className="px-3 py-3">
                    {party.chunk_count > 0 ? (
                      <CoverageBar value={party.chunk_count} max={maxChunks} />
                    ) : (
                      <span className="text-xs text-red-400/70">
                        Not indexed
                      </span>
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
// CandidateSourcesPanel — fetches & renders per-candidate Qdrant sources
// ---------------------------------------------------------------------------

interface CandidateSource {
  source_type: string;
  url: string | null;
  document_name: string | null;
  page_title: string | null;
  chunk_count: number;
  fiabilite: number | null;
  themes: Record<string, number>;
}

interface CandidateSourcesData {
  candidate_id: string;
  total_chunks: number;
  sources: CandidateSource[];
}

function sourceTypeBadge(sourceType: string) {
  if (sourceType === "profession_de_foi")
    return (
      <span className="rounded bg-green-500/15 px-1.5 py-0.5 text-[10px] font-medium text-green-400">
        profession de foi
      </span>
    );
  if (sourceType === "uploaded_document")
    return (
      <span className="rounded bg-purple-500/15 px-1.5 py-0.5 text-[10px] font-medium text-purple-400">
        uploaded
      </span>
    );
  if (sourceType === "programme")
    return (
      <span className="rounded bg-amber-500/15 px-1.5 py-0.5 text-[10px] font-medium text-amber-400">
        programme
      </span>
    );
  // website / html / candidate_website_*
  return (
    <span className="rounded bg-blue-500/15 px-1.5 py-0.5 text-[10px] font-medium text-blue-400">
      {sourceType.replace(/_/g, " ")}
    </span>
  );
}

const CandidateSourcesPanel = memo(function CandidateSourcesPanel({
  candidateId,
  secret,
  apiUrl,
}: {
  candidateId: string;
  secret: string | undefined;
  apiUrl: string | undefined;
}) {
  const [data, setData] = useState<CandidateSourcesData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setData(null);
    const base = apiUrl || BACKEND_URL;
    fetch(`${base}/api/v1/admin/candidate-sources/${candidateId}`, {
      headers: secret ? { "X-Admin-Secret": secret } : {},
    })
      .then((r) => {
        if (!r.ok) throw new Error(`Status ${r.status}`);
        return r.json() as Promise<CandidateSourcesData>;
      })
      .then((json) => {
        if (!cancelled) {
          setData(json);
          setLoading(false);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load");
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [candidateId, secret, apiUrl]);

  if (loading)
    return (
      <div className="flex items-center gap-2 px-6 py-4">
        <Loader2Icon className="text-muted-foreground size-3.5 animate-spin" />
        <span className="text-muted-foreground text-xs">Loading sources…</span>
      </div>
    );

  if (error)
    return (
      <div className="px-6 py-3 text-xs text-red-400">
        Error: {error}
      </div>
    );

  if (!data || data.sources.length === 0)
    return (
      <div className="text-muted-foreground px-6 py-3 text-xs">
        No indexed sources found for this candidate.
      </div>
    );

  return (
    <div className="border-violet-500/20 bg-violet-500/[0.03] border-l-2 px-6 py-3">
      <p className="text-muted-foreground mb-2 text-[11px] font-semibold tracking-wider uppercase">
        {data.total_chunks} indexed chunks — {data.sources.length} source
        {data.sources.length !== 1 ? "s" : ""}
      </p>
      <table className="w-full text-xs">
        <thead>
          <tr className="text-muted-foreground border-border-subtle border-b text-left">
            <th className="pb-1.5 pr-3 font-medium">Type</th>
            <th className="pb-1.5 pr-3 font-medium">Document</th>
            <th className="pb-1.5 pr-3 text-right font-medium">Chunks</th>
            <th className="pb-1.5 pr-3 text-right font-medium">Fiabilité</th>
            <th className="pb-1.5 font-medium">Themes</th>
          </tr>
        </thead>
        <tbody className="divide-border-subtle/40 divide-y">
          {data.sources.map((src, i) => (
            <tr key={i} className="align-top">
              <td className="py-1.5 pr-3">{sourceTypeBadge(src.source_type)}</td>
              <td className="py-1.5 pr-3">
                {src.url ? (
                  <a
                    href={src.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-foreground hover:text-primary inline-flex items-center gap-1 font-medium"
                  >
                    {src.document_name || src.page_title || src.url}
                    <ExternalLinkIcon className="size-3 shrink-0" />
                  </a>
                ) : (
                  <span className="text-foreground font-medium">
                    {src.document_name || src.page_title || "—"}
                  </span>
                )}
                {src.page_title && src.document_name && src.page_title !== src.document_name && (
                  <span className="text-muted-foreground ml-1.5 text-[10px]">
                    {src.page_title}
                  </span>
                )}
              </td>
              <td className="text-foreground py-1.5 pr-3 text-right tabular-nums">
                {src.chunk_count}
              </td>
              <td className="text-muted-foreground py-1.5 pr-3 text-right tabular-nums">
                {src.fiabilite ?? "—"}
              </td>
              <td className="py-1.5">
                <div className="flex flex-wrap gap-1">
                  {Object.entries(src.themes)
                    .sort((a, b) => b[1] - a[1])
                    .slice(0, 6)
                    .map(([theme, count]) => (
                      <span
                        key={theme}
                        className="bg-border-subtle rounded px-1.5 py-0.5 text-[10px] tabular-nums"
                        title={`${count} chunks`}
                      >
                        {theme}
                        <span className="text-muted-foreground ml-0.5">{count}</span>
                      </span>
                    ))}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
});

// ---------------------------------------------------------------------------
// Candidates table
// ---------------------------------------------------------------------------

function CandidatesTable({
  candidates,
  secret,
  apiUrl,
}: {
  candidates: CandidateCoverage[];
  secret?: string;
  apiUrl?: string;
}) {
  const [sortKey, setSortKey] = useState<CandidateSortKey>("name");
  const [sortDir, setSortDir] = useState<SortDir>("asc");
  const [search, setSearch] = useState("");
  const [onlyMissing, setOnlyMissing] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);

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

  const notIndexed = candidates.filter(
    (c) => c.has_website && c.chunk_count === 0,
  ).length;

  const warnings: string[] = [];
  if (missingWebsite > 0)
    warnings.push(
      `${missingWebsite} ${missingWebsite === 1 ? "candidate" : "candidates"} without a website — can't scrape content`,
    );
  if (missingManifesto > 0)
    warnings.push(
      `${missingManifesto} ${missingManifesto === 1 ? "candidate" : "candidates"} without a manifesto document`,
    );
  if (notIndexed > 0)
    warnings.push(
      `${notIndexed} ${notIndexed === 1 ? "candidate has" : "candidates have"} a website but no indexed content — run the scraper + indexer pipeline`,
    );

  const rowVirtualizer = useVirtualizer({
    count: sorted.length,
    getScrollElement: () => scrollContainerRef.current,
    estimateSize: useCallback(
      (index: number) => {
        const candidate = sorted[index];
        if (!candidate) return 48;
        return expandedId === candidate.candidate_id ? 400 : 48;
      },
      [sorted, expandedId],
    ),
    overscan: 10,
  });

  const virtualItems = rowVirtualizer.getVirtualItems();

  return (
    <div className="space-y-3">
      <WarningBanner warnings={warnings} />
      <div className="bg-surface border-border-subtle overflow-hidden rounded-xl border">
        <div className="border-border-subtle space-y-3 border-b px-5 pt-4 pb-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-foreground text-sm font-semibold">
              Candidates ({filtered.length}
              {filtered.length !== candidates.length
                ? ` / ${candidates.length}`
                : ""}
              )
            </p>
            <div className="flex items-center gap-4">
              <div className="relative">
                <SearchIcon className="text-muted-foreground pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2" />
                <input
                  type="text"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Search name, commune, party..."
                  className="border-border-subtle bg-background text-foreground placeholder:text-muted-foreground focus:ring-primary/40 w-56 rounded-lg border py-1.5 pr-3 pl-8 text-xs focus:ring-1 focus:outline-none"
                />
              </div>
              <SortButton
                label="Name"
                active={sortKey === "name"}
                dir={sortDir}
                onClick={() => handleSort("name")}
              />
              <SortButton
                label="Commune"
                active={sortKey === "commune_name"}
                dir={sortDir}
                onClick={() => handleSort("commune_name")}
              />
              <SortButton
                label="Party"
                active={sortKey === "party_label"}
                dir={sortDir}
                onClick={() => handleSort("party_label")}
              />
            </div>
          </div>
          <div className="flex items-center gap-2">
            <FilterIcon className="text-muted-foreground size-3" />
            <ToggleChip
              label="Only missing data"
              active={onlyMissing}
              onClick={() => setOnlyMissing((v) => !v)}
              count={
                candidates.filter((c) => !c.has_website || !c.has_manifesto)
                  .length
              }
            />
          </div>
        </div>
        <div ref={scrollContainerRef} className="max-h-[500px] overflow-y-auto">
          <table className="w-full text-sm">
            <thead className="bg-surface sticky top-0 z-10">
              <tr className="border-border-subtle border-b text-left">
                <th className="text-muted-foreground w-10 px-5 py-2.5 text-xs font-semibold tracking-wider uppercase">
                  #
                </th>
                <th className="text-muted-foreground px-3 py-2.5 text-xs font-semibold tracking-wider uppercase">
                  Candidate
                </th>
                <th className="text-muted-foreground px-3 py-2.5 text-xs font-semibold tracking-wider uppercase">
                  Commune
                </th>
                <th className="text-muted-foreground px-3 py-2.5 text-xs font-semibold tracking-wider uppercase">
                  List / Party
                </th>
                <th className="text-muted-foreground w-20 px-3 py-2.5 text-center text-xs font-semibold tracking-wider uppercase">
                  Website
                </th>
                <th className="text-muted-foreground w-24 px-3 py-2.5 text-center text-xs font-semibold tracking-wider uppercase">
                  Manifesto
                </th>
                <th className="text-muted-foreground w-36 px-3 py-2.5 text-center text-xs font-semibold tracking-wider uppercase">
                  Chunks
                </th>
                <th className="text-muted-foreground w-20 px-3 py-2.5 text-center text-xs font-semibold tracking-wider uppercase">
                  Uploaded
                </th>
              </tr>
            </thead>
            <tbody className="divide-border-subtle/50 divide-y">
              {sorted.length === 0 && (
                <tr>
                  <td
                    colSpan={8}
                    className="text-muted-foreground px-5 py-8 text-center text-sm"
                  >
                    {candidates.length === 0
                      ? "No candidates found."
                      : "No candidates match current filters."}
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
                const isExpanded = expandedId === c.candidate_id;
                return (
                  <Fragment key={c.candidate_id}>
                  <tr
                    className={`hover:bg-border-subtle/10 cursor-pointer select-none transition-colors ${
                      !c.has_website || !c.has_manifesto
                        ? "bg-red-500/[0.03]"
                        : ""
                    }`}
                    onClick={() =>
                      setExpandedId(isExpanded ? null : c.candidate_id)
                    }
                  >
                    <td className="text-muted-foreground px-5 py-3 text-xs tabular-nums">
                      <ChevronRightIcon
                        className={`inline-block size-3.5 transition-transform duration-150 ${isExpanded ? "rotate-90" : ""}`}
                      />
                    </td>
                    <td className="px-3 py-3">
                      <span className="text-foreground font-medium">
                        {c.name}
                      </span>
                    </td>
                    <td className="text-muted-foreground px-3 py-3">
                      {c.commune_name || "—"}
                      {c.commune_code && (
                        <span className="text-muted-foreground/60 ml-1.5 font-mono text-[10px]">
                          {c.commune_code}
                        </span>
                      )}
                    </td>
                    <td className="text-muted-foreground px-3 py-3 text-xs">
                      {c.party_label || "—"}
                    </td>
                    <td className="px-3 py-3 text-center">
                      {c.has_website ? (
                        <a
                          href={c.website_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-green-500 hover:text-green-400"
                          title={c.website_url}
                        >
                          <CheckIcon className="mx-auto size-4" />
                        </a>
                      ) : (
                        <span className="text-muted-foreground text-[11px]">—</span>
                      )}
                    </td>
                    <td className="px-3 py-3 text-center">
                      {c.manifesto_pdf_url ? (
                        <a
                          href={c.manifesto_pdf_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-green-500 hover:text-green-400"
                          title={c.manifesto_pdf_url}
                        >
                          <CheckIcon className="mx-auto size-4" />
                        </a>
                      ) : c.manifesto_chunks > 0 ? (
                        <span className="text-green-500" title="Manifesto indexed (no URL available)">
                          <CheckIcon className="mx-auto size-4" />
                        </span>
                      ) : (
                        <span className="text-muted-foreground text-[11px]">—</span>
                      )}
                    </td>
                    <td className="px-3 py-3 text-center">
                      <span className="inline-flex items-center gap-1.5 text-[11px] tabular-nums">
                        <span
                          className={
                            c.has_website && c.website_chunks === 0
                              ? "font-medium text-red-400"
                              : c.website_chunks > 0
                                ? "text-green-500"
                                : "text-muted-foreground"
                          }
                        >
                          {c.has_website ? c.website_chunks : "—"}
                        </span>
                        <span className="text-muted-foreground/50">site</span>
                        <span className="text-muted-foreground/30">·</span>
                        <span
                          className={
                            (c.has_manifesto || c.manifesto_chunks > 0) && c.manifesto_chunks === 0
                              ? "font-medium text-red-400"
                              : c.manifesto_chunks > 0
                                ? "text-green-500"
                                : "text-muted-foreground"
                          }
                        >
                          {c.has_manifesto || c.manifesto_chunks > 0 ? c.manifesto_chunks : "—"}
                        </span>
                        <span className="text-muted-foreground/50">manifesto</span>
                      </span>
                    </td>
                    <td className="px-3 py-3 text-center">
                      <span
                        className={`text-[11px] tabular-nums ${
                          c.uploaded_chunks > 0
                            ? "font-medium text-blue-400"
                            : "text-muted-foreground"
                        }`}
                      >
                        {c.uploaded_chunks > 0 ? c.uploaded_chunks : "—"}
                      </span>
                    </td>
                  </tr>
                  {isExpanded && (
                    <tr className="bg-border-subtle/5">
                      <td colSpan={8} className="p-0">
                        <CandidateSourcesPanel
                          candidateId={c.candidate_id}
                          secret={secret}
                          apiUrl={apiUrl}
                          key={c.candidate_id}
                        />
                      </td>
                    </tr>
                  )}
                  </Fragment>
                );
              })}

              {/* Bottom padding row */}
              {virtualItems.length > 0 &&
                (() => {
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
  secret,
  apiUrl,
}: {
  communes: CommuneCoverage[];
  parties: PartyCoverage[];
  candidates: CandidateCoverage[];
  coverageByCommune: ChartAggregations["coverageByCommune"];
  secret?: string;
  apiUrl?: string;
}) {
  return (
    <div className="space-y-8">
      <CommunesTable
        communes={communes}
        coverageByCommune={coverageByCommune}
      />

      <div>
        <div className="mb-4 flex items-center gap-3">
          <span className="text-muted-foreground text-xs font-semibold tracking-widest whitespace-nowrap uppercase">
            Parties — Knowledge Base Coverage
          </span>
          <div className="border-border-subtle flex-1 border-t" />
        </div>
        <PartiesTable parties={parties} />
      </div>

      <div>
        <div className="mb-4 flex items-center gap-3">
          <span className="text-muted-foreground text-xs font-semibold tracking-widest whitespace-nowrap uppercase">
            Candidates — Data Availability
          </span>
          <div className="border-border-subtle flex-1 border-t" />
        </div>
        <CandidatesTable candidates={candidates} secret={secret} apiUrl={apiUrl} />
      </div>
    </div>
  );
}

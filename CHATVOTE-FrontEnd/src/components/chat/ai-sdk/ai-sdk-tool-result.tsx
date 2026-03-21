"use client";

import { useState } from "react";

import dynamic from "next/dynamic";

import {
  ChevronDown,
  ChevronUp,
  Database,
  ExternalLink,
  Globe,
  MapPin,
  MessageSquare,
  Search,
  Sparkles,
  Unlock,
  Users,
  Vote,
} from "lucide-react";

const AiSdkChartWidget = dynamic(() => import("./ai-sdk-chart-widget"), {
  ssr: false,
  loading: () => (
    <div className="my-2 flex items-center gap-2 rounded-xl border border-white/10 bg-white/5 p-3 text-sm">
      <span className="flex gap-1">
        <span className="bg-primary/60 size-1.5 animate-bounce rounded-full [animation-delay:-0.3s]" />
        <span className="bg-primary/60 size-1.5 animate-bounce rounded-full [animation-delay:-0.15s]" />
        <span className="bg-primary/60 size-1.5 animate-bounce rounded-full" />
      </span>
      <span className="text-muted-foreground">Chargement du graphique...</span>
    </div>
  ),
});

type SearchResult = {
  id: number;
  content: string;
  source: string;
  url: string;
  page: number | string;
  party_id: string;
  candidate_name?: string;
};

type ToolPart = {
  type: string;
  toolCallId?: string;
  toolName?: string;
  state?: string;
  args?: Record<string, unknown>;
  input?: unknown;
  output?: unknown;
};

type Props = {
  part: ToolPart;
  onSendMessage?: (text: string) => void;
};

const TOOL_LOADING_LABELS: Record<string, string> = {
  searchDocumentsWithRerank: "Recherche documents",
  suggestFollowUps: "Génération de suggestions",
  presentOptions: "Préparation des options",
  runDeepResearch: "Recherche approfondie en cours",
  changeCity: "Changement de ville",
  changeCandidates: "Mise à jour des partis",
  removeRestrictions: "Suppression des restrictions",
  searchDataGouv: "Recherche sur data.gouv.fr",
  webSearch: "Recherche sur le web",
  renderWidget: "Génération du graphique",
  searchVotingRecords: "Votes parlementaires",
  searchParliamentaryQuestions: "Questions parlementaires",
};

export default function AiSdkToolResult({ part, onSendMessage }: Props) {
  const toolName = part.toolName ?? part.type.replace("tool-", "");
  const [expanded, setExpanded] = useState(false);

  // ── Searching / loading state ──────────────────────────────────────────────
  if (
    part.state === "partial-call" ||
    part.state === "call" ||
    part.state === "input-available" ||
    part.state === "input-streaming"
  ) {
    const input = (part.input ?? part.args ?? {}) as Record<string, unknown>;

    const baseLabel = TOOL_LOADING_LABELS[toolName] ?? "Traitement en cours";

    // Show partyId (readable) or candidateId for now (name will appear in result)
    let displayLabel = baseLabel;
    if (toolName === "searchDocumentsWithRerank") {
      // Show filter info if available
      const candidateIds = (input as any).candidateIds;
      const partyIds = (input as any).partyIds;
      if (candidateIds?.length) {
        displayLabel = `${baseLabel} (${candidateIds.length} candidat${candidateIds.length > 1 ? 's' : ''})`;
      } else if (partyIds?.length) {
        displayLabel = `${baseLabel} (${partyIds.length} parti${partyIds.length > 1 ? 's' : ''})`;
      }
    }

    return (
      <div className="my-2 flex items-center gap-2.5 rounded-xl border border-white/10 bg-white/5 p-3 text-xs">
        <span className="flex gap-1">
          <span className="bg-primary/70 size-1.5 animate-bounce rounded-full [animation-delay:-0.3s]" />
          <span className="bg-primary/70 size-1.5 animate-bounce rounded-full [animation-delay:-0.15s]" />
          <span className="bg-primary/70 size-1.5 animate-bounce rounded-full" />
        </span>
        <span className="text-muted-foreground">
          {displayLabel}...
        </span>
        {(input as any).query && (
          <span className="text-muted-foreground/50 truncate italic">
            &quot;{String((input as any).query)}&quot;
          </span>
        )}
      </div>
    );
  }

  // ── suggestFollowUps ───────────────────────────────────────────────────────
  if (toolName === "suggestFollowUps" && part.state === "output-available") {
    const result = part.output as { suggestions?: string[] };
    if (!result?.suggestions?.length) return null;

    return (
      <div className="mt-3 flex flex-wrap gap-2">
        {result.suggestions.map((suggestion, i) => (
          <button
            key={i}
            onClick={() => onSendMessage?.(suggestion)}
            className="inline-flex items-center gap-1.5 rounded-full border border-white/10 bg-white/5 px-3 py-1.5 text-xs text-purple-200 transition-colors hover:border-white/20 hover:bg-white/10"
          >
            <Sparkles className="text-primary/80 size-3 shrink-0" />
            {suggestion}
          </button>
        ))}
      </div>
    );
  }

  // ── runDeepResearch ────────────────────────────────────────────────────────
  if (toolName === "runDeepResearch") {
    if (part.state !== "output-available") {
      return (
        <div className="my-2 flex items-center gap-3 rounded-xl border border-purple-500/20 bg-purple-500/5 p-3">
          <div className="relative flex size-8 items-center justify-center">
            <div className="absolute inset-0 animate-ping rounded-full bg-purple-500/20" />
            <Search className="relative size-4 text-purple-300" />
          </div>
          <div className="flex flex-col gap-0.5">
            <span className="text-sm font-medium text-purple-200">
              Recherche approfondie en cours
            </span>
            <span className="text-muted-foreground text-xs">
              Reformulation et exploration multi-requêtes...
            </span>
          </div>
        </div>
      );
    }

    const result = part.output as {
      findings?: Array<{ content: string; source?: string; url?: string; score?: number; candidate_name?: string }>;
      totalFindings?: number;
      queriesTried?: string[];
      collectionsSearched?: string[];
      summary?: string;
      elapsedMs?: number;
    };

    return (
      <div className="my-2 rounded-xl border border-purple-500/20 bg-purple-500/5 p-3">
        <button
          onClick={() => setExpanded(!expanded)}
          className="flex w-full items-center gap-2 text-left"
        >
          <Search className="size-4 shrink-0 text-purple-300" />
          <span className="text-sm font-medium text-purple-200">
            Recherche approfondie
          </span>
          <span className="text-muted-foreground ml-1 text-xs">
            {result.totalFindings ?? 0} résultats · {result.queriesTried?.length ?? 0} requêtes · {result.elapsedMs ? `${(result.elapsedMs / 1000).toFixed(1)}s` : ''}
          </span>
          <span className="ml-auto">
            {expanded ? (
              <ChevronUp className="text-muted-foreground size-3.5" />
            ) : (
              <ChevronDown className="text-muted-foreground size-3.5" />
            )}
          </span>
        </button>
        {expanded && (
          <div className="mt-2 space-y-2 border-t border-purple-500/10 pt-2">
            {result.queriesTried && result.queriesTried.length > 0 && (
              <div className="flex flex-wrap gap-1">
                {result.queriesTried.map((q, i) => (
                  <span
                    key={i}
                    className="rounded-full bg-purple-500/10 px-2 py-0.5 text-[10px] text-purple-300"
                  >
                    {q}
                  </span>
                ))}
              </div>
            )}
            {result.findings?.slice(0, 6).map((f, i) => (
              <div
                key={i}
                className="rounded-lg border border-white/5 bg-white/5 p-2 text-xs"
              >
                {f.candidate_name && (
                  <span className="mb-1 inline-block rounded bg-purple-500/20 px-1.5 py-0.5 text-[10px] font-medium text-purple-200">
                    {f.candidate_name}
                  </span>
                )}
                <p className="text-muted-foreground line-clamp-3 leading-relaxed">
                  {f.content}
                </p>
                {f.source && (
                  <span className="text-muted-foreground mt-1 block text-[10px]">
                    {f.source}
                  </span>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    );
  }

  // ── presentOptions ─────────────────────────────────────────────────────────
  if (toolName === "presentOptions" && part.state === "output-available") {
    const result = part.output as { label?: string; options?: string[] };
    if (!result?.options?.length) return null;

    return (
      <div className="mt-3 flex flex-col gap-2">
        {result.label && (
          <span className="text-muted-foreground text-xs font-medium">
            {result.label}
          </span>
        )}
        <div className="flex flex-wrap gap-2">
          {result.options.map((option, i) => (
            <button
              key={i}
              onClick={() => onSendMessage?.(option)}
              className="inline-flex items-center gap-1.5 rounded-full border border-white/10 bg-white/5 px-3 py-1.5 text-xs transition-colors hover:border-white/20 hover:bg-white/10"
            >
              {option}
            </button>
          ))}
        </div>
      </div>
    );
  }

  // ── RAG search results (manifestos + candidate websites) ───────────────────
  if (
    part.state === "output-available" &&
    toolName === "searchDocumentsWithRerank"
  ) {
    return (
      <SourceResultCard
        output={part.output}
        query={(part.input as Record<string, unknown>)?.query as string ?? (part.args as Record<string, unknown>)?.query as string}
        expanded={expanded}
        setExpanded={setExpanded}
        icon={<Search className="size-3.5 shrink-0 text-purple-300" />}
        accentColor="border-l-purple-400/60"
        fiabilityLabel="🥈 Documents officiels"
      />
    );
  }

  // ── Voting records results ─────────────────────────────────────────────────
  if (toolName === "searchVotingRecords" && part.state === "output-available") {
    return (
      <SourceResultCard
        output={part.output}
        expanded={expanded}
        setExpanded={setExpanded}
        icon={<Vote className="size-3.5 shrink-0 text-violet-300" />}
        accentColor="border-l-violet-400/60"
        label="vote parlementaire"
        labelPlural="votes parlementaires"
      />
    );
  }

  // ── Parliamentary questions results ────────────────────────────────────────
  if (
    toolName === "searchParliamentaryQuestions" &&
    part.state === "output-available"
  ) {
    return (
      <SourceResultCard
        output={part.output}
        expanded={expanded}
        setExpanded={setExpanded}
        icon={<MessageSquare className="size-3.5 shrink-0 text-indigo-300" />}
        accentColor="border-l-indigo-400/60"
        label="question parlementaire"
        labelPlural="questions parlementaires"
      />
    );
  }

  // ── data.gouv.fr results ───────────────────────────────────────────────────
  if (toolName === "searchDataGouv" && part.state === "output-available") {
    const result = part.output as {
      datasets?: Array<{
        id: string;
        title: string;
        description: string;
        url: string;
        organization?: { name: string };
        resources?: Array<{ title: string; format: string; url: string }>;
      }>;
      count?: number;
    };
    const datasets = result?.datasets ?? [];
    const count = result?.count ?? datasets.length;

    return (
      <div className="my-2 overflow-hidden rounded-xl border border-l-2 border-white/10 border-l-blue-400/60 bg-white/5 text-xs backdrop-blur-sm">
        <button
          onClick={() => setExpanded((prev) => !prev)}
          className="flex w-full items-center gap-2 px-3 py-2 text-left transition-colors hover:bg-white/5"
        >
          <Database className="size-3.5 shrink-0 text-blue-300" />
          <span className="text-foreground/80 flex-1">
            {count} jeu{count !== 1 ? "x" : ""} de données trouvé
            {count !== 1 ? "s" : ""} sur{" "}
            <span className="text-foreground font-medium">data.gouv.fr</span>
          </span>
          {datasets.length > 0 &&
            (expanded ? (
              <ChevronUp className="text-muted-foreground size-3.5 shrink-0" />
            ) : (
              <ChevronDown className="text-muted-foreground size-3.5 shrink-0" />
            ))}
        </button>

        {expanded && datasets.length > 0 && (
          <ul className="divide-y divide-white/5 border-t border-white/10">
            {datasets.map((ds, i) => (
              <li key={ds.id ?? i} className="p-3">
                <div className="flex items-start gap-2">
                  <span className="bg-primary/15 text-primary flex size-5 shrink-0 items-center justify-center rounded-full text-[10px] font-semibold">
                    {i + 1}
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="text-foreground font-medium">
                      {ds.title}
                      {ds.url && (
                        <a
                          href={ds.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          onClick={(e) => e.stopPropagation()}
                          className="text-muted-foreground hover:text-foreground ml-1 inline-block transition-colors"
                        >
                          <ExternalLink className="inline size-3" />
                        </a>
                      )}
                    </p>
                    {ds.organization?.name && (
                      <p className="text-muted-foreground mt-0.5">
                        {ds.organization.name}
                      </p>
                    )}
                    {ds.description && (
                      <p className="text-foreground/60 mt-0.5 line-clamp-2 leading-snug">
                        {ds.description}
                      </p>
                    )}
                    {ds.resources && ds.resources.length > 0 && (
                      <div className="mt-1.5 flex flex-wrap gap-1">
                        {ds.resources.map((r, ri) => (
                          <a
                            key={ri}
                            href={r.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            onClick={(e) => e.stopPropagation()}
                            className="bg-primary/10 text-primary hover:bg-primary/20 inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-medium transition-colors"
                          >
                            {r.format?.toUpperCase() || "FILE"}
                          </a>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    );
  }

  // ── Web search results ─────────────────────────────────────────────────────
  if (toolName === "webSearch" && part.state === "output-available") {
    const result = part.output as {
      results?: Array<{
        id: number;
        title: string;
        snippet: string;
        url: string;
      }>;
      count?: number;
    };
    const webResults = result?.results ?? [];
    const count = result?.count ?? webResults.length;

    return (
      <div className="my-2 overflow-hidden rounded-xl border border-l-2 border-white/10 border-l-sky-400/60 bg-white/5 text-xs backdrop-blur-sm">
        <button
          onClick={() => setExpanded((prev) => !prev)}
          className="flex w-full items-center gap-2 px-3 py-2 text-left transition-colors hover:bg-white/5"
        >
          <Globe className="size-3.5 shrink-0 text-sky-300" />
          <span className="text-foreground/80 flex-1">
            <span className="text-muted-foreground/60 flex items-center gap-2 text-[10px]">
              <span className="shrink-0 rounded bg-amber-500/10 px-1.5 py-0.5 text-[9px] font-medium text-amber-300">⚠️ Non vérifié</span>
            </span>
            {count} résultat{count !== 1 ? "s" : ""} web
          </span>
          {webResults.length > 0 &&
            (expanded ? (
              <ChevronUp className="text-muted-foreground size-3.5 shrink-0" />
            ) : (
              <ChevronDown className="text-muted-foreground size-3.5 shrink-0" />
            ))}
        </button>

        {expanded && webResults.length > 0 && (
          <ul className="divide-y divide-white/5 border-t border-white/10">
            {webResults.map((wr, i) => (
              <li key={wr.id ?? i} className="flex gap-2 p-3">
                <span className="bg-primary/15 text-primary flex size-5 shrink-0 items-center justify-center rounded-full text-[10px] font-semibold">
                  {i + 1}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="text-foreground font-medium">
                    {wr.title}
                    {wr.url && (
                      <a
                        href={wr.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        onClick={(e) => e.stopPropagation()}
                        className="text-muted-foreground hover:text-foreground ml-1 inline-block transition-colors"
                      >
                        <ExternalLink className="inline size-3" />
                      </a>
                    )}
                  </p>
                  <p className="text-foreground/60 mt-0.5 line-clamp-2 leading-snug">
                    {wr.snippet}
                  </p>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    );
  }

  // ── Chart widget ───────────────────────────────────────────────────────────
  if (toolName === "renderWidget" && part.state === "output-available") {
    const result = part.output as {
      widget?: {
        type: "chart";
        chartType: "bar" | "pie" | "radar" | "line";
        title: string;
        data: Array<{ label: string; value: number; color?: string }>;
        xAxisLabel?: string;
        yAxisLabel?: string;
      };
    };
    if (!result?.widget) return null;
    const w = result.widget;
    return (
      <AiSdkChartWidget
        type="chart"
        chartType={w.chartType}
        title={w.title}
        data={w.data}
        xAxisLabel={w.xAxisLabel}
        yAxisLabel={w.yAxisLabel}
      />
    );
  }

  // ── changeCity ─────────────────────────────────────────────────────────────
  if (toolName === "changeCity" && part.state === "output-available") {
    const result = part.output as {
      action: string;
      cityName: string;
      municipalityCode?: string;
    };
    return (
      <div className="my-2 flex items-center gap-2 rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-xs">
        <MapPin className="size-3.5 shrink-0 text-purple-300" />
        <span className="text-foreground/70">
          Contexte changé :{" "}
          <span className="text-foreground font-medium">{result.cityName}</span>
        </span>
      </div>
    );
  }

  // ── changeCandidates ───────────────────────────────────────────────────────
  if (toolName === "changeCandidates" && part.state === "output-available") {
    const result = part.output as {
      action: string;
      partyIds: string[];
      operation: string;
    };
    return (
      <div className="my-2 flex items-center gap-2 rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-xs">
        <Users className="size-3.5 shrink-0 text-purple-300" />
        <span className="text-foreground/70">
          Partis mis à jour :{" "}
          <span className="text-foreground font-medium">
            {result.partyIds.join(", ")}
          </span>
        </span>
      </div>
    );
  }

  // ── removeRestrictions ─────────────────────────────────────────────────────
  if (toolName === "removeRestrictions" && part.state === "output-available") {
    return (
      <div className="my-2 flex items-center gap-2 rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-xs">
        <Unlock className="size-3.5 shrink-0 text-purple-300" />
        <span className="text-foreground/70">
          Restrictions supprimées — recherche nationale activée
        </span>
      </div>
    );
  }

  return null;
}

// ── Reusable source result card ──────────────────────────────────────────────

function SourceResultCard({
  output,
  query,
  expanded,
  setExpanded,
  icon,
  accentColor,
  label = "source",
  labelPlural = "sources",
  fiabilityLabel,
}: {
  output: unknown;
  query?: string;
  expanded: boolean;
  setExpanded: (fn: (prev: boolean) => boolean) => void;
  icon: React.ReactNode;
  accentColor: string;
  label?: string;
  labelPlural?: string;
  fiabilityLabel?: string;
}) {
  const result = output as {
    partyId?: string;
    candidateId?: string;
    candidateName?: string;
    results?: SearchResult[];
    documents?: Array<{ content: string }>;
    count?: number;
  };

  const sources = result?.results ?? [];
  const count = result?.count ?? result?.documents?.length ?? sources.length;
  // Extract unique candidate names from results for display
  const candidateNames = [...new Set(sources.map((s) => s.candidate_name).filter(Boolean))];
  // Show candidate names from results, or top-level candidateName, or partyId — never raw candidateId
  const entityLabel = candidateNames.length > 0
    ? candidateNames.join(", ")
    : result?.candidateName ?? result?.partyId;

  return (
    <div
      className={`my-2 overflow-hidden rounded-xl border border-l-2 border-white/10 ${accentColor} bg-white/5 text-xs backdrop-blur-sm`}
    >
      <button
        onClick={() => setExpanded((prev) => !prev)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left transition-colors hover:bg-white/5"
      >
        {icon}
        <span className="text-foreground/80 flex-1">
          {(query || fiabilityLabel) && (
            <span className="text-muted-foreground/60 flex items-center gap-2 text-[10px]">
              {query && <span className="truncate italic">{query}</span>}
              {fiabilityLabel && <span className="shrink-0 rounded bg-white/5 px-1.5 py-0.5 text-[9px] font-medium">{fiabilityLabel}</span>}
            </span>
          )}
          {entityLabel ? (
            <>
              <span className="text-foreground font-medium">
                {candidateNames.length > 0 || result?.candidateName ? entityLabel : entityLabel.toUpperCase()}
              </span>
              {" — "}
              {count} {count !== 1 ? labelPlural : label}
            </>
          ) : (
            <>
              {count} {count !== 1 ? labelPlural : label} trouvée
              {count !== 1 ? "s" : ""}
            </>
          )}
        </span>
        {sources.length > 0 &&
          (expanded ? (
            <ChevronUp className="text-muted-foreground size-3.5 shrink-0" />
          ) : (
            <ChevronDown className="text-muted-foreground size-3.5 shrink-0" />
          ))}
      </button>

      {expanded && sources.length > 0 && (
        <ul className="divide-y divide-white/5 border-t border-white/10">
          {sources.map((src, i) => (
            <li key={src.id ?? i} className="flex gap-2 p-3">
              <span className="flex size-5 shrink-0 items-center justify-center rounded-full bg-purple-500/30 text-[10px] font-semibold text-purple-200">
                {i + 1}
              </span>
              <div className="min-w-0 flex-1">
                {(src.candidate_name || (src.party_id && !src.party_id.startsWith("cand-"))) && (
                  <div className="mb-1 flex flex-wrap items-center gap-1">
                    {src.candidate_name && (
                      <span className="inline-block rounded bg-purple-500/20 px-1.5 py-0.5 text-[10px] font-medium text-purple-200">
                        {src.candidate_name}
                      </span>
                    )}
                    {src.party_id && !src.party_id.startsWith("cand-") && (
                      <span className="inline-block rounded bg-blue-500/20 px-1.5 py-0.5 text-[10px] font-medium text-blue-200">
                        {src.party_id.toUpperCase()}
                      </span>
                    )}
                  </div>
                )}
                <p className="text-foreground/80 line-clamp-3 leading-snug">
                  {src.content.length > 150
                    ? src.content.slice(0, 150) + "…"
                    : src.content}
                </p>
                <div className="text-muted-foreground mt-1 flex items-center gap-1">
                  {src.source && (
                    <span className="truncate font-medium">{src.source}</span>
                  )}
                  {src.page != null && src.page !== "" && (
                    <span className="shrink-0">· p.{src.page}</span>
                  )}
                  {src.url && (
                    <a
                      href={src.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      onClick={(e) => e.stopPropagation()}
                      className="hover:text-foreground ml-auto shrink-0 transition-colors"
                    >
                      <ExternalLink className="size-3" />
                    </a>
                  )}
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

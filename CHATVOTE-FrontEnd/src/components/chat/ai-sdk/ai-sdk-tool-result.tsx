'use client';

import {
  ChevronDown,
  ChevronUp,
  Database,
  ExternalLink,
  Globe,
  Loader2,
  MapPin,
  MessageSquare,
  Search,
  Sparkles,
  Unlock,
  Users,
  Vote,
} from 'lucide-react';
import { useState } from 'react';
import dynamic from 'next/dynamic';

const AiSdkChartWidget = dynamic(() => import('./ai-sdk-chart-widget'), {
  ssr: false,
  loading: () => (
    <div className="bg-muted/50 my-2 flex items-center gap-2 rounded-lg border p-3 text-sm">
      <Loader2 className="text-primary size-4 animate-spin" />
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
  searchPartyManifesto: 'Recherche dans le programme',
  searchCandidateWebsite: 'Recherche sur le site du candidat',
  suggestFollowUps: 'Génération de suggestions',
  changeCity: 'Changement de ville',
  changeCandidates: 'Mise à jour des partis',
  removeRestrictions: 'Suppression des restrictions',
  searchDataGouv: 'Recherche sur data.gouv.fr',
  webSearch: 'Recherche sur le web',
  renderWidget: 'Génération du graphique',
  searchVotingRecords: 'Recherche des votes parlementaires',
  searchParliamentaryQuestions: 'Recherche des questions parlementaires',
};

export default function AiSdkToolResult({ part, onSendMessage }: Props) {
  const toolName = part.toolName ?? part.type.replace('tool-', '');
  const [expanded, setExpanded] = useState(false);

  // ── Searching / loading state ──────────────────────────────────────────────
  if (
    part.state === 'partial-call' ||
    part.state === 'call' ||
    part.state === 'input-available' ||
    part.state === 'input-streaming'
  ) {
    const input = (part.input ?? part.args ?? {}) as Record<string, string>;
    const partyId = input.partyId;
    const query = input.query;

    const label = TOOL_LOADING_LABELS[toolName] ?? 'Traitement en cours';
    const suffix =
      toolName === 'searchPartyManifesto' && partyId
        ? ` de ${partyId.toUpperCase()}`
        : '';

    return (
      <div className="bg-muted/50 my-2 flex items-center gap-2 rounded-lg border p-3 text-sm">
        <Loader2 className="text-primary size-4 animate-spin" />
        <span className="text-muted-foreground">
          {label}
          {suffix}...
        </span>
        {query && (
          <span className="text-muted-foreground/60 truncate text-xs italic">
            &quot;{query}&quot;
          </span>
        )}
      </div>
    );
  }

  // ── suggestFollowUps ───────────────────────────────────────────────────────
  if (toolName === 'suggestFollowUps' && part.state === 'output-available') {
    const result = part.output as { suggestions?: string[] };
    if (!result?.suggestions?.length) return null;

    return (
      <div className="mt-3 flex flex-wrap gap-2">
        {result.suggestions.map((suggestion, i) => (
          <button
            key={i}
            onClick={() => onSendMessage?.(suggestion)}
            className="bg-background hover:bg-accent rounded-full border px-3 py-1.5 text-xs transition-colors"
          >
            <Sparkles className="mr-1 inline size-3" />
            {suggestion}
          </button>
        ))}
      </div>
    );
  }

  // ── RAG search results (manifestos + candidate websites) ───────────────────
  if (
    part.state === 'output-available' &&
    (toolName === 'searchPartyManifesto' || toolName === 'searchCandidateWebsite')
  ) {
    return (
      <SourceResultCard
        output={part.output}
        expanded={expanded}
        setExpanded={setExpanded}
        icon={<Search className="size-3.5 shrink-0 text-green-600 dark:text-green-400" />}
        colorScheme="green"
      />
    );
  }

  // ── Voting records results ─────────────────────────────────────────────────
  if (toolName === 'searchVotingRecords' && part.state === 'output-available') {
    return (
      <SourceResultCard
        output={part.output}
        expanded={expanded}
        setExpanded={setExpanded}
        icon={<Vote className="size-3.5 shrink-0 text-purple-600 dark:text-purple-400" />}
        colorScheme="purple"
        label="vote parlementaire"
        labelPlural="votes parlementaires"
      />
    );
  }

  // ── Parliamentary questions results ────────────────────────────────────────
  if (toolName === 'searchParliamentaryQuestions' && part.state === 'output-available') {
    return (
      <SourceResultCard
        output={part.output}
        expanded={expanded}
        setExpanded={setExpanded}
        icon={
          <MessageSquare className="size-3.5 shrink-0 text-indigo-600 dark:text-indigo-400" />
        }
        colorScheme="indigo"
        label="question parlementaire"
        labelPlural="questions parlementaires"
      />
    );
  }

  // ── data.gouv.fr results ───────────────────────────────────────────────────
  if (toolName === 'searchDataGouv' && part.state === 'output-available') {
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
      <div className="my-2 overflow-hidden rounded-lg border border-sky-200 bg-sky-50 text-xs dark:border-sky-900 dark:bg-sky-950">
        <button
          onClick={() => setExpanded((prev) => !prev)}
          className="flex w-full items-center gap-2 p-2 text-left transition-colors hover:bg-sky-100 dark:hover:bg-sky-900/50"
        >
          <Database className="size-3.5 shrink-0 text-sky-600 dark:text-sky-400" />
          <span className="flex-1 text-sky-800 dark:text-sky-200">
            {count} jeu{count !== 1 ? 'x' : ''} de données trouvé{count !== 1 ? 's' : ''} sur
            data.gouv.fr
          </span>
          {datasets.length > 0 &&
            (expanded ? (
              <ChevronUp className="size-3.5 shrink-0 text-sky-600 dark:text-sky-400" />
            ) : (
              <ChevronDown className="size-3.5 shrink-0 text-sky-600 dark:text-sky-400" />
            ))}
        </button>

        {expanded && datasets.length > 0 && (
          <ul className="divide-y divide-sky-200 border-t border-sky-200 dark:divide-sky-900 dark:border-sky-900">
            {datasets.map((ds, i) => (
              <li key={ds.id ?? i} className="p-2">
                <div className="flex items-start gap-2">
                  <span className="flex size-5 shrink-0 items-center justify-center rounded-full bg-sky-200 text-[10px] font-semibold text-sky-800 dark:bg-sky-800 dark:text-sky-200">
                    {i + 1}
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="font-medium text-sky-900 dark:text-sky-100">
                      {ds.title}
                      {ds.url && (
                        <a
                          href={ds.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          onClick={(e) => e.stopPropagation()}
                          className="ml-1 inline-block hover:text-sky-600 dark:hover:text-sky-300"
                        >
                          <ExternalLink className="inline size-3" />
                        </a>
                      )}
                    </p>
                    {ds.organization?.name && (
                      <p className="text-sky-700 dark:text-sky-400">{ds.organization.name}</p>
                    )}
                    {ds.description && (
                      <p className="mt-0.5 line-clamp-2 leading-snug text-sky-900/70 dark:text-sky-100/70">
                        {ds.description}
                      </p>
                    )}
                    {ds.resources && ds.resources.length > 0 && (
                      <div className="mt-1 flex flex-wrap gap-1">
                        {ds.resources.map((r, ri) => (
                          <a
                            key={ri}
                            href={r.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            onClick={(e) => e.stopPropagation()}
                            className="inline-flex items-center gap-0.5 rounded bg-sky-200/60 px-1.5 py-0.5 text-[10px] font-medium text-sky-800 hover:bg-sky-300/60 dark:bg-sky-800/60 dark:text-sky-200 dark:hover:bg-sky-700/60"
                          >
                            {r.format?.toUpperCase() || 'FILE'}
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
  if (toolName === 'webSearch' && part.state === 'output-available') {
    const result = part.output as {
      results?: Array<{ id: number; title: string; snippet: string; url: string }>;
      count?: number;
    };
    const webResults = result?.results ?? [];
    const count = result?.count ?? webResults.length;

    return (
      <div className="my-2 overflow-hidden rounded-lg border border-teal-200 bg-teal-50 text-xs dark:border-teal-900 dark:bg-teal-950">
        <button
          onClick={() => setExpanded((prev) => !prev)}
          className="flex w-full items-center gap-2 p-2 text-left transition-colors hover:bg-teal-100 dark:hover:bg-teal-900/50"
        >
          <Globe className="size-3.5 shrink-0 text-teal-600 dark:text-teal-400" />
          <span className="flex-1 text-teal-800 dark:text-teal-200">
            {count} résultat{count !== 1 ? 's' : ''} web
          </span>
          {webResults.length > 0 &&
            (expanded ? (
              <ChevronUp className="size-3.5 shrink-0 text-teal-600 dark:text-teal-400" />
            ) : (
              <ChevronDown className="size-3.5 shrink-0 text-teal-600 dark:text-teal-400" />
            ))}
        </button>

        {expanded && webResults.length > 0 && (
          <ul className="divide-y divide-teal-200 border-t border-teal-200 dark:divide-teal-900 dark:border-teal-900">
            {webResults.map((wr, i) => (
              <li key={wr.id ?? i} className="flex gap-2 p-2">
                <span className="flex size-5 shrink-0 items-center justify-center rounded-full bg-teal-200 text-[10px] font-semibold text-teal-800 dark:bg-teal-800 dark:text-teal-200">
                  {i + 1}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="font-medium text-teal-900 dark:text-teal-100">
                    {wr.title}
                    {wr.url && (
                      <a
                        href={wr.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        onClick={(e) => e.stopPropagation()}
                        className="ml-1 inline-block hover:text-teal-600 dark:hover:text-teal-300"
                      >
                        <ExternalLink className="inline size-3" />
                      </a>
                    )}
                  </p>
                  <p className="mt-0.5 line-clamp-2 leading-snug text-teal-900/70 dark:text-teal-100/70">
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
  if (toolName === 'renderWidget' && part.state === 'output-available') {
    const result = part.output as {
      widget?: {
        type: 'chart';
        chartType: 'bar' | 'pie' | 'radar' | 'line';
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
  if (toolName === 'changeCity' && part.state === 'output-available') {
    const result = part.output as { action: string; cityName: string; municipalityCode?: string };
    return (
      <div className="my-2 flex items-center gap-2 rounded-lg border border-blue-200 bg-blue-50 p-2 text-xs dark:border-blue-900 dark:bg-blue-950">
        <MapPin className="size-3.5 text-blue-600 dark:text-blue-400" />
        <span className="text-blue-800 dark:text-blue-200">
          Contexte changé : <strong>{result.cityName}</strong>
        </span>
      </div>
    );
  }

  // ── changeCandidates ───────────────────────────────────────────────────────
  if (toolName === 'changeCandidates' && part.state === 'output-available') {
    const result = part.output as { action: string; partyIds: string[]; operation: string };
    return (
      <div className="my-2 flex items-center gap-2 rounded-lg border border-blue-200 bg-blue-50 p-2 text-xs dark:border-blue-900 dark:bg-blue-950">
        <Users className="size-3.5 text-blue-600 dark:text-blue-400" />
        <span className="text-blue-800 dark:text-blue-200">
          Partis mis à jour : <strong>{result.partyIds.join(', ')}</strong>
        </span>
      </div>
    );
  }

  // ── removeRestrictions ─────────────────────────────────────────────────────
  if (toolName === 'removeRestrictions' && part.state === 'output-available') {
    return (
      <div className="my-2 flex items-center gap-2 rounded-lg border border-blue-200 bg-blue-50 p-2 text-xs dark:border-blue-900 dark:bg-blue-950">
        <Unlock className="size-3.5 text-blue-600 dark:text-blue-400" />
        <span className="text-blue-800 dark:text-blue-200">
          Restrictions supprimées — recherche nationale activée
        </span>
      </div>
    );
  }

  return null;
}

// ── Reusable source result card ──────────────────────────────────────────────
type ColorScheme = 'green' | 'purple' | 'indigo';

const COLOR_CLASSES: Record<
  ColorScheme,
  {
    border: string;
    bg: string;
    hoverBg: string;
    text: string;
    textStrong: string;
    badge: string;
    badgeText: string;
    divider: string;
    icon: string;
  }
> = {
  green: {
    border: 'border-green-200 dark:border-green-900',
    bg: 'bg-green-50 dark:bg-green-950',
    hoverBg: 'hover:bg-green-100 dark:hover:bg-green-900/50',
    text: 'text-green-800 dark:text-green-200',
    textStrong: 'text-green-900 dark:text-green-100',
    badge: 'bg-green-200 dark:bg-green-800',
    badgeText: 'text-green-800 dark:text-green-200',
    divider: 'divide-green-200 dark:divide-green-900 border-green-200 dark:border-green-900',
    icon: 'text-green-600 dark:text-green-400',
  },
  purple: {
    border: 'border-purple-200 dark:border-purple-900',
    bg: 'bg-purple-50 dark:bg-purple-950',
    hoverBg: 'hover:bg-purple-100 dark:hover:bg-purple-900/50',
    text: 'text-purple-800 dark:text-purple-200',
    textStrong: 'text-purple-900 dark:text-purple-100',
    badge: 'bg-purple-200 dark:bg-purple-800',
    badgeText: 'text-purple-800 dark:text-purple-200',
    divider:
      'divide-purple-200 dark:divide-purple-900 border-purple-200 dark:border-purple-900',
    icon: 'text-purple-600 dark:text-purple-400',
  },
  indigo: {
    border: 'border-indigo-200 dark:border-indigo-900',
    bg: 'bg-indigo-50 dark:bg-indigo-950',
    hoverBg: 'hover:bg-indigo-100 dark:hover:bg-indigo-900/50',
    text: 'text-indigo-800 dark:text-indigo-200',
    textStrong: 'text-indigo-900 dark:text-indigo-100',
    badge: 'bg-indigo-200 dark:bg-indigo-800',
    badgeText: 'text-indigo-800 dark:text-indigo-200',
    divider:
      'divide-indigo-200 dark:divide-indigo-900 border-indigo-200 dark:border-indigo-900',
    icon: 'text-indigo-600 dark:text-indigo-400',
  },
};

function SourceResultCard({
  output,
  expanded,
  setExpanded,
  icon,
  colorScheme,
  label = 'source',
  labelPlural = 'sources',
}: {
  output: unknown;
  expanded: boolean;
  setExpanded: (fn: (prev: boolean) => boolean) => void;
  icon: React.ReactNode;
  colorScheme: ColorScheme;
  label?: string;
  labelPlural?: string;
}) {
  const result = output as {
    partyId?: string;
    candidateId?: string;
    results?: SearchResult[];
    documents?: Array<{ content: string }>;
    count?: number;
  };

  const sources = result?.results ?? [];
  const count = result?.count ?? result?.documents?.length ?? sources.length;
  const entityLabel = result?.partyId ?? result?.candidateId;
  const c = COLOR_CLASSES[colorScheme];

  return (
    <div className={`my-2 overflow-hidden rounded-lg border ${c.border} ${c.bg} text-xs`}>
      <button
        onClick={() => setExpanded((prev) => !prev)}
        className={`flex w-full items-center gap-2 p-2 text-left transition-colors ${c.hoverBg}`}
      >
        {icon}
        <span className={`flex-1 ${c.text}`}>
          {count} {count !== 1 ? labelPlural : label} trouvée{count !== 1 ? 's' : ''}
          {entityLabel && (
            <>
              {' '}
              pour <strong>{entityLabel.toUpperCase()}</strong>
            </>
          )}
        </span>
        {sources.length > 0 &&
          (expanded ? (
            <ChevronUp className={`size-3.5 shrink-0 ${c.icon}`} />
          ) : (
            <ChevronDown className={`size-3.5 shrink-0 ${c.icon}`} />
          ))}
      </button>

      {expanded && sources.length > 0 && (
        <ul className={`divide-y border-t ${c.divider}`}>
          {sources.map((src, i) => (
            <li key={src.id ?? i} className="flex gap-2 p-2">
              <span
                className={`flex size-5 shrink-0 items-center justify-center rounded-full text-[10px] font-semibold ${c.badge} ${c.badgeText}`}
              >
                {i + 1}
              </span>
              <div className="min-w-0 flex-1">
                <p className={`line-clamp-3 leading-snug ${c.textStrong}`}>
                  {src.content.length > 150 ? src.content.slice(0, 150) + '…' : src.content}
                </p>
                <div className={`mt-1 flex items-center gap-1 ${c.icon}`}>
                  {src.source && <span className="truncate font-medium">{src.source}</span>}
                  {src.page != null && src.page !== '' && (
                    <span className="shrink-0">· p.{src.page}</span>
                  )}
                  {src.url && (
                    <a
                      href={src.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      onClick={(e) => e.stopPropagation()}
                      className={`ml-auto shrink-0 hover:${c.textStrong}`}
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

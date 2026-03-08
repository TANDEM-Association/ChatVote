"use client";

import { useEffect, useRef, useState } from "react";

import Link from "next/link";
import { useParams } from "next/navigation";

import { MessageCircle } from "lucide-react";

import {
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
  ResponsiveContainer,
} from "recharts";

import { Badge } from "@components/ui/badge";
import { Button } from "@components/ui/button";
import { Separator } from "@components/ui/separator";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type ListInfo = {
  panel_number: number;
  list_label: string;
  list_short_label: string;
  head_first_name: string;
  head_last_name: string;
  nuance_code: string | null;
  nuance_label: string | null;
};

type TaxonomyTheme = {
  theme: string;
  total_count: number;
  percentage: number;
  by_list: Record<string, number>;
};

type BertopicTopic = {
  topic_id: number;
  label: string;
  count: number;
  percentage: number;
  words: Array<{ word: string; weight: number }>;
  representative_messages: Array<{
    text: string;
    session_id: string;
    chat_title: string;
  }>;
};

type DashboardData = {
  commune: {
    code: string;
    name: string;
    postal_code: string;
    epci_nom: string;
    list_count: number;
    lists: ListInfo[];
  };
  stats: {
    total_questions: number;
    total_lists: number;
    total_chunks: number;
    themes_detected: number;
  };
  taxonomy: {
    themes: TaxonomyTheme[];
  };
  bertopic: {
    status: string;
    message?: string;
    total_messages: number;
    num_topics: number;
    topics: BertopicTopic[];
  };
};

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const LIST_COLORS = [
  "#7C3AED", // violet-600
  "#6D28D9", // violet-700
  "#A78BFA", // violet-400
  "#C084FC", // purple-400
  "#818CF8", // indigo-400
  "#67E8F9", // cyan-300
  "#94A3B8", // slate-400
  "#CBD5E1", // slate-300
  "#E879F9", // fuchsia-400
];

function listColor(index: number): string {
  return LIST_COLORS[index % LIST_COLORS.length];
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function normalize(values: number[]): number[] {
  const max = Math.max(...values, 1);
  return values.map((v) => Math.round((v / max) * 100));
}

type RadarEntry = {
  theme: string;
  citizen: number;
  program: number;
};

function buildRadarData(
  themes: TaxonomyTheme[],
  listLabel: string,
): RadarEntry[] {
  const citizenRaw = themes.map((t) => t.total_count);
  const programRaw = themes.map((t) => t.by_list[listLabel] ?? 0);
  const citizenNorm = normalize(citizenRaw);
  const programNorm = normalize(programRaw);

  return themes.map((t, i) => ({
    theme:
      t.theme.length > 14 ? t.theme.slice(0, 13) + "…" : t.theme,
    citizen: citizenNorm[i],
    program: programNorm[i],
  }));
}

function buildCombinedRadarData(
  themes: TaxonomyTheme[],
  lists: ListInfo[],
): Array<Record<string, string | number>> {
  return themes.map((t) => {
    const entry: Record<string, string | number> = {
      theme: t.theme.length > 14 ? t.theme.slice(0, 13) + "…" : t.theme,
    };
    // Normalize each list's values relative to the max across all lists for this theme
    const values = lists.map((l) => t.by_list[l.list_label] ?? 0);
    const max = Math.max(...values, 1);
    lists.forEach((l) => {
      entry[l.list_short_label || l.list_label] = Math.round(
        ((t.by_list[l.list_label] ?? 0) / max) * 100,
      );
    });
    return entry;
  });
}

function alignmentScore(data: RadarEntry[]): number {
  if (data.length === 0) return 0;
  const scores = data.map(({ citizen, program }) => {
    const mx = Math.max(citizen, program, 1);
    const mn = Math.min(citizen, program);
    return mn / mx;
  });
  return Math.round((scores.reduce((a, b) => a + b, 0) / scores.length) * 100);
}

function blindSpots(data: RadarEntry[], topN = 5): string[] {
  const sorted = [...data].sort((a, b) => b.citizen - a.citizen);
  const top = sorted.slice(0, topN);
  return top
    .filter(({ program }) => program < 30)
    .map(({ theme }) => theme);
}

function scoreColor(score: number): string {
  if (score >= 70) return "text-green-500";
  if (score >= 55) return "text-amber-500";
  return "text-red-500";
}

function scoreBg(score: number): string {
  if (score >= 70) return "bg-green-500/10 border-green-500/30";
  if (score >= 55) return "bg-amber-500/10 border-amber-500/30";
  return "bg-red-500/10 border-red-500/30";
}

// ---------------------------------------------------------------------------
// Sub-components
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
    <div className="bg-surface border border-border-subtle rounded-xl flex-1 min-w-0 overflow-hidden">
      <div className="h-[3px] w-full" style={{ backgroundColor: accentColor }} />
      <div className="p-4 pt-3">
        <p className="text-3xl font-extrabold text-foreground leading-none">
          {value}
        </p>
        <p className="mt-1 text-xs uppercase text-muted-foreground tracking-wider">
          {label}
        </p>
      </div>
    </div>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-3 mb-4">
      <span className="text-xs font-semibold uppercase tracking-widest text-muted-foreground whitespace-nowrap">
        {children}
      </span>
      <div className="flex-1 border-t border-border-subtle" />
    </div>
  );
}

function ThermometerBar({
  rank,
  label,
  count,
  percentage,
  isTop3,
}: {
  rank: number;
  label: string;
  count: number;
  percentage: number;
  isTop3: boolean;
}) {
  const barRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = barRef.current;
    if (!el) return;
    // Start at 0, animate to target width
    el.style.width = "0%";
    const raf = requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        el.style.width = `${percentage}%`;
      });
    });
    return () => cancelAnimationFrame(raf);
  }, [percentage]);

  return (
    <div className="flex items-center gap-3 py-1.5">
      <span className="w-5 text-right text-xs font-bold text-muted-foreground shrink-0">
        {rank}.
      </span>
      <span className="w-40 text-sm text-foreground truncate shrink-0">
        {label}
      </span>
      <div className="flex-1 h-6 bg-border-subtle/40 rounded-full overflow-hidden relative">
        <div
          ref={barRef}
          className="h-full rounded-full flex items-center justify-end pr-2 transition-[width] duration-700 ease-out"
          style={{
            width: "0%",
            background: isTop3
              ? "linear-gradient(90deg, #381AF3, #8B5CF6)"
              : "#381AF3",
          }}
        >
          <span className="text-[10px] text-white font-semibold whitespace-nowrap">
            {count} extraits
          </span>
        </div>
      </div>
      <span className="w-10 text-right text-sm font-semibold text-foreground shrink-0">
        {percentage.toFixed(1)}%
      </span>
    </div>
  );
}

function LegendBar({ lists }: { lists: ListInfo[] }) {
  return (
    <div className="flex flex-wrap items-center gap-x-5 gap-y-2 py-2">
      <div className="flex items-center gap-2">
        <svg width="28" height="10">
          <line
            x1="0"
            y1="5"
            x2="28"
            y2="5"
            stroke="#a1a1aa"
            strokeWidth="2"
            strokeDasharray="4 3"
          />
        </svg>
        <span className="text-xs text-muted-foreground">
          Préoccupations citoyennes
        </span>
      </div>
      {lists.map((list, i) => (
        <div key={list.panel_number} className="flex items-center gap-2">
          <span
            className="inline-block w-3 h-3 rounded-sm"
            style={{ backgroundColor: listColor(i) }}
          />
          <span className="text-xs text-muted-foreground">
            {list.list_short_label || list.list_label}
          </span>
        </div>
      ))}
    </div>
  );
}

function RadarCard({
  list,
  listIndex,
  themes,
}: {
  list: ListInfo;
  listIndex: number;
  themes: TaxonomyTheme[];
}) {
  const color = listColor(listIndex);
  const headName = `${list.head_first_name} ${list.head_last_name}`;
  const radarData = buildRadarData(themes, list.list_label);
  const score = alignmentScore(radarData);
  const blind = blindSpots(radarData);

  return (
    <div className="bg-surface border border-border-subtle rounded-xl overflow-hidden flex flex-col">
      <div className="h-[3px] w-full" style={{ backgroundColor: color }} />
      <div className="p-4 flex flex-col gap-3 flex-1">
        <div>
          <p className="font-bold text-foreground text-sm leading-tight">
            {headName}
          </p>
          <p className="text-xs uppercase text-muted-foreground tracking-wider mt-0.5 truncate">
            {list.list_short_label || list.list_label}
          </p>
        </div>

        <div className="w-full aspect-square">
          <ResponsiveContainer width="100%" height="100%">
            <RadarChart data={radarData} margin={{ top: 10, right: 20, bottom: 10, left: 20 }}>
              <PolarGrid stroke="#2E275A" />
              <PolarAngleAxis
                dataKey="theme"
                tick={{ fill: "#a1a1aa", fontSize: 9 }}
              />
              <PolarRadiusAxis
                angle={30}
                domain={[0, 100]}
                tick={false}
                axisLine={false}
              />
              <Radar
                name="Citoyens"
                dataKey="citizen"
                stroke="#a1a1aa"
                fill="transparent"
                strokeDasharray="4 3"
                strokeWidth={1.5}
              />
              <Radar
                name="Programme"
                dataKey="program"
                stroke={color}
                fill={color}
                fillOpacity={0.15}
                strokeWidth={2}
              />
            </RadarChart>
          </ResponsiveContainer>
        </div>

        <div
          className={`border rounded-lg px-3 py-2 flex items-center justify-between ${scoreBg(score)}`}
        >
          <span className="text-xs text-muted-foreground">Alignement</span>
          <span className={`text-xl font-extrabold ${scoreColor(score)}`}>
            {score}%
          </span>
        </div>

        {blind.length > 0 && (
          <div>
            <p className="text-[10px] uppercase text-muted-foreground tracking-wider mb-1.5">
              Angles morts
            </p>
            <div className="flex flex-wrap gap-1">
              {blind.map((theme) => (
                <span
                  key={theme}
                  className="inline-block text-[10px] bg-red-500/10 text-red-400 border border-red-500/20 rounded px-1.5 py-0.5"
                >
                  {theme}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function CombinedRadarSection({
  themes,
  lists,
}: {
  themes: TaxonomyTheme[];
  lists: ListInfo[];
}) {
  const data = buildCombinedRadarData(themes, lists);

  return (
    <section>
      <SectionLabel>🗺️ Vue d&apos;ensemble — Couverture thématique comparée</SectionLabel>
      <div className="bg-surface border border-border-subtle rounded-xl p-6">
        <div className="max-w-2xl mx-auto aspect-square">
          <ResponsiveContainer width="100%" height="100%">
            <RadarChart data={data} margin={{ top: 20, right: 40, bottom: 20, left: 40 }}>
              <PolarGrid stroke="#2E275A" />
              <PolarAngleAxis
                dataKey="theme"
                tick={{ fill: "#a1a1aa", fontSize: 11 }}
              />
              <PolarRadiusAxis
                angle={30}
                domain={[0, 100]}
                tick={false}
                axisLine={false}
              />
              {lists.map((list, i) => (
                <Radar
                  key={list.panel_number}
                  name={list.list_short_label || list.list_label}
                  dataKey={list.list_short_label || list.list_label}
                  stroke={listColor(i)}
                  fill={listColor(i)}
                  fillOpacity={0.05}
                  strokeWidth={2}
                />
              ))}
            </RadarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function CommuneDashboardPage() {
  const params = useParams<{ communeCode: string }>();
  const communeCode = params.communeCode;

  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = () => {
    setLoading(true);
    setError(null);
    fetch(`/api/commune/${communeCode}/dashboard`)
      .then((res) => {
        if (!res.ok) throw new Error(`Erreur ${res.status}`);
        return res.json() as Promise<DashboardData>;
      })
      .then((d) => {
        setData(d);
        setLoading(false);
      })
      .catch((err: unknown) => {
        setError(
          err instanceof Error ? err.message : "Erreur inconnue",
        );
        setLoading(false);
      });
  };

  useEffect(() => {
    fetchData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [communeCode]);

  // ---- Loading state -------------------------------------------------------
  if (loading) {
    return (
      <div className="overflow-y-auto h-screen bg-background flex items-center justify-center">
        <div className="flex flex-col items-center gap-4 text-muted-foreground">
          <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin" />
          <p className="text-sm">Chargement du tableau de bord…</p>
        </div>
      </div>
    );
  }

  // ---- Error state ---------------------------------------------------------
  if (error || !data) {
    return (
      <div className="overflow-y-auto h-screen bg-background flex items-center justify-center">
        <div className="flex flex-col items-center gap-4 text-center max-w-sm">
          <p className="text-destructive font-semibold">
            {error ?? "Données introuvables"}
          </p>
          <p className="text-sm text-muted-foreground">
            Impossible de charger le tableau de bord pour la commune{" "}
            <span className="font-mono">{communeCode}</span>.
          </p>
          <Button variant="outline" onClick={fetchData}>
            Réessayer
          </Button>
        </div>
      </div>
    );
  }

  const { commune, stats, taxonomy } = data;

  return (
    <div className="overflow-y-auto h-screen bg-background text-foreground">
      {/* ------------------------------------------------------------------ */}
      {/* Commune header                                                       */}
      {/* ------------------------------------------------------------------ */}
      <div className="bg-purple-900 bg-gradient-to-r from-purple-900 to-purple-800 border-b border-border-subtle">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 py-5 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <div className="flex items-center gap-3">
            <Badge className="bg-primary/20 text-primary border border-primary/30 text-[10px] font-bold uppercase tracking-widest px-2 py-0.5">
              Commune
            </Badge>
            <h1 className="text-2xl sm:text-3xl font-extrabold text-white tracking-tight">
              {commune.name}
            </h1>
          </div>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-purple-200">
            {commune.postal_code && (
              <span>CP {commune.postal_code}</span>
            )}
            <span>INSEE {commune.code}</span>
            {commune.epci_nom && (
              <>
                <Separator orientation="vertical" className="h-3 bg-purple-600 hidden sm:block" />
                <span className="truncate max-w-[18rem]">{commune.epci_nom}</span>
              </>
            )}
            <Separator orientation="vertical" className="h-3 bg-purple-600 hidden sm:block" />
            <span>
              {commune.list_count} liste{commune.list_count !== 1 ? "s" : ""}
            </span>
            <span>·</span>
            <span>
              {stats.total_questions} question{stats.total_questions !== 1 ? "s" : ""}
            </span>
          </div>
          <Link
            href={`/chat?municipality_code=${commune.code}`}
            className="inline-flex items-center gap-2 rounded-lg bg-white/10 px-4 py-2 text-sm font-medium text-white transition hover:bg-white/20"
          >
            <MessageCircle className="size-4" />
            Poser une question
          </Link>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 py-6 space-y-8">
        {/* ---------------------------------------------------------------- */}
        {/* Stats row                                                         */}
        {/* ---------------------------------------------------------------- */}
        <div className="flex gap-3 flex-wrap sm:flex-nowrap">
          <StatCard
            value={stats.total_questions}
            label="Questions citoyennes"
            accentColor="#7C3AED"
          />
          <StatCard
            value={stats.total_lists}
            label="Listes en compétition"
            accentColor="#A78BFA"
          />
          <StatCard
            value={stats.themes_detected}
            label="Thèmes détectés"
            accentColor="#818CF8"
          />
          <StatCard
            value={stats.total_chunks}
            label="Extraits de programme"
            accentColor="#94A3B8"
          />
        </div>

        {/* ---------------------------------------------------------------- */}
        {/* Thermometre citoyen                                               */}
        {/* ---------------------------------------------------------------- */}
        <section>
          <SectionLabel>🌡️ Couverture thématique — Répartition des programmes</SectionLabel>

          {taxonomy.themes.length === 0 ? (
            <div className="bg-surface border border-border-subtle rounded-xl p-6 text-center text-muted-foreground text-sm">
              Pas assez de données pour l&apos;analyse thématique
            </div>
          ) : (
            <div className="bg-surface border border-border-subtle rounded-xl overflow-hidden">
              <div className="px-5 pt-4 pb-2 border-b border-border-subtle flex items-start justify-between gap-2">
                <div>
                  <p className="font-semibold text-foreground text-sm">
                    Thèmes les plus couverts dans les programmes
                  </p>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    Classification fixe · {stats.total_chunks} extraits analysés · {taxonomy.themes.length} thèmes
                  </p>
                </div>
              </div>
              <div className="px-5 py-4 space-y-1">
                {taxonomy.themes.map((theme, i) => (
                  <ThermometerBar
                    key={theme.theme}
                    rank={i + 1}
                    label={theme.theme}
                    count={theme.total_count}
                    percentage={theme.percentage}
                    isTop3={i < 3}
                  />
                ))}
              </div>
            </div>
          )}
        </section>

        {/* ---------------------------------------------------------------- */}
        {/* Legend                                                            */}
        {/* ---------------------------------------------------------------- */}
        {taxonomy.themes.length > 0 && commune.lists.length > 0 && (
          <div className="bg-surface border border-border-subtle rounded-xl px-5 py-3">
            <LegendBar lists={commune.lists} />
          </div>
        )}

        {/* ---------------------------------------------------------------- */}
        {/* Combined radar                                                    */}
        {/* ---------------------------------------------------------------- */}
        {taxonomy.themes.length > 0 && commune.lists.length > 0 && (
          <CombinedRadarSection themes={taxonomy.themes} lists={commune.lists} />
        )}

        {/* ---------------------------------------------------------------- */}
        {/* Radar grid                                                        */}
        {/* ---------------------------------------------------------------- */}
        {taxonomy.themes.length > 0 && commune.lists.length > 0 && (
          <section>
            <SectionLabel>
              📊 Alignement programme ↔ préoccupations
            </SectionLabel>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
              {commune.lists.map((list, i) => (
                <RadarCard
                  key={list.panel_number}
                  list={list}
                  listIndex={i}
                  themes={taxonomy.themes}
                />
              ))}
            </div>
          </section>
        )}
      </div>
    </div>
  );
}

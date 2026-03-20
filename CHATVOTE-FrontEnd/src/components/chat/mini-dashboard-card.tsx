"use client";

import { useEffect, useState } from "react";

import { toTitleCase } from "@lib/utils";
import {
  BarChart3,
  Layers,
  MessageCircle,
  Users,
} from "lucide-react";
import {
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
  ResponsiveContainer,
} from "recharts";

// ---------------------------------------------------------------------------
// Types (mirrors commune dashboard page)
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
  citizen: {
    total_messages: number;
    classified_messages: number;
    themes: Array<{ theme: string; count: number; percentage: number }>;
  };
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const LIST_COLORS = [
  "#7C3AED",
  "#6D28D9",
  "#A78BFA",
  "#C084FC",
  "#818CF8",
  "#67E8F9",
  "#94A3B8",
];

function listColor(i: number) {
  return LIST_COLORS[i % LIST_COLORS.length];
}

function _normalize(values: number[]): number[] {
  const max = Math.max(...values, 1);
  return values.map((v) => Math.round((v / max) * 100));
}

function buildCombinedMiniData(
  themes: TaxonomyTheme[],
  lists: ListInfo[],
): Array<Record<string, string | number>> {
  // Take top 6 themes for the mini radar
  const top = themes.slice(0, 6);
  return top.map((t) => {
    const entry: Record<string, string | number> = {
      theme: t.theme.length > 14 ? t.theme.slice(0, 12) + "…" : t.theme,
    };
    const values = lists.map((l) => t.by_list[l.list_label] ?? 0);
    const max = Math.max(...values, 1);
    lists.forEach((l) => {
      entry[toTitleCase(l.list_label)] = Math.round(
        ((t.by_list[l.list_label] ?? 0) / max) * 100,
      );
    });
    return entry;
  });
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

type Props = {
  communeCode: string;
  communeName: string;
};

// Feature-gated: hidden until NEXT_PUBLIC_ENABLE_COMMUNE_DASHBOARD=true
const COMMUNE_DASHBOARD_ENABLED =
  process.env.NEXT_PUBLIC_ENABLE_COMMUNE_DASHBOARD === "true";

export default function MiniDashboardCard({ communeCode, communeName }: Props) {
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [hasEnoughData, setHasEnoughData] = useState(false);

  useEffect(() => {
    if (!COMMUNE_DASHBOARD_ENABLED) return;

    setLoading(true);
    setHasEnoughData(false);
    setData(null);

    const abortController = new AbortController();
    // Abort after 8 seconds so the skeleton doesn't hang indefinitely
    const timeout = setTimeout(() => abortController.abort(), 8_000);

    fetch(`/api/commune/${communeCode}/dashboard`, {
      signal: abortController.signal,
    })
      .then((res) => {
        if (!res.ok) throw new Error(`${res.status}`);
        return res.json() as Promise<DashboardData>;
      })
      .then((d) => {
        setData(d);
        // Same check as commune page: need themes + lists
        const enough =
          d.taxonomy.themes.length > 0 && d.commune.lists.length > 0;
        setHasEnoughData(enough);
        setLoading(false);
      })
      .catch((err) => {
        // Ignore abort errors (component unmounted or timed out)
        if (err instanceof Error && err.name === "AbortError") return;
        setLoading(false);
        setHasEnoughData(false);
      });

    return () => {
      clearTimeout(timeout);
      abortController.abort();
    };
  }, [communeCode]);

  if (!COMMUNE_DASHBOARD_ENABLED) {
    return null;
  }

  // Loading skeleton
  if (loading) {
    return (
      <div className="border-border-subtle bg-surface w-full max-w-sm animate-pulse rounded-2xl border p-4">
        <div className="flex items-center gap-3">
          <div className="bg-border-subtle/60 h-10 w-10 rounded-xl" />
          <div className="flex-1 space-y-2">
            <div className="bg-border-subtle/60 h-3 w-24 rounded" />
            <div className="bg-border-subtle/40 h-2 w-16 rounded" />
          </div>
        </div>
      </div>
    );
  }

  // Not enough data → don't render anything
  if (!hasEnoughData || !data) {
    return null;
  }

  const { commune, stats, taxonomy } = data;
  const radarData = buildCombinedMiniData(taxonomy.themes, commune.lists);
  const topThemes = taxonomy.themes.slice(0, 3);

  return (
    <div className="w-full max-w-sm">
      <div className="border-border-subtle bg-surface relative overflow-hidden rounded-2xl border">
        {/* Top accent bar */}
        <div className="from-primary h-[3px] w-full bg-gradient-to-r via-violet-500 to-indigo-400" />

        <div className="p-4">
          {/* Header */}
          <div className="mb-3 flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <div className="bg-primary/10 flex size-9 items-center justify-center rounded-xl">
                <BarChart3 className="text-primary size-4" />
              </div>
              <div>
                <p className="text-foreground text-sm leading-tight font-semibold">
                  {communeName}
                </p>
                <p className="text-muted-foreground text-[11px]">
                  Tableau de bord
                </p>
              </div>
            </div>
          </div>

          {/* Stats row */}
          <div className="mb-3 flex gap-2">
            <div className="flex flex-1 items-center gap-1.5 rounded-lg bg-violet-500/10 px-2.5 py-1.5">
              <MessageCircle className="size-3 text-violet-400" />
              <span className="text-foreground text-xs font-bold">
                {stats.total_questions}
              </span>
              <span className="text-muted-foreground text-[10px]">
                questions
              </span>
            </div>
            <div className="flex flex-1 items-center gap-1.5 rounded-lg bg-indigo-500/10 px-2.5 py-1.5">
              <Users className="size-3 text-indigo-400" />
              <span className="text-foreground text-xs font-bold">
                {stats.total_lists}
              </span>
              <span className="text-muted-foreground text-[10px]">listes</span>
            </div>
            <div className="flex flex-1 items-center gap-1.5 rounded-lg bg-purple-500/10 px-2.5 py-1.5">
              <Layers className="size-3 text-purple-400" />
              <span className="text-foreground text-xs font-bold">
                {stats.themes_detected}
              </span>
              <span className="text-muted-foreground text-[10px]">thèmes</span>
            </div>
          </div>

          {/* Mini radar + top themes side by side */}
          <div className="flex items-center gap-3">
            {/* Mini radar chart */}
            <div className="size-28 shrink-0">
              <ResponsiveContainer width="100%" height="100%">
                <RadarChart
                  data={radarData}
                  margin={{ top: 8, right: 8, bottom: 8, left: 8 }}
                >
                  <PolarGrid stroke="var(--border-subtle)" strokeWidth={0.5} />
                  <PolarAngleAxis dataKey="theme" tick={false} />
                  <PolarRadiusAxis
                    angle={30}
                    domain={[0, 100]}
                    tick={false}
                    axisLine={false}
                  />
                  {commune.lists.slice(0, 3).map((list, i) => (
                    <Radar
                      key={list.panel_number}
                      dataKey={toTitleCase(list.list_label)}
                      stroke={listColor(i)}
                      fill={listColor(i)}
                      fillOpacity={0.08}
                      strokeWidth={1.5}
                    />
                  ))}
                </RadarChart>
              </ResponsiveContainer>
            </div>

            {/* Top themes */}
            <div className="flex flex-1 flex-col gap-1.5">
              <p className="text-muted-foreground mb-0.5 text-[10px] font-semibold tracking-wider uppercase">
                Thèmes principaux
              </p>
              {topThemes.map((theme, i) => {
                const maxPct = topThemes[0]?.percentage ?? 1;
                return (
                  <div key={theme.theme} className="flex items-center gap-2">
                    <span className="text-muted-foreground w-4 text-right text-[10px] font-bold">
                      {i + 1}.
                    </span>
                    <div className="flex-1">
                      <div className="mb-0.5 flex items-center justify-between">
                        <span className="text-foreground max-w-[120px] truncate text-[11px]">
                          {theme.theme}
                        </span>
                        <span className="text-muted-foreground ml-1 text-[10px] font-semibold">
                          {theme.percentage.toFixed(0)}%
                        </span>
                      </div>
                      <div className="bg-border-subtle/40 h-1 w-full overflow-hidden rounded-full">
                        <div
                          className="h-full rounded-full transition-all duration-500"
                          style={{
                            width: `${(theme.percentage / maxPct) * 100}%`,
                            background:
                              i === 0
                                ? "linear-gradient(90deg, #381AF3, #7C3AED)"
                                : i === 1
                                  ? "#A78BFA"
                                  : "#818CF8",
                          }}
                        />
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

        </div>
      </div>
    </div>
  );
}

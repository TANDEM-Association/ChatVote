"use client";

import { useState, useEffect, useCallback, useMemo } from "react";
import { Loader2, RefreshCw } from "lucide-react";
import { Button } from "@components/ui/button";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  PieChart,
  Pie,
  Cell,
  ScatterChart,
  Scatter,
  ResponsiveContainer,
  Legend,
} from "recharts";

import type { CoverageResponse, CommuneCoverage, CandidateCoverage } from "../../../../api/coverage/route";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface ChartsTabProps {
  secret: string;
  apiUrl: string;
}

// ---------------------------------------------------------------------------
// Score helpers (mirrors coverage-tables-client.tsx)
// ---------------------------------------------------------------------------

function computeCoverageScore(
  commune: CommuneCoverage,
  communeCandidates: CandidateCoverage[],
): number {
  let score = 0;
  if (commune.list_count > 0) score += 33;
  if (communeCandidates.length > 0) {
    const withWebsite = communeCandidates.filter((c) => c.has_website).length;
    score += 33 * (withWebsite / communeCandidates.length);
    const withManifesto = communeCandidates.filter((c) => c.has_manifesto).length;
    score += 34 * (withManifesto / communeCandidates.length);
  }
  return Math.round(score);
}

// ---------------------------------------------------------------------------
// Theme constants
// ---------------------------------------------------------------------------

const COLORS = {
  purple1: "#7C3AED",
  purple2: "#6D28D9",
  purple3: "#5B21B6",
  purple4: "#A78BFA",
  blue: "#818CF8",
  green: "#22c55e",
  red: "#ef4444",
  yellow: "#eab308",
  slate: "#94a3b8",
};

const TICK_FILL = "#94a3b8";
const GRID_STROKE = "#1e293b";

// ---------------------------------------------------------------------------
// Chart card wrapper
// ---------------------------------------------------------------------------

function ChartCard({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-xl border border-border-subtle bg-card p-4">
      <p className="mb-3 text-sm font-medium text-foreground">{title}</p>
      {children}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Custom tooltip
// ---------------------------------------------------------------------------

function DarkTooltip({
  active,
  payload,
  label,
  formatter,
}: {
  active?: boolean;
  payload?: Array<{ name: string; value: number; color?: string }>;
  label?: string;
  formatter?: (value: number, name: string) => string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-border-subtle bg-card px-3 py-2 shadow-lg text-xs">
      {label && <p className="mb-1 font-medium text-foreground">{label}</p>}
      {payload.map((p) => (
        <p key={p.name} style={{ color: p.color ?? TICK_FILL }}>
          {p.name}: <span className="font-semibold tabular-nums">{formatter ? formatter(p.value, p.name) : p.value}</span>
        </p>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Chart 1: Coverage Funnel
// ---------------------------------------------------------------------------

function CoverageFunnelChart({ candidates }: { candidates: CandidateCoverage[] }) {
  const total = candidates.length;
  const hasWebsite = candidates.filter((c) => c.has_website).length;
  const scraped = candidates.filter((c) => c.has_scraped).length;
  const indexed = candidates.filter((c) => c.chunk_count > 0).length;

  const data = [
    { label: "Total", value: total, fill: COLORS.purple1 },
    { label: "Has Website", value: hasWebsite, fill: COLORS.purple2 },
    { label: "Scraped", value: scraped, fill: COLORS.purple4 },
    { label: "Indexed", value: indexed, fill: COLORS.blue },
  ];

  return (
    <ChartCard title="Coverage Funnel">
      <ResponsiveContainer width="100%" height={280}>
        <BarChart data={data} layout="vertical" margin={{ left: 8, right: 16, top: 4, bottom: 4 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} horizontal={false} />
          <XAxis type="number" tick={{ fill: TICK_FILL, fontSize: 11 }} tickLine={false} axisLine={false} />
          <YAxis type="category" dataKey="label" tick={{ fill: TICK_FILL, fontSize: 11 }} tickLine={false} axisLine={false} width={80} />
          <Tooltip content={<DarkTooltip formatter={(v) => v.toLocaleString()} />} />
          <Bar dataKey="value" radius={[0, 4, 4, 0]} name="Candidates">
            {data.map((entry) => (
              <Cell key={entry.label} fill={entry.fill} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}

// ---------------------------------------------------------------------------
// Chart 2: Candidate Status Donut
// ---------------------------------------------------------------------------

function CandidateStatusChart({ candidates }: { candidates: CandidateCoverage[] }) {
  const noWebsite = candidates.filter((c) => !c.has_website).length;
  const hasWebsiteNotIndexed = candidates.filter((c) => c.has_website && c.chunk_count === 0).length;
  const indexed = candidates.filter((c) => c.chunk_count > 0).length;

  const data = [
    { name: "No Website", value: noWebsite, fill: COLORS.red },
    { name: "Has Website (not indexed)", value: hasWebsiteNotIndexed, fill: COLORS.yellow },
    { name: "Indexed in RAG", value: indexed, fill: COLORS.green },
  ].filter((d) => d.value > 0);

  const total = candidates.length;

  return (
    <ChartCard title="Candidate Status">
      <ResponsiveContainer width="100%" height={280}>
        <PieChart>
          <Pie
            data={data}
            cx="50%"
            cy="45%"
            innerRadius={60}
            outerRadius={95}
            paddingAngle={2}
            dataKey="value"
          >
            {data.map((entry) => (
              <Cell key={entry.name} fill={entry.fill} />
            ))}
          </Pie>
          <Tooltip
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null;
              const p = payload[0];
              const pct = total > 0 ? Math.round(((p.value as number) / total) * 100) : 0;
              return (
                <div className="rounded-lg border border-border-subtle bg-card px-3 py-2 shadow-lg text-xs">
                  <p className="font-medium text-foreground">{p.name}</p>
                  <p style={{ color: p.payload?.fill ?? TICK_FILL }}>
                    {(p.value as number).toLocaleString()} ({pct}%)
                  </p>
                </div>
              );
            }}
          />
          <Legend
            formatter={(value) => <span style={{ color: TICK_FILL, fontSize: 11 }}>{value}</span>}
            wrapperStyle={{ paddingTop: 8 }}
          />
        </PieChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}

// ---------------------------------------------------------------------------
// Chart 3 & 4: Top/Bottom 15 Communes by Coverage Score
// ---------------------------------------------------------------------------

function CommuneRankChart({
  title,
  communes,
  candidates,
  mode,
}: {
  title: string;
  communes: CommuneCoverage[];
  candidates: CandidateCoverage[];
  mode: "top" | "bottom";
}) {
  const candidatesByCommune = useMemo(() => {
    const map: Record<string, CandidateCoverage[]> = {};
    for (const c of candidates) {
      if (c.commune_code) {
        (map[c.commune_code] ??= []).push(c);
      }
    }
    return map;
  }, [candidates]);

  const scored = useMemo(() => {
    return communes
      .filter((c) => c.candidate_count > 0)
      .map((c) => ({
        name: c.name.length > 18 ? c.name.slice(0, 16) + "…" : c.name,
        score: computeCoverageScore(c, candidatesByCommune[c.code] ?? []),
      }))
      .sort((a, b) => (mode === "top" ? b.score - a.score : a.score - b.score))
      .slice(0, 15);
  }, [communes, candidatesByCommune, mode]);

  const fill = mode === "top" ? COLORS.green : COLORS.red;

  return (
    <ChartCard title={title}>
      <ResponsiveContainer width="100%" height={280}>
        <BarChart data={scored} layout="vertical" margin={{ left: 8, right: 16, top: 4, bottom: 4 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} horizontal={false} />
          <XAxis type="number" domain={[0, 100]} tick={{ fill: TICK_FILL, fontSize: 11 }} tickLine={false} axisLine={false} unit="%" />
          <YAxis type="category" dataKey="name" tick={{ fill: TICK_FILL, fontSize: 10 }} tickLine={false} axisLine={false} width={100} />
          <Tooltip content={<DarkTooltip formatter={(v) => `${v}%`} />} />
          <Bar dataKey="score" fill={fill} radius={[0, 4, 4, 0]} name="Score" />
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}

// ---------------------------------------------------------------------------
// Chart 5: Coverage by Department
// ---------------------------------------------------------------------------

function getDeptCode(communeCode: string): string {
  if (!communeCode) return "??";
  // Overseas (971–976 DOM-TOM) use 3-char prefix
  if (/^97[0-9]/.test(communeCode)) return communeCode.slice(0, 3);
  return communeCode.slice(0, 2);
}

function CoverageByDeptChart({
  communes,
  candidates,
}: {
  communes: CommuneCoverage[];
  candidates: CandidateCoverage[];
}) {
  const candidatesByCommune = useMemo(() => {
    const map: Record<string, CandidateCoverage[]> = {};
    for (const c of candidates) {
      if (c.commune_code) {
        (map[c.commune_code] ??= []).push(c);
      }
    }
    return map;
  }, [candidates]);

  const data = useMemo(() => {
    const deptScores: Record<string, number[]> = {};
    for (const c of communes) {
      const dept = getDeptCode(c.code);
      const score = computeCoverageScore(c, candidatesByCommune[c.code] ?? []);
      (deptScores[dept] ??= []).push(score);
    }
    return Object.entries(deptScores)
      .map(([dept, scores]) => ({
        dept,
        avg: Math.round(scores.reduce((s, v) => s + v, 0) / scores.length),
      }))
      .sort((a, b) => b.avg - a.avg);
  }, [communes, candidatesByCommune]);

  return (
    <ChartCard title="Coverage by Department (avg score)">
      <ResponsiveContainer width="100%" height={280}>
        <BarChart data={data} margin={{ left: 4, right: 16, top: 4, bottom: 4 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} vertical={false} />
          <XAxis dataKey="dept" tick={{ fill: TICK_FILL, fontSize: 10 }} tickLine={false} axisLine={false} />
          <YAxis domain={[0, 100]} tick={{ fill: TICK_FILL, fontSize: 11 }} tickLine={false} axisLine={false} unit="%" />
          <Tooltip content={<DarkTooltip formatter={(v) => `${v}%`} />} />
          <Bar dataKey="avg" fill={COLORS.blue} radius={[4, 4, 0, 0]} name="Avg Score" />
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}

// ---------------------------------------------------------------------------
// Chart 6: Party Label Distribution
// ---------------------------------------------------------------------------

function PartyLabelDistributionChart({ candidates }: { candidates: CandidateCoverage[] }) {
  const data = useMemo(() => {
    const counts: Record<string, { total: number; withWebsite: number }> = {};
    for (const c of candidates) {
      const label = c.party_label || "Unknown";
      if (!counts[label]) counts[label] = { total: 0, withWebsite: 0 };
      counts[label].total++;
      if (c.has_website) counts[label].withWebsite++;
    }
    return Object.entries(counts)
      .map(([label, v]) => ({
        label: label.length > 12 ? label.slice(0, 10) + "…" : label,
        total: v.total,
        withWebsite: v.withWebsite,
      }))
      .sort((a, b) => b.total - a.total)
      .slice(0, 20);
  }, [candidates]);

  return (
    <ChartCard title="Candidates by Political Label">
      <ResponsiveContainer width="100%" height={280}>
        <BarChart data={data} margin={{ left: 4, right: 16, top: 4, bottom: 24 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} vertical={false} />
          <XAxis dataKey="label" tick={{ fill: TICK_FILL, fontSize: 9 }} tickLine={false} axisLine={false} angle={-35} textAnchor="end" interval={0} />
          <YAxis tick={{ fill: TICK_FILL, fontSize: 11 }} tickLine={false} axisLine={false} />
          <Tooltip content={<DarkTooltip />} />
          <Legend formatter={(value) => <span style={{ color: TICK_FILL, fontSize: 11 }}>{value}</span>} />
          <Bar dataKey="total" fill={COLORS.purple1} radius={[4, 4, 0, 0]} name="Total" />
          <Bar dataKey="withWebsite" fill={COLORS.green} radius={[4, 4, 0, 0]} name="With Website" />
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}

// ---------------------------------------------------------------------------
// Chart 7: Population vs Coverage Scatter
// ---------------------------------------------------------------------------

function PopulationVsCoverageChart({
  communes,
  candidates,
}: {
  communes: CommuneCoverage[];
  candidates: CandidateCoverage[];
}) {
  const candidatesByCommune = useMemo(() => {
    const map: Record<string, CandidateCoverage[]> = {};
    for (const c of candidates) {
      if (c.commune_code) {
        (map[c.commune_code] ??= []).push(c);
      }
    }
    return map;
  }, [candidates]);

  const data = useMemo(() => {
    return communes
      .filter((c) => c.population > 0 && c.candidate_count > 0)
      .map((c) => ({
        population: c.population,
        score: computeCoverageScore(c, candidatesByCommune[c.code] ?? []),
        name: c.name,
      }));
  }, [communes, candidatesByCommune]);

  return (
    <ChartCard title="Population vs Coverage Score">
      <ResponsiveContainer width="100%" height={280}>
        <ScatterChart margin={{ left: 4, right: 16, top: 4, bottom: 4 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} />
          <XAxis
            dataKey="population"
            name="Population"
            type="number"
            tick={{ fill: TICK_FILL, fontSize: 10 }}
            tickLine={false}
            axisLine={false}
            tickFormatter={(v: number) => v >= 1000 ? `${Math.round(v / 1000)}k` : String(v)}
          />
          <YAxis
            dataKey="score"
            name="Score"
            type="number"
            domain={[0, 100]}
            tick={{ fill: TICK_FILL, fontSize: 11 }}
            tickLine={false}
            axisLine={false}
            unit="%"
          />
          <Tooltip
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null;
              const d = payload[0]?.payload as { name: string; population: number; score: number } | undefined;
              if (!d) return null;
              return (
                <div className="rounded-lg border border-border-subtle bg-card px-3 py-2 shadow-lg text-xs">
                  <p className="font-medium text-foreground">{d.name}</p>
                  <p style={{ color: TICK_FILL }}>Population: <span className="font-semibold">{d.population.toLocaleString("fr-FR")}</span></p>
                  <p style={{ color: COLORS.purple4 }}>Score: <span className="font-semibold">{d.score}%</span></p>
                </div>
              );
            }}
          />
          <Scatter data={data} fill={COLORS.purple4} fillOpacity={0.7} />
        </ScatterChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}

// ---------------------------------------------------------------------------
// Chart 8: Chunk Count Distribution Histogram
// ---------------------------------------------------------------------------

function ChunkDistributionChart({ candidates }: { candidates: CandidateCoverage[] }) {
  const data = useMemo(() => {
    const buckets = [
      { label: "0", min: 0, max: 0 },
      { label: "1–10", min: 1, max: 10 },
      { label: "11–25", min: 11, max: 25 },
      { label: "26–50", min: 26, max: 50 },
      { label: "51–100", min: 51, max: 100 },
      { label: "100+", min: 101, max: Infinity },
    ];
    return buckets.map((b) => ({
      label: b.label,
      count: candidates.filter((c) => c.chunk_count >= b.min && c.chunk_count <= b.max).length,
    }));
  }, [candidates]);

  return (
    <ChartCard title="Chunk Count Distribution (indexed candidates)">
      <ResponsiveContainer width="100%" height={280}>
        <BarChart data={data} margin={{ left: 4, right: 16, top: 4, bottom: 4 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} vertical={false} />
          <XAxis dataKey="label" tick={{ fill: TICK_FILL, fontSize: 11 }} tickLine={false} axisLine={false} />
          <YAxis tick={{ fill: TICK_FILL, fontSize: 11 }} tickLine={false} axisLine={false} />
          <Tooltip content={<DarkTooltip formatter={(v) => v.toLocaleString()} />} />
          <Bar dataKey="count" fill={COLORS.purple2} radius={[4, 4, 0, 0]} name="Candidates" />
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}

// ---------------------------------------------------------------------------
// Main Charts Tab
// ---------------------------------------------------------------------------

export default function ChartsTab({ secret, apiUrl }: ChartsTabProps) {
  const [data, setData] = useState<CoverageResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/coverage`, { cache: "no-store" });
      if (!res.ok) throw new Error(`Status ${res.status}`);
      const json: CoverageResponse = await res.json();
      setData(json);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to fetch coverage data");
    } finally {
      setLoading(false);
    }
  }, [secret, apiUrl]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="size-5 animate-spin text-muted-foreground" />
        <span className="ml-2 text-sm text-muted-foreground">Loading chart data...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-6 text-center">
        <p className="text-sm text-red-400">{error}</p>
        <Button size="sm" variant="outline" onClick={fetchData} className="mt-3">
          Retry
        </Button>
      </div>
    );
  }

  if (!data) return null;

  const { communes, candidates } = data;

  return (
    <div className="space-y-4">
      {/* Header row */}
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          {communes.length} communes · {candidates.length} candidates
        </p>
        <Button size="sm" variant="ghost" onClick={fetchData} className="h-8 gap-1.5 text-xs">
          <RefreshCw className="size-3.5" />
          Refresh
        </Button>
      </div>

      {/* 2-column grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <CoverageFunnelChart candidates={candidates} />
        <CandidateStatusChart candidates={candidates} />
        <CommuneRankChart
          title="Top 15 Communes by Coverage Score"
          communes={communes}
          candidates={candidates}
          mode="top"
        />
        <CommuneRankChart
          title="Bottom 15 Communes by Coverage Score"
          communes={communes}
          candidates={candidates}
          mode="bottom"
        />
        <CoverageByDeptChart communes={communes} candidates={candidates} />
        <PartyLabelDistributionChart candidates={candidates} />
        <PopulationVsCoverageChart communes={communes} candidates={candidates} />
        <ChunkDistributionChart candidates={candidates} />
      </div>
    </div>
  );
}

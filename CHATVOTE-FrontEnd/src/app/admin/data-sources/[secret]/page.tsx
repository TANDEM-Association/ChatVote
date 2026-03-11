"use client";

import { useParams } from "next/navigation";
import React, { useState, useEffect, useCallback, useRef } from "react";

import {
  Play,
  RotateCcw,
  Trash2,
  ChevronDown,
  ChevronRight,
  Settings,
  Loader2,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Circle,
  Square,
  Eye,
  X,
} from "lucide-react";

import { Button } from "@components/ui/button";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface NodeConfig {
  node_id: string;
  label: string;
  enabled: boolean;
  status: "idle" | "running" | "success" | "error";
  last_run_at: string | null;
  last_duration_s: number | null;
  last_error: string | null;
  counts: Record<string, number | string>;
  settings: Record<string, any>;
  checkpoints: Record<string, any>;
}

type NodesMap = Record<string, NodeConfig>;

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const API_URL =
  process.env.NEXT_PUBLIC_API_URL ||
  process.env.NEXT_PUBLIC_SOCKET_URL ||
  "http://localhost:8080";

const POLL_INTERVAL_MS = 5000;

/** Human-readable descriptions for each pipeline node */
const NODE_DESCRIPTIONS: Record<string, string> = {
  population:
    "Fetches top communes by population from geo.api.gouv.fr. Provides the commune list (INSEE codes) used by all downstream nodes.",
  candidatures:
    "Downloads the official candidatures CSV from data.gouv.fr (887K+ rows). Parses candidate lists per commune with party affiliations and nuance codes.",
  websites:
    "Loads candidate campaign website URLs from a Google Sheet via the Sheets API. Matches URLs to seeded candidates by commune + name.",
  pourquituvotes:
    "Scrapes pourquituvotes.fr JSON API (134 communes) to extract programmeUrl campaign links per candidate. Merges into the websites cache.",
  professions:
    "Downloads professions de foi PDFs from programme-candidats.interieur.gouv.fr using URL pattern data-pdf/{tour}-{commune}-{panneau}.pdf. Uses candidatures data for panneau numbers.",
  seed:
    "Writes candidate and party data to Firestore. Combines population, candidatures, and websites data into the final documents.",
  scraper:
    "Built-in candidate website scraper (BFS, max 15 pages + 5 PDFs per site). When Crawl Service Scraper is enabled, candidate sites are handled there instead. Backend: playwright, playwright-fast, or firecrawl.",
  crawl_scraper:
    "External crawl K8s service for candidate websites. When enabled, takes over candidate site scraping from the built-in scraper. Submits to Google Sheet, polls until PROCESSED, downloads from Drive. Already-processed sites skip straight to download.",
  indexer:
    "Embeds scraped content into Qdrant vector DB for RAG retrieval. Indexes party manifestos (PDFs) and candidate websites (from scraper node) using LLM embeddings.",
};

/** DAG layout: rows of node_ids with their grid column positions */
const DAG_ROWS: { id: string; col: number; row: number }[] = [
  { id: "population", col: 0, row: 0 },
  { id: "candidatures", col: 1, row: 0 },
  { id: "websites", col: 2, row: 0 },
  { id: "pourquituvotes", col: 3, row: 0 },
  { id: "seed", col: 1, row: 1 },
  { id: "professions", col: 2, row: 1 },
  { id: "scraper", col: 1, row: 2 },
  { id: "crawl_scraper", col: 2, row: 2 },
  { id: "indexer", col: 1, row: 3 },
];

/** Edges in the DAG: [from, to] */
const DAG_EDGES: [string, string][] = [
  ["population", "seed"],
  ["candidatures", "seed"],
  ["websites", "seed"],
  ["pourquituvotes", "seed"],
  ["professions", "seed"],
  ["seed", "scraper"],
  ["seed", "crawl_scraper"],
  ["scraper", "indexer"],
  ["crawl_scraper", "indexer"],
];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function statusIcon(status: NodeConfig["status"]) {
  switch (status) {
    case "success":
      return <CheckCircle2 className="size-4 text-emerald-500" />;
    case "running":
      return <Loader2 className="size-4 animate-spin text-amber-400" />;
    case "error":
      return <XCircle className="size-4 text-red-500" />;
    default:
      return <Circle className="size-4 text-zinc-400" />;
  }
}

function statusDot(status: NodeConfig["status"]) {
  const base = "size-2.5 rounded-full shrink-0";
  switch (status) {
    case "success":
      return <span className={`${base} bg-emerald-500`} />;
    case "running":
      return <span className={`${base} animate-pulse bg-amber-400`} />;
    case "error":
      return <span className={`${base} bg-red-500`} />;
    default:
      return <span className={`${base} bg-zinc-400`} />;
  }
}

function formatTimestamp(ts: string | null): string {
  if (!ts) return "Never";
  const d = new Date(ts);
  return d.toLocaleString("fr-FR", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function formatDuration(s: number | null): string {
  if (s === null) return "--";
  if (s < 60) return `${s.toFixed(1)}s`;
  const m = Math.floor(s / 60);
  const rem = s % 60;
  return `${m}m ${rem.toFixed(0)}s`;
}

// ---------------------------------------------------------------------------
// Toggle switch (no dependency)
// ---------------------------------------------------------------------------

function Toggle({
  checked,
  onChange,
  disabled,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer items-center rounded-full transition-colors duration-200 focus-visible:ring-2 focus-visible:ring-zinc-400 focus-visible:ring-offset-2 focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-50 ${
        checked ? "bg-emerald-500" : "bg-zinc-600"
      }`}
    >
      <span
        className={`pointer-events-none block size-3.5 rounded-full bg-white shadow-sm ring-0 transition-transform duration-200 ${
          checked ? "translate-x-[18px]" : "translate-x-[3px]"
        }`}
      />
    </button>
  );
}

// ---------------------------------------------------------------------------
// Node Card
// ---------------------------------------------------------------------------

/** Known dropdown options for specific settings */
const SETTING_OPTIONS: Record<string, string[]> = {
  scraper_backend: ["playwright", "playwright-fast", "firecrawl"],
};

function NodeCard({
  node,
  onRun,
  onForceRun,
  onStop,
  onToggleEnabled,
  onUpdateSettings,
  onPreview,
}: {
  node: NodeConfig;
  onRun: () => void;
  onForceRun: () => void;
  onStop: () => void;
  onToggleEnabled: (enabled: boolean) => void;
  onUpdateSettings: (settings: Record<string, any>) => void;
  onPreview: () => void;
}) {
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [errorOpen, setErrorOpen] = useState(false);
  const [localSettings, setLocalSettings] = useState<Record<string, any>>(
    node.settings,
  );
  const [settingsDirty, setSettingsDirty] = useState(false);

  useEffect(() => {
    setLocalSettings(node.settings);
    setSettingsDirty(false);
  }, [node.settings]);

  const settingsKeys = Object.keys(node.settings);
  const countsEntries = Object.entries(node.counts);
  const isRunning = node.status === "running";

  function handleSettingChange(key: string, value: string) {
    const updated = { ...localSettings, [key]: value };
    setLocalSettings(updated);
    setSettingsDirty(true);
  }

  function handleSaveSettings() {
    onUpdateSettings(localSettings);
    setSettingsDirty(false);
  }

  return (
    <div
      className={`relative flex w-full flex-col rounded-lg border bg-white shadow-sm transition-shadow hover:shadow-md ${
        isRunning
          ? "border-amber-300"
          : node.status === "error"
            ? "border-red-300"
            : node.status === "success"
              ? "border-emerald-200"
              : "border-zinc-200"
      }`}
    >
      {/* Header */}
      <div className="flex items-center gap-2 border-b border-zinc-100 px-4 py-3">
        {statusDot(node.status)}
        <h3 className="flex-1 text-sm font-semibold text-zinc-800 tracking-tight">
          {node.label}
        </h3>
        <Toggle
          checked={node.enabled}
          onChange={onToggleEnabled}
          disabled={isRunning}
        />
      </div>

      {/* Description */}
      {NODE_DESCRIPTIONS[node.node_id] && (
        <p className="px-4 pt-2 text-[11px] leading-relaxed text-zinc-400">
          {NODE_DESCRIPTIONS[node.node_id]}
        </p>
      )}

      {/* Body */}
      <div className="flex flex-col gap-3 px-4 py-3">
        {/* Timestamp + duration */}
        <div className="flex items-center justify-between text-xs text-zinc-500">
          <span>{formatTimestamp(node.last_run_at)}</span>
          <span className="font-mono">
            {formatDuration(node.last_duration_s)}
          </span>
        </div>

        {/* Live progress (visible when running with any counts) */}
        {isRunning && Object.keys(node.counts).length > 0 && (() => {
          const c = node.counts;

          // Auto-detect total/done keys for progress bar
          // Prefer exact matches first, then suffixed variants
          const totalKey = Object.keys(c).find(k => k === "total")
            ?? Object.keys(c).find(k => k.endsWith("_total"));
          const total = totalKey ? Number(c[totalKey]) || 0 : 0;
          const doneKey = Object.keys(c).find(k => k === "scraped" || k === "done")
            ?? Object.keys(c).find(k => k.endsWith("_done"));
          const done = doneKey ? Number(c[doneKey]) || 0 : 0;
          const pct = total > 0 ? Math.round((done / total) * 100) : 0;

          const elapsed = Number(c.elapsed_s ?? 0);
          const eta = Number(c.eta_s ?? 0);
          const rate = c.rate_per_sec ?? c.rate_communes_per_sec ?? null;
          const phase = c.phase as string | undefined;
          const current = c.current as string | undefined;
          const currentUrls = c.current_urls as string | undefined;
          const lastResults = (c.last_results ?? []) as Array<{
            name?: string; pages?: number; chars?: number; ok?: boolean; error?: string;
          }>;

          const fmtTime = (s: number) => {
            if (s < 60) return `${Math.round(s)}s`;
            const m = Math.floor(s / 60);
            const sec = Math.round(s % 60);
            return `${m}m${sec > 0 ? ` ${sec}s` : ""}`;
          };

          const fmtChars = (n: number) => {
            if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
            if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K`;
            return String(n);
          };

          // Extra numeric stats (exclude meta/display keys)
          const metaKeys = new Set([
            totalKey, doneKey, "elapsed_s", "eta_s", "rate_per_sec",
            "rate_communes_per_sec", "phase", "current", "current_urls", "last_results",
          ]);
          const extraStats = Object.entries(c).filter(
            ([k, v]) => !metaKeys.has(k) && typeof v !== "object"
          );

          return (
            <div className="flex flex-col gap-2">
              {/* Phase indicator */}
              {phase && (
                <span className="text-[11px] font-medium text-amber-600">
                  Phase: {phase}
                </span>
              )}

              {/* Currently scraping */}
              {current && (
                <div className="rounded-md bg-amber-50 px-2.5 py-1.5">
                  <span className="text-[10px] font-medium text-amber-700">
                    Scraping:
                  </span>
                  <span className="ml-1 text-[11px] font-semibold text-amber-900">
                    {current}
                  </span>
                  {currentUrls && (
                    <p className="mt-0.5 truncate text-[10px] text-amber-600">
                      {currentUrls}
                    </p>
                  )}
                </div>
              )}

              {/* Progress bar */}
              {total > 0 && (
                <div className="flex items-center gap-2">
                  <div className="h-2.5 flex-1 overflow-hidden rounded-full bg-zinc-200">
                    <div
                      className="h-full rounded-full bg-amber-400 transition-all duration-700 ease-out"
                      style={{ width: `${Math.min(100, pct)}%` }}
                    />
                  </div>
                  <span className="min-w-[3ch] text-right text-xs font-bold text-zinc-700">
                    {pct}%
                  </span>
                </div>
              )}

              {/* Stats grid */}
              <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 text-[11px]">
                {total > 0 && (
                  <>
                    <span className="text-zinc-400">Progress</span>
                    <span className="text-right font-mono font-medium text-zinc-700">
                      {done} / {total}
                    </span>
                  </>
                )}

                {extraStats.map(([key, val]) => (
                  <React.Fragment key={key}>
                    <span className="text-zinc-400">{key.replace(/_/g, " ")}</span>
                    <span className="text-right font-mono font-medium text-zinc-700">
                      {key === "total_chars" ? fmtChars(Number(val)) : String(val)}
                    </span>
                  </React.Fragment>
                ))}

                {rate !== null && (
                  <>
                    <span className="text-zinc-400">Speed</span>
                    <span className="text-right font-mono font-medium text-zinc-700">
                      {rate}/s
                    </span>
                  </>
                )}

                {elapsed > 0 && (
                  <>
                    <span className="text-zinc-400">Elapsed</span>
                    <span className="text-right font-mono font-medium text-zinc-700">
                      {fmtTime(elapsed)}
                    </span>
                  </>
                )}

                {eta > 0 && (
                  <>
                    <span className="text-zinc-400">ETA</span>
                    <span className="text-right font-mono font-medium text-amber-600">
                      ~{fmtTime(eta)}
                    </span>
                  </>
                )}
              </div>

              {/* Last results feed */}
              {lastResults.length > 0 && (
                <div className="flex flex-col gap-1 border-t border-zinc-100 pt-2">
                  <span className="text-[10px] font-medium text-zinc-400">Recent</span>
                  {lastResults.map((r, i) => (
                    <div key={i} className="flex items-center gap-1.5 text-[10px]">
                      {r.ok ? (
                        <CheckCircle2 className="size-3 shrink-0 text-emerald-500" />
                      ) : (
                        <XCircle className="size-3 shrink-0 text-red-400" />
                      )}
                      <span className="truncate font-medium text-zinc-700">
                        {r.name}
                      </span>
                      {r.ok ? (
                        <span className="ml-auto shrink-0 font-mono text-zinc-500">
                          {r.pages}p · {fmtChars(r.chars ?? 0)}
                        </span>
                      ) : (
                        <span className="ml-auto shrink-0 truncate text-red-500">
                          {r.error}
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })()}

        {/* Counts */}
        {countsEntries.length > 0 && !isRunning && (
          <div className="flex flex-wrap gap-1.5">
            {countsEntries.map(([key, val]) => (
              <span
                key={key}
                className="inline-flex items-center rounded-full bg-zinc-100 px-2 py-0.5 text-[11px] font-medium text-zinc-600"
              >
                {key.replace(/_/g, " ")}:&nbsp;
                <span className="font-semibold text-zinc-800">{String(val)}</span>
              </span>
            ))}
          </div>
        )}

        {/* Error */}
        {node.status === "error" && node.last_error && (
          <div className="rounded-md bg-red-50 p-2">
            <button
              type="button"
              onClick={() => setErrorOpen(!errorOpen)}
              className="flex w-full items-center gap-1 text-left text-xs font-medium text-red-700"
            >
              <AlertTriangle className="size-3.5 shrink-0" />
              <span className="flex-1 truncate">
                {node.last_error.split("\n")[0]}
              </span>
              {errorOpen ? (
                <ChevronDown className="size-3.5 shrink-0" />
              ) : (
                <ChevronRight className="size-3.5 shrink-0" />
              )}
            </button>
            {errorOpen && (
              <pre className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap text-[11px] leading-relaxed text-red-600">
                {node.last_error}
              </pre>
            )}
          </div>
        )}

        {/* Actions */}
        <div className="flex items-center gap-2">
          {isRunning ? (
            <Button
              size="sm"
              variant="outline"
              onClick={onStop}
              className="h-7 gap-1.5 px-2.5 text-xs border-red-300 text-red-600 hover:bg-red-50"
            >
              <Square className="size-3" />
              Stop
            </Button>
          ) : (
            <>
              <Button
                size="sm"
                variant="outline"
                onClick={onRun}
                disabled={!node.enabled}
                className="h-7 gap-1.5 px-2.5 text-xs"
              >
                <Play className="size-3" />
                Run
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={onForceRun}
                className="h-7 gap-1.5 px-2.5 text-xs"
              >
                <RotateCcw className="size-3" />
                Force
              </Button>
            </>
          )}
          <div className="ml-auto flex items-center gap-1">
            <Button
              size="sm"
              variant="ghost"
              onClick={onPreview}
              className="h-7 gap-1 px-2 text-xs text-zinc-500"
              title="Preview data"
            >
              <Eye className="size-3" />
            </Button>
            {settingsKeys.length > 0 && (
              <Button
                size="sm"
                variant="ghost"
                onClick={() => setSettingsOpen(!settingsOpen)}
                className="h-7 gap-1 px-2 text-xs text-zinc-500"
              >
                <Settings className="size-3" />
                {settingsOpen ? (
                  <ChevronDown className="size-3" />
                ) : (
                  <ChevronRight className="size-3" />
                )}
              </Button>
            )}
          </div>
        </div>

        {/* Settings panel */}
        {settingsOpen && settingsKeys.length > 0 && (
          <div className="flex flex-col gap-2 rounded-md bg-zinc-50 p-3">
            {settingsKeys.map((key) => (
              <label key={key} className="flex flex-col gap-1">
                <span className="text-[11px] font-medium text-zinc-500">
                  {key.replace(/_/g, " ")}
                </span>
                {SETTING_OPTIONS[key] ? (
                  <select
                    value={String(localSettings[key] ?? "")}
                    onChange={(e) => handleSettingChange(key, e.target.value)}
                    className="rounded-md border border-zinc-200 bg-white px-2 py-1.5 text-xs text-zinc-800 outline-none focus:border-zinc-400 focus:ring-1 focus:ring-zinc-300"
                  >
                    {SETTING_OPTIONS[key].map((opt) => (
                      <option key={opt} value={opt}>
                        {opt}
                      </option>
                    ))}
                  </select>
                ) : typeof localSettings[key] === "boolean" ? (
                  <select
                    value={String(localSettings[key])}
                    onChange={(e) => handleSettingChange(key, e.target.value)}
                    className="rounded-md border border-zinc-200 bg-white px-2 py-1.5 text-xs text-zinc-800 outline-none focus:border-zinc-400 focus:ring-1 focus:ring-zinc-300"
                  >
                    <option value="true">true</option>
                    <option value="false">false</option>
                  </select>
                ) : (
                  <input
                    type="text"
                    value={String(localSettings[key] ?? "")}
                    onChange={(e) => handleSettingChange(key, e.target.value)}
                    className="rounded-md border border-zinc-200 bg-white px-2 py-1 text-xs text-zinc-800 outline-none focus:border-zinc-400 focus:ring-1 focus:ring-zinc-300"
                  />
                )}
              </label>
            ))}
            {settingsDirty && (
              <Button
                size="sm"
                onClick={handleSaveSettings}
                className="mt-1 h-7 self-end text-xs"
              >
                Save
              </Button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// SVG DAG Arrows
// ---------------------------------------------------------------------------

interface ArrowsProps {
  nodes: NodesMap;
}

/**
 * Draws SVG arrows between DAG nodes.
 * Uses an overlay SVG that sits behind the cards.
 * We compute positions from the known grid layout.
 */
function DagArrows({ nodes }: ArrowsProps) {
  const [positions, setPositions] = useState<
    Record<string, { cx: number; cy: number }>
  >({});

  const containerRef = useRef<HTMLDivElement | null>(null);

  const recalc = useCallback(() => {
    if (!containerRef.current) return;
    const container = containerRef.current;
    const rect = container.getBoundingClientRect();
    const pos: Record<string, { cx: number; cy: number }> = {};

    for (const item of DAG_ROWS) {
      const el = container.querySelector(`[data-node-id="${item.id}"]`);
      if (!el) continue;
      const elRect = el.getBoundingClientRect();
      pos[item.id] = {
        cx: elRect.left - rect.left + elRect.width / 2,
        cy: elRect.top - rect.top + elRect.height / 2,
      };
    }
    setPositions(pos);
  }, []);

  useEffect(() => {
    recalc();
    window.addEventListener("resize", recalc);
    return () => window.removeEventListener("resize", recalc);
  }, [recalc, nodes]);

  // Re-measure after a tick to pick up layout changes
  useEffect(() => {
    const timer = setTimeout(recalc, 100);
    return () => clearTimeout(timer);
  }, [recalc]);

  return { containerRef, positions };
}

// ---------------------------------------------------------------------------
// Page component
// ---------------------------------------------------------------------------

export default function DataSourcesPage() {
  const params = useParams<{ secret: string }>();
  const secret = params.secret;

  const [nodes, setNodes] = useState<NodesMap>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [bustCacheConfirm, setBustCacheConfirm] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [arrowPositions, setArrowPositions] = useState<
    Record<string, { cx: number; cy: number; bottom: number; top: number }>
  >({});
  const [previewNode, setPreviewNode] = useState<string | null>(null);
  const [previewData, setPreviewData] = useState<any>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [topCommunes, setTopCommunes] = useState<number>(1);

  // ---- API helpers ----

  const headers = useCallback(
    () => ({
      "Content-Type": "application/json",
      "X-Admin-Secret": secret,
    }),
    [secret],
  );

  const fetchStatus = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/api/v1/admin/data-sources/status`, {
        headers: headers(),
        cache: "no-store",
      });
      if (!res.ok) throw new Error(`Status ${res.status}`);
      const data: NodesMap = await res.json();
      // Console log for real-time pipeline monitoring
      const running = Object.values(data).filter((n) => n.status === "running");
      const done = Object.values(data).filter((n) => n.status === "success");
      const errored = Object.values(data).filter((n) => n.status === "error");
      if (running.length > 0) {
        console.log(
          `%c[Pipeline] Running: ${running.map((n) => `${n.label} ${JSON.stringify(n.counts)}`).join(" | ")}`,
          "color: #f59e0b; font-weight: bold",
        );
      }
      if (done.length > 0) {
        console.log(
          `%c[Pipeline] Done: ${done.map((n) => n.label).join(", ")}`,
          "color: #10b981",
        );
      }
      if (errored.length > 0) {
        console.log(
          `%c[Pipeline] Errors: ${errored.map((n) => `${n.label}: ${n.last_error?.slice(0, 80)}`).join(" | ")}`,
          "color: #ef4444; font-weight: bold",
        );
      }
      setNodes(data);
      setError(null);
    } catch (err: any) {
      setError(err.message || "Failed to fetch status");
    } finally {
      setLoading(false);
    }
  }, [headers]);

  const runNode = useCallback(
    async (nodeId: string, force: boolean) => {
      try {
        await fetch(`${API_URL}/api/v1/admin/data-sources/run/${nodeId}`, {
          method: "POST",
          headers: headers(),
          body: JSON.stringify({ force }),
        });
        await fetchStatus();
      } catch (err: any) {
        setError(err.message);
      }
    },
    [headers, fetchStatus],
  );

  const updateConfig = useCallback(
    async (nodeId: string, enabled: boolean, settings: Record<string, any>) => {
      try {
        await fetch(`${API_URL}/api/v1/admin/data-sources/config/${nodeId}`, {
          method: "PUT",
          headers: headers(),
          body: JSON.stringify({ enabled, settings }),
        });
        await fetchStatus();
      } catch (err: any) {
        setError(err.message);
      }
    },
    [headers, fetchStatus],
  );

  const bustCache = useCallback(async () => {
    try {
      await fetch(`${API_URL}/api/v1/admin/data-sources/bust-cache`, {
        method: "POST",
        headers: headers(),
      });
      setBustCacheConfirm(false);
      await fetchStatus();
    } catch (err: any) {
      setError(err.message);
    }
  }, [headers, fetchStatus]);

  const [clearAllConfirm, setClearAllConfirm] = useState(false);
  const clearAll = useCallback(async () => {
    try {
      console.log(
        "%c[Pipeline] CLEARING ALL DATA (Firestore + Qdrant + caches)",
        "color: #ef4444; font-weight: bold; font-size: 14px",
      );
      const res = await fetch(`${API_URL}/api/v1/admin/data-sources/clear-all`, {
        method: "POST",
        headers: headers(),
      });
      const data = await res.json();
      console.log("%c[Pipeline] Clear result:", "color: #ef4444", data);
      setClearAllConfirm(false);
      await fetchStatus();
    } catch (err: any) {
      setError(err.message);
    }
  }, [headers, fetchStatus]);

  const runAll = useCallback(
    async (force: boolean) => {
      try {
        console.log(
          `%c[Pipeline] Starting run-all (force=${force}, top_communes=${topCommunes})`,
          "color: #6366f1; font-weight: bold",
        );
        await fetch(`${API_URL}/api/v1/admin/data-sources/run-all`, {
          method: "POST",
          headers: headers(),
          body: JSON.stringify({ force, top_communes: topCommunes }),
        });
        await fetchStatus();
      } catch (err: any) {
        setError(err.message);
      }
    },
    [headers, fetchStatus, topCommunes],
  );

  const stopNode = useCallback(
    async (nodeId: string) => {
      try {
        await fetch(`${API_URL}/api/v1/admin/data-sources/stop/${nodeId}`, {
          method: "POST",
          headers: headers(),
        });
        await fetchStatus();
      } catch (err: any) {
        setError(err.message);
      }
    },
    [headers, fetchStatus],
  );

  const stopAll = useCallback(async () => {
    try {
      await fetch(`${API_URL}/api/v1/admin/data-sources/stop-all`, {
        method: "POST",
        headers: headers(),
      });
      await fetchStatus();
    } catch (err: any) {
      setError(err.message);
    }
  }, [headers, fetchStatus]);

  const fetchPreview = useCallback(
    async (nodeId: string) => {
      setPreviewNode(nodeId);
      setPreviewData(null);
      setPreviewLoading(true);
      try {
        const res = await fetch(
          `${API_URL}/api/v1/admin/data-sources/preview/${nodeId}`,
          { headers: headers(), cache: "no-store" },
        );
        if (!res.ok) throw new Error(`Status ${res.status}`);
        const data = await res.json();
        setPreviewData(data);
      } catch (err: any) {
        setPreviewData({ error: err.message });
      } finally {
        setPreviewLoading(false);
      }
    },
    [headers],
  );

  // ---- Polling ----

  useEffect(() => {
    fetchStatus();
  }, [fetchStatus]);

  // Stable ref for fetchStatus so the interval doesn't get recreated
  const fetchStatusRef = useRef(fetchStatus);
  fetchStatusRef.current = fetchStatus;

  const anyRunning = Object.values(nodes).some((n) => n.status === "running");

  // Always poll – status can change server-side (e.g. after clear-all or
  // when a node finishes between polls) so we keep refreshing.
  useEffect(() => {
    pollRef.current = setInterval(() => fetchStatusRef.current(), POLL_INTERVAL_MS);
    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, []);

  // ---- Arrow position calculation ----

  const recalcArrows = useCallback(() => {
    if (!containerRef.current) return;
    const container = containerRef.current;
    const rect = container.getBoundingClientRect();
    const pos: Record<
      string,
      { cx: number; cy: number; bottom: number; top: number }
    > = {};

    for (const item of DAG_ROWS) {
      const el = container.querySelector(
        `[data-node-id="${item.id}"]`,
      ) as HTMLElement | null;
      if (!el) continue;
      const elRect = el.getBoundingClientRect();
      pos[item.id] = {
        cx: elRect.left - rect.left + elRect.width / 2,
        cy: elRect.top - rect.top + elRect.height / 2,
        bottom: elRect.bottom - rect.top,
        top: elRect.top - rect.top,
      };
    }
    setArrowPositions(pos);
  }, []);

  useEffect(() => {
    recalcArrows();
    window.addEventListener("resize", recalcArrows);
    return () => window.removeEventListener("resize", recalcArrows);
  }, [recalcArrows]);

  // Re-measure after nodes load
  useEffect(() => {
    if (Object.keys(nodes).length > 0) {
      const t = setTimeout(recalcArrows, 150);
      return () => clearTimeout(t);
    }
  }, [nodes, recalcArrows]);

  // ---- Node lookup helper ----

  function getNode(id: string): NodeConfig | null {
    return nodes[id] ?? null;
  }

  // ---- Render helpers ----

  function renderNodeCard(nodeId: string) {
    const node = getNode(nodeId);
    if (!node) {
      return (
        <div
          data-node-id={nodeId}
          className="flex h-32 items-center justify-center rounded-lg border border-dashed border-zinc-300 bg-zinc-50 text-xs text-zinc-400"
        >
          {nodeId} (not configured)
        </div>
      );
    }
    return (
      <div data-node-id={nodeId}>
        <NodeCard
          node={node}
          onRun={() => runNode(nodeId, false)}
          onForceRun={() => runNode(nodeId, true)}
          onStop={() => stopNode(nodeId)}
          onToggleEnabled={(enabled) =>
            updateConfig(nodeId, enabled, node.settings)
          }
          onUpdateSettings={(settings) =>
            updateConfig(nodeId, node.enabled, settings)
          }
          onPreview={() => fetchPreview(nodeId)}
        />
      </div>
    );
  }

  // ---- Main render ----

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-zinc-50">
        <Loader2 className="size-6 animate-spin text-zinc-400" />
      </div>
    );
  }

  return (
    <div className="fixed inset-0 overflow-y-auto bg-zinc-50">
      {/* Header */}
      <header className="border-b border-zinc-200 bg-white">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
          <div>
            <h1 className="text-lg font-bold tracking-tight text-zinc-900">
              Data Sources
            </h1>
            <p className="mt-0.5 text-xs text-zinc-500">
              Pipeline administration &middot; DAG overview
            </p>
          </div>
          <div className="flex items-center gap-2">
            {anyRunning && (
              <span className="mr-2 flex items-center gap-1.5 text-xs text-amber-600">
                <Loader2 className="size-3 animate-spin" />
                Running...
              </span>
            )}
          </div>
        </div>
      </header>

      {/* Error banner */}
      {error && (
        <div className="border-b border-red-200 bg-red-50 px-6 py-3">
          <div className="mx-auto flex max-w-6xl items-center gap-2 text-sm text-red-700">
            <AlertTriangle className="size-4 shrink-0" />
            <span>{error}</span>
            <button
              type="button"
              onClick={() => setError(null)}
              className="ml-auto text-xs underline"
            >
              Dismiss
            </button>
          </div>
        </div>
      )}

      {/* Toolbar */}
      <div className="border-b border-zinc-200 bg-white">
        <div className="mx-auto flex max-w-6xl items-center gap-2 px-6 py-3">
          {anyRunning ? (
            <Button
              size="sm"
              variant="outline"
              onClick={stopAll}
              className="h-8 gap-1.5 text-xs border-red-300 text-red-600 hover:bg-red-50"
            >
              <Square className="size-3.5" />
              Stop All
            </Button>
          ) : (
            <>
              <Button
                size="sm"
                onClick={() => runAll(false)}
                className="h-8 gap-1.5 text-xs"
              >
                <Play className="size-3.5" />
                Run All Enabled
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={() => runAll(true)}
                className="h-8 gap-1.5 text-xs"
              >
                <RotateCcw className="size-3.5" />
                Force Re-run All
              </Button>
            </>
          )}

          <div className="ml-4 flex items-center gap-1.5">
            <label
              htmlFor="top-communes"
              className="text-xs font-medium text-zinc-500 whitespace-nowrap"
            >
              Communes:
            </label>
            <input
              id="top-communes"
              type="number"
              min={1}
              max={500}
              value={topCommunes}
              onChange={(e) => setTopCommunes(Math.max(1, parseInt(e.target.value) || 1))}
              className="w-16 rounded-md border border-zinc-200 bg-white px-2 py-1 text-xs text-zinc-800 outline-none focus:border-zinc-400 focus:ring-1 focus:ring-zinc-300"
            />
          </div>

          <div className="flex-1" />

          {bustCacheConfirm ? (
            <div className="flex items-center gap-2">
              <span className="text-xs text-red-600 font-medium">
                Reset all checkpoints?
              </span>
              <Button
                size="sm"
                variant="destructive"
                onClick={bustCache}
                className="h-7 text-xs"
              >
                Confirm
              </Button>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => setBustCacheConfirm(false)}
                className="h-7 text-xs"
              >
                Cancel
              </Button>
            </div>
          ) : (
            <Button
              size="sm"
              variant="outline"
              onClick={() => setBustCacheConfirm(true)}
              className="h-8 gap-1.5 text-xs text-red-600 hover:text-red-700"
            >
              <Trash2 className="size-3.5" />
              Bust Cache
            </Button>
          )}

          {clearAllConfirm ? (
            <div className="flex items-center gap-2">
              <span className="text-xs text-red-600 font-bold">
                DELETE all data?
              </span>
              <Button
                size="sm"
                variant="destructive"
                onClick={clearAll}
                className="h-7 text-xs"
              >
                Yes, Clear All
              </Button>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => setClearAllConfirm(false)}
                className="h-7 text-xs"
              >
                Cancel
              </Button>
            </div>
          ) : (
            <Button
              size="sm"
              variant="outline"
              onClick={() => setClearAllConfirm(true)}
              className="h-8 gap-1.5 text-xs text-red-600 hover:text-red-700 border-red-300"
            >
              <Trash2 className="size-3.5" />
              Clear All Data
            </Button>
          )}

          <Button
            size="sm"
            variant="ghost"
            onClick={() => fetchStatus()}
            className="h-8 gap-1.5 text-xs"
          >
            <RotateCcw className="size-3.5" />
            Refresh
          </Button>
        </div>
      </div>

      {/* DAG Grid */}
      <div className="mx-auto max-w-6xl px-6 py-8">
        <div ref={containerRef} className="relative">
          {/* SVG arrow overlay */}
          <svg
            className="pointer-events-none absolute inset-0 z-0"
            width="100%"
            height="100%"
            style={{ overflow: "visible" }}
          >
            <defs>
              <marker
                id="arrowhead"
                markerWidth="8"
                markerHeight="6"
                refX="8"
                refY="3"
                orient="auto"
              >
                <path d="M0,0 L8,3 L0,6 Z" fill="#a1a1aa" />
              </marker>
            </defs>
            {DAG_EDGES.map(([from, to]) => {
              const fromPos = arrowPositions[from];
              const toPos = arrowPositions[to];
              if (!fromPos || !toPos) return null;

              const x1 = fromPos.cx;
              const y1 = fromPos.bottom + 2;
              const x2 = toPos.cx;
              const y2 = toPos.top - 2;
              const midY = (y1 + y2) / 2;

              return (
                <path
                  key={`${from}-${to}`}
                  d={`M${x1},${y1} C${x1},${midY} ${x2},${midY} ${x2},${y2}`}
                  fill="none"
                  stroke="#d4d4d8"
                  strokeWidth="1.5"
                  markerEnd="url(#arrowhead)"
                />
              );
            })}
          </svg>

          {/* Row 0: Sources */}
          <div className="relative z-10 grid grid-cols-4 gap-4">
            {renderNodeCard("population")}
            {renderNodeCard("candidatures")}
            {renderNodeCard("websites")}
            {renderNodeCard("pourquituvotes")}
          </div>

          {/* Spacer for arrows */}
          <div className="h-10" />

          {/* Row 1: Seed + Professions */}
          <div className="relative z-10 grid grid-cols-4 gap-4">
            <div /> {/* empty left cell */}
            {renderNodeCard("seed")}
            {renderNodeCard("professions")}
            <div /> {/* empty right cell */}
          </div>

          {/* Spacer for arrows */}
          <div className="h-10" />

          {/* Row 2: Scrapers (built-in + crawl service) */}
          <div className="relative z-10 grid grid-cols-4 gap-4">
            <div /> {/* empty left cell */}
            {renderNodeCard("scraper")}
            {renderNodeCard("crawl_scraper")}
            <div /> {/* empty right cell */}
          </div>

          {/* Spacer for arrows */}
          <div className="h-10" />

          {/* Row 3: Indexer */}
          <div className="relative z-10 grid grid-cols-4 gap-4">
            <div /> {/* empty left cell */}
            {renderNodeCard("indexer")}
            <div /> {/* empty cell */}
            <div /> {/* empty right cell */}
          </div>
        </div>
      </div>

      {/* Footer summary */}
      <div className="border-t border-zinc-200 bg-white">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-3 text-xs text-zinc-400">
          <span>
            {Object.values(nodes).filter((n) => n.enabled).length} /{" "}
            {Object.values(nodes).length} nodes enabled
          </span>
          <span>
            Last refresh:{" "}
            {new Date().toLocaleTimeString("fr-FR", {
              hour: "2-digit",
              minute: "2-digit",
              second: "2-digit",
            })}
          </span>
        </div>
      </div>

      {/* Preview modal */}
      {previewNode && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm"
          onClick={() => setPreviewNode(null)}
        >
          <div
            className="relative mx-4 flex max-h-[80vh] w-full max-w-3xl flex-col rounded-xl border border-zinc-200 bg-white shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal header */}
            <div className="flex items-center justify-between border-b border-zinc-100 px-5 py-3">
              <h2 className="text-sm font-semibold text-zinc-800">
                <Eye className="mr-2 inline-block size-4 text-zinc-400" />
                {nodes[previewNode]?.label ?? previewNode} — Data Preview
              </h2>
              <button
                type="button"
                onClick={() => setPreviewNode(null)}
                className="rounded-md p-1 text-zinc-400 transition-colors hover:bg-zinc-100 hover:text-zinc-600"
              >
                <X className="size-4" />
              </button>
            </div>

            {/* Modal body */}
            <div className="flex-1 overflow-auto p-5">
              {previewLoading ? (
                <div className="flex items-center justify-center py-16">
                  <Loader2 className="size-5 animate-spin text-zinc-400" />
                  <span className="ml-2 text-sm text-zinc-500">Loading preview...</span>
                </div>
              ) : previewData?.error ? (
                <div className="rounded-md bg-red-50 p-4 text-sm text-red-700">
                  {previewData.error}
                </div>
              ) : previewData?.samples?.length === 0 ? (
                <div className="py-12 text-center text-sm text-zinc-400">
                  No data available. Run this node first.
                </div>
              ) : previewData?.samples ? (
                <div className="flex flex-col gap-3">
                  <p className="text-xs text-zinc-400">
                    Showing {previewData.samples.length} sample{previewData.samples.length !== 1 ? "s" : ""}
                  </p>
                  {previewData.samples.map((item: any, i: number) => (
                    <div
                      key={i}
                      className="rounded-lg border border-zinc-100 bg-zinc-50 p-3"
                    >
                      <pre className="max-h-48 overflow-auto whitespace-pre-wrap text-[11px] leading-relaxed text-zinc-700">
                        {JSON.stringify(item, null, 2)}
                      </pre>
                    </div>
                  ))}
                </div>
              ) : (
                <pre className="max-h-96 overflow-auto whitespace-pre-wrap rounded-lg bg-zinc-50 p-4 text-[11px] leading-relaxed text-zinc-700">
                  {JSON.stringify(previewData, null, 2)}
                </pre>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

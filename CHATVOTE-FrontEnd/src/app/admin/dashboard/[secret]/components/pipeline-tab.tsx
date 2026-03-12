"use client";

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
  Zap,
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
// Props
// ---------------------------------------------------------------------------

interface PipelineTabProps {
  secret: string;
  apiUrl: string;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

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
  seed: "Writes candidate and party data to Firestore. Combines population, candidatures, and websites data into the final documents.",
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

function statusDot(status: NodeConfig["status"]) {
  const base = "size-2.5 rounded-full shrink-0";
  switch (status) {
    case "success":
      return <span className={`${base} bg-emerald-500`} />;
    case "running":
      return <span className={`${base} animate-pulse bg-amber-400`} />;
    case "error":
      return <span className={`${base} bg-red-500/100`} />;
    default:
      return <span className={`${base} bg-muted-foreground`} />;
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
      className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer items-center rounded-full transition-colors duration-200 focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-50 ${
        checked ? "bg-emerald-500" : "bg-purple-500"
      }`}
    >
      <span
        className={`pointer-events-none block size-3.5 rounded-full bg-card shadow-sm ring-0 transition-transform duration-200 ${
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
  onTriggerCrawl,
  onToggleEnabled,
  onUpdateSettings,
  onPreview,
}: {
  node: NodeConfig;
  onRun: () => void;
  onForceRun: () => void;
  onStop: () => void;
  onTriggerCrawl?: () => void;
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
      className={`relative flex w-full flex-col rounded-lg border border-border-subtle bg-card shadow-sm transition-shadow hover:shadow-md ${
        isRunning
          ? "border-amber-500/30"
          : node.status === "error"
            ? (node.last_error?.includes("Stopped by admin") || node.last_error?.includes("Cancelled by admin"))
              ? "border-amber-500/30"
              : "border-red-500/30"
            : node.status === "success"
              ? "border-emerald-500/30"
              : "border-border-subtle"
      }`}
    >
      {/* Header */}
      <div className="flex items-center gap-2 border-b border-border-subtle px-4 py-3">
        {statusDot(node.status)}
        <h3 className="flex-1 text-sm font-semibold text-foreground tracking-tight">
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
        <p className="px-4 pt-2 text-[11px] leading-relaxed text-muted-foreground">
          {NODE_DESCRIPTIONS[node.node_id]}
        </p>
      )}

      {/* Body */}
      <div className="flex flex-col gap-3 px-4 py-3">
        {/* Timestamp + duration */}
        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <span>{formatTimestamp(node.last_run_at)}</span>
          <span className="font-mono">
            {formatDuration(node.last_duration_s)}
          </span>
        </div>

        {/* Live progress (visible when running with any counts) */}
        {isRunning &&
          Object.keys(node.counts).length > 0 &&
          (() => {
            const c = node.counts;

            // For downloading phase, use downloaded/download_total for progress
            const isDownloading = c.phase === "downloading" && c.download_total;
            const totalKey = isDownloading
              ? "download_total"
              : (Object.keys(c).find((k) => k === "total") ??
                Object.keys(c).find((k) => k.endsWith("_total")));
            const total = totalKey ? Number(c[totalKey]) || 0 : 0;
            const doneKey = isDownloading
              ? "downloaded"
              : (Object.keys(c).find((k) => k === "scraped" || k === "done") ??
                Object.keys(c).find((k) => k.endsWith("_done")));
            const done = doneKey ? Number(c[doneKey]) || 0 : 0;
            const pct = total > 0 ? Math.round((done / total) * 100) : 0;

            const elapsed = Number(c.elapsed_s ?? 0);
            const eta = Number(c.eta_s ?? 0);
            const rate = c.rate_per_sec ?? c.rate_communes_per_sec ?? null;
            const phase = c.phase as string | undefined;
            const current = c.current as string | undefined;
            const currentUrls = c.current_urls as string | undefined;
            const lastResults = (
              Array.isArray(c.last_results) ? c.last_results : []
            ) as Array<{
              name?: string;
              pages?: number;
              chars?: number;
              ok?: boolean;
              error?: string;
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

            const metaKeys = new Set([
              totalKey,
              doneKey,
              "elapsed_s",
              "eta_s",
              "rate_per_sec",
              "rate_communes_per_sec",
              "phase",
              "current",
              "current_urls",
              "last_results",
              "downloaded",
              "download_total",
            ]);
            const extraStats = Object.entries(c).filter(
              ([k, v]) => !metaKeys.has(k) && typeof v !== "object",
            );

            return (
              <div className="flex flex-col gap-2">
                {phase && (
                  <span className="text-[11px] font-medium text-amber-600">
                    Phase: {phase}
                  </span>
                )}

                {current && (
                  <div className="rounded-md bg-amber-500/10 px-2.5 py-1.5">
                    <span className="text-[10px] font-medium text-amber-400">
                      {phase === "downloading" ? "Downloading:" : "Scraping:"}
                    </span>
                    <span className="ml-1 text-[11px] font-semibold text-amber-300">
                      {current}
                    </span>
                    {currentUrls && (
                      <p className="mt-0.5 truncate text-[10px] text-amber-600">
                        {currentUrls}
                      </p>
                    )}
                  </div>
                )}

                {total > 0 && (
                  <div className="flex items-center gap-2">
                    <div className="h-2.5 flex-1 overflow-hidden rounded-full bg-surface-elevated">
                      <div
                        className="h-full rounded-full bg-amber-400 transition-all duration-700 ease-out"
                        style={{ width: `${Math.min(100, pct)}%` }}
                      />
                    </div>
                    <span className="min-w-[3ch] text-right text-xs font-bold text-foreground">
                      {pct}%
                    </span>
                  </div>
                )}

                <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 text-[11px]">
                  {total > 0 && (
                    <>
                      <span className="text-muted-foreground">Progress</span>
                      <span className="text-right font-mono font-medium text-foreground">
                        {done} / {total}
                      </span>
                    </>
                  )}

                  {extraStats.map(([key, val]) => (
                    <React.Fragment key={key}>
                      <span className="text-muted-foreground">
                        {key.replace(/_/g, " ")}
                      </span>
                      <span className="text-right font-mono font-medium text-foreground">
                        {key === "total_chars"
                          ? fmtChars(Number(val))
                          : String(val)}
                      </span>
                    </React.Fragment>
                  ))}

                  {rate !== null && (
                    <>
                      <span className="text-muted-foreground">Speed</span>
                      <span className="text-right font-mono font-medium text-foreground">
                        {rate}/s
                      </span>
                    </>
                  )}

                  {elapsed > 0 && (
                    <>
                      <span className="text-muted-foreground">Elapsed</span>
                      <span className="text-right font-mono font-medium text-foreground">
                        {fmtTime(elapsed)}
                      </span>
                    </>
                  )}

                  {eta > 0 && (
                    <>
                      <span className="text-muted-foreground">ETA</span>
                      <span className="text-right font-mono font-medium text-amber-600">
                        ~{fmtTime(eta)}
                      </span>
                    </>
                  )}
                </div>

                {lastResults.length > 0 && (
                  <div className="flex flex-col gap-1 border-t border-border-subtle pt-2">
                    <span className="text-[10px] font-medium text-muted-foreground">
                      Recent
                    </span>
                    {lastResults.map((r, i) => (
                      <div
                        key={i}
                        className="flex items-center gap-1.5 text-[10px]"
                      >
                        {r.ok ? (
                          <CheckCircle2 className="size-3 shrink-0 text-emerald-500" />
                        ) : (
                          <XCircle className="size-3 shrink-0 text-red-400" />
                        )}
                        <span className="truncate font-medium text-foreground">
                          {r.name}
                        </span>
                        {r.ok ? (
                          <span className="ml-auto shrink-0 font-mono text-muted-foreground">
                            {r.pages}p &middot;{" "}
                            {r.chars !== undefined
                              ? r.chars >= 1_000
                                ? `${(r.chars / 1_000).toFixed(0)}K`
                                : String(r.chars)
                              : ""}
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
                className="inline-flex items-center rounded-full bg-surface-elevated px-2 py-0.5 text-[11px] font-medium text-muted-foreground"
              >
                {key.replace(/_/g, " ")}:&nbsp;
                <span className="font-semibold text-foreground">
                  {String(val)}
                </span>
              </span>
            ))}
          </div>
        )}

        {/* Error */}
        {node.status === "error" && node.last_error && (() => {
          const isAdminStop = node.last_error.includes("Stopped by admin") || node.last_error.includes("Cancelled by admin");
          return (
            <div className={`rounded-md p-2 ${isAdminStop ? "bg-amber-500/10" : "bg-red-500/10"}`}>
              <button
                type="button"
                onClick={() => setErrorOpen(!errorOpen)}
                className={`flex w-full items-center gap-1 text-left text-xs font-medium ${isAdminStop ? "text-amber-400" : "text-red-400"}`}
              >
                {isAdminStop ? (
                  <Square className="size-3.5 shrink-0" />
                ) : (
                  <AlertTriangle className="size-3.5 shrink-0" />
                )}
                <span className="flex-1 truncate">
                  {node.last_error.split("\n")[0]}
                </span>
                {!isAdminStop && (errorOpen ? (
                  <ChevronDown className="size-3.5 shrink-0" />
                ) : (
                  <ChevronRight className="size-3.5 shrink-0" />
                ))}
              </button>
              {errorOpen && !isAdminStop && (
                <pre className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap text-[11px] leading-relaxed text-red-400">
                  {node.last_error}
                </pre>
              )}
            </div>
          );
        })()}

        {/* Actions */}
        <div className="flex items-center gap-2">
          {isRunning ? (
            <>
              <Button
                size="sm"
                variant="outline"
                onClick={onStop}
                className="h-7 gap-1.5 px-2.5 text-xs border-red-500/30 text-red-400 hover:bg-red-500/100/10"
              >
                <Square className="size-3" />
                Stop
              </Button>
              {onTriggerCrawl && (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={onTriggerCrawl}
                  className="h-7 gap-1.5 px-2.5 text-xs border-amber-500/30 text-amber-400 hover:bg-amber-500/100/10"
                >
                  <Zap className="size-3" />
                  Trigger Scrape
                </Button>
              )}
            </>
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
              className="h-7 gap-1 px-2 text-xs text-muted-foreground"
              title="Preview data"
            >
              <Eye className="size-3" />
            </Button>
            {settingsKeys.length > 0 && (
              <Button
                size="sm"
                variant="ghost"
                onClick={() => setSettingsOpen(!settingsOpen)}
                className="h-7 gap-1 px-2 text-xs text-muted-foreground"
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
          <div className="flex flex-col gap-2 rounded-md bg-background p-3">
            {settingsKeys.map((key) => (
              <label key={key} className="flex flex-col gap-1">
                <span className="text-[11px] font-medium text-muted-foreground">
                  {key.replace(/_/g, " ")}
                </span>
                {SETTING_OPTIONS[key] ? (
                  <select
                    value={String(localSettings[key] ?? "")}
                    onChange={(e) => handleSettingChange(key, e.target.value)}
                    className="rounded-md border border-border-subtle bg-card px-2 py-1.5 text-xs text-foreground outline-none focus:border-border-strong focus:ring-1 focus:ring-ring"
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
                    className="rounded-md border border-border-subtle bg-card px-2 py-1.5 text-xs text-foreground outline-none focus:border-border-strong focus:ring-1 focus:ring-ring"
                  >
                    <option value="true">true</option>
                    <option value="false">false</option>
                  </select>
                ) : (
                  <input
                    type="text"
                    value={String(localSettings[key] ?? "")}
                    onChange={(e) => handleSettingChange(key, e.target.value)}
                    className="rounded-md border border-border-subtle bg-card px-2 py-1 text-xs text-foreground outline-none focus:border-border-strong focus:ring-1 focus:ring-ring"
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
// Pipeline Tab Component
// ---------------------------------------------------------------------------

export default function PipelineTab({ secret, apiUrl }: PipelineTabProps) {
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
      const res = await fetch(`${apiUrl}/api/v1/admin/data-sources/status`, {
        headers: headers(),
        cache: "no-store",
      });
      if (!res.ok) throw new Error(`Status ${res.status}`);
      const data: NodesMap = await res.json();
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
  }, [headers, apiUrl]);

  const runNode = useCallback(
    async (nodeId: string, force: boolean) => {
      try {
        await fetch(`${apiUrl}/api/v1/admin/data-sources/run/${nodeId}`, {
          method: "POST",
          headers: headers(),
          body: JSON.stringify({ force }),
        });
        await fetchStatus();
      } catch (err: any) {
        setError(err.message);
      }
    },
    [headers, fetchStatus, apiUrl],
  );

  const updateConfig = useCallback(
    async (nodeId: string, enabled: boolean, settings: Record<string, any>) => {
      try {
        await fetch(`${apiUrl}/api/v1/admin/data-sources/config/${nodeId}`, {
          method: "PUT",
          headers: headers(),
          body: JSON.stringify({ enabled, settings }),
        });
        await fetchStatus();
      } catch (err: any) {
        setError(err.message);
      }
    },
    [headers, fetchStatus, apiUrl],
  );

  const bustCache = useCallback(async () => {
    try {
      await fetch(`${apiUrl}/api/v1/admin/data-sources/bust-cache`, {
        method: "POST",
        headers: headers(),
      });
      setBustCacheConfirm(false);
      await fetchStatus();
    } catch (err: any) {
      setError(err.message);
    }
  }, [headers, fetchStatus, apiUrl]);

  const [clearAllConfirm, setClearAllConfirm] = useState(false);
  const clearAll = useCallback(async () => {
    try {
      console.log(
        "%c[Pipeline] CLEARING ALL DATA (Firestore + Qdrant + caches)",
        "color: #ef4444; font-weight: bold; font-size: 14px",
      );
      const res = await fetch(
        `${apiUrl}/api/v1/admin/data-sources/clear-all`,
        {
          method: "POST",
          headers: headers(),
        },
      );
      const data = await res.json();
      console.log("%c[Pipeline] Clear result:", "color: #ef4444", data);
      setClearAllConfirm(false);
      await fetchStatus();
    } catch (err: any) {
      setError(err.message);
    }
  }, [headers, fetchStatus, apiUrl]);

  const runAll = useCallback(
    async (force: boolean) => {
      try {
        console.log(
          `%c[Pipeline] Starting run-all (force=${force}, top_communes=${topCommunes})`,
          "color: #6366f1; font-weight: bold",
        );
        await fetch(`${apiUrl}/api/v1/admin/data-sources/run-all`, {
          method: "POST",
          headers: headers(),
          body: JSON.stringify({ force, top_communes: topCommunes }),
        });
        await fetchStatus();
      } catch (err: any) {
        setError(err.message);
      }
    },
    [headers, fetchStatus, topCommunes, apiUrl],
  );

  const stopNode = useCallback(
    async (nodeId: string) => {
      try {
        await fetch(`${apiUrl}/api/v1/admin/data-sources/stop/${nodeId}`, {
          method: "POST",
          headers: headers(),
        });
        await fetchStatus();
      } catch (err: any) {
        setError(err.message);
      }
    },
    [headers, fetchStatus, apiUrl],
  );

  const triggerCrawl = useCallback(async () => {
    try {
      const res = await fetch(`${apiUrl}/api/v1/admin/data-sources/trigger-crawl`, {
        method: "POST",
        headers: headers(),
      });
      const data = await res.json();
      if (data.error) {
        setError(`Trigger failed: ${data.error}`);
      }
    } catch (err: any) {
      setError(err.message);
    }
  }, [headers, apiUrl]);

  const stopAll = useCallback(async () => {
    try {
      await fetch(`${apiUrl}/api/v1/admin/data-sources/stop-all`, {
        method: "POST",
        headers: headers(),
      });
      await fetchStatus();
    } catch (err: any) {
      setError(err.message);
    }
  }, [headers, fetchStatus, apiUrl]);

  const fetchPreview = useCallback(
    async (nodeId: string) => {
      setPreviewNode(nodeId);
      setPreviewData(null);
      setPreviewLoading(true);
      try {
        const res = await fetch(
          `${apiUrl}/api/v1/admin/data-sources/preview/${nodeId}`,
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
    [headers, apiUrl],
  );

  // ---- Polling ----

  useEffect(() => {
    fetchStatus();
  }, [fetchStatus]);

  const fetchStatusRef = useRef(fetchStatus);
  fetchStatusRef.current = fetchStatus;

  const anyRunning = Object.values(nodes).some((n) => n.status === "running");

  useEffect(() => {
    pollRef.current = setInterval(
      () => fetchStatusRef.current(),
      POLL_INTERVAL_MS,
    );
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
          className="flex h-32 items-center justify-center rounded-lg border border-dashed border-border-subtle bg-background text-xs text-muted-foreground"
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
          onTriggerCrawl={nodeId === "crawl_scraper" ? triggerCrawl : undefined}
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
      <div className="flex items-center justify-center py-20">
        <Loader2 className="size-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="space-y-0">
      {/* Error banner */}
      {error && (
        <div className="mb-4 rounded-md border border-red-500/30 bg-red-500/10 px-4 py-3">
          <div className="flex items-center gap-2 text-sm text-red-400">
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
      <div className="mb-4 flex items-center gap-2 rounded-lg border border-border-subtle bg-card px-4 py-3">
        {anyRunning ? (
          <Button
            size="sm"
            variant="outline"
            onClick={stopAll}
            className="h-8 gap-1.5 text-xs border-red-500/30 text-red-400 hover:bg-red-500/100/10"
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
            className="text-xs font-medium text-muted-foreground whitespace-nowrap"
          >
            Communes:
          </label>
          <input
            id="top-communes"
            type="number"
            min={1}
            max={500}
            value={topCommunes}
            onChange={(e) =>
              setTopCommunes(Math.max(1, parseInt(e.target.value) || 1))
            }
            className="w-16 rounded-md border border-border-subtle bg-card px-2 py-1 text-xs text-foreground outline-none focus:border-border-strong focus:ring-1 focus:ring-ring"
          />
        </div>

        {anyRunning && (
          <span className="ml-2 flex items-center gap-1.5 text-xs text-amber-600">
            <Loader2 className="size-3 animate-spin" />
            Running...
          </span>
        )}

        <div className="flex-1" />

        {bustCacheConfirm ? (
          <div className="flex items-center gap-2">
            <span className="text-xs text-red-400 font-medium">
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
            className="h-8 gap-1.5 text-xs text-red-400 hover:text-red-400"
          >
            <Trash2 className="size-3.5" />
            Bust Cache
          </Button>
        )}

        {clearAllConfirm ? (
          <div className="flex items-center gap-2">
            <span className="text-xs text-red-400 font-bold">
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
            className="h-8 gap-1.5 text-xs text-red-400 hover:text-red-400 border-red-500/30"
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

      {/* DAG Grid */}
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
          <div />
          {renderNodeCard("seed")}
          {renderNodeCard("professions")}
          <div />
        </div>

        {/* Spacer for arrows */}
        <div className="h-10" />

        {/* Row 2: Scrapers */}
        <div className="relative z-10 grid grid-cols-4 gap-4">
          <div />
          {renderNodeCard("scraper")}
          {renderNodeCard("crawl_scraper")}
          <div />
        </div>

        {/* Spacer for arrows */}
        <div className="h-10" />

        {/* Row 3: Indexer */}
        <div className="relative z-10 grid grid-cols-4 gap-4">
          <div />
          {renderNodeCard("indexer")}
          <div />
          <div />
        </div>
      </div>

      {/* Footer summary */}
      <div className="mt-8 flex items-center justify-between rounded-lg border border-border-subtle bg-card px-4 py-3 text-xs text-muted-foreground">
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

      {/* Preview modal */}
      {previewNode && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm"
          onClick={() => setPreviewNode(null)}
        >
          <div
            className="relative mx-4 flex max-h-[80vh] w-full max-w-3xl flex-col rounded-xl border border-border-subtle bg-card shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between border-b border-border-subtle px-5 py-3">
              <h2 className="text-sm font-semibold text-foreground">
                <Eye className="mr-2 inline-block size-4 text-muted-foreground" />
                {nodes[previewNode]?.label ?? previewNode} — Data Preview
              </h2>
              <button
                type="button"
                onClick={() => setPreviewNode(null)}
                className="rounded-md p-1 text-muted-foreground transition-colors hover:bg-surface-elevated hover:text-foreground"
              >
                <X className="size-4" />
              </button>
            </div>

            <div className="flex-1 overflow-auto p-5">
              {previewLoading ? (
                <div className="flex items-center justify-center py-16">
                  <Loader2 className="size-5 animate-spin text-muted-foreground" />
                  <span className="ml-2 text-sm text-muted-foreground">
                    Loading preview...
                  </span>
                </div>
              ) : previewData?.error ? (
                <div className="rounded-md bg-red-500/10 p-4 text-sm text-red-400">
                  {previewData.error}
                </div>
              ) : previewData?.samples?.length === 0 ? (
                <div className="py-12 text-center text-sm text-muted-foreground">
                  No data available. Run this node first.
                </div>
              ) : previewData?.samples ? (
                <div className="flex flex-col gap-3">
                  <p className="text-xs text-muted-foreground">
                    Showing {previewData.samples.length} sample
                    {previewData.samples.length !== 1 ? "s" : ""}
                  </p>
                  {previewData.samples.map((item: any, i: number) => (
                    <div
                      key={i}
                      className="rounded-lg border border-border-subtle bg-background p-3"
                    >
                      <pre className="max-h-48 overflow-auto whitespace-pre-wrap text-[11px] leading-relaxed text-foreground">
                        {JSON.stringify(item, null, 2)}
                      </pre>
                    </div>
                  ))}
                </div>
              ) : (
                <pre className="max-h-96 overflow-auto whitespace-pre-wrap rounded-lg bg-background p-4 text-[11px] leading-relaxed text-foreground">
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

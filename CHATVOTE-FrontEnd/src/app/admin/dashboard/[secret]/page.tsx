"use client";

import { Suspense, useCallback, useEffect, useState } from "react";

import dynamic from "next/dynamic";
import { useParams, useRouter, useSearchParams } from "next/navigation";

const API_URL =
  process.env.NEXT_PUBLIC_API_URL ||
  process.env.NEXT_PUBLIC_SOCKET_URL ||
  "http://localhost:8080";

const TABS = [
  "overview",
  "pipeline",
  "coverage",
  "charts",
  "chats",
  "multi-query",
  "consistency",
  "crawler",
  "upload",
] as const;
type TabId = (typeof TABS)[number];

const TAB_LABELS: Record<TabId, string> = {
  overview: "Overview",
  pipeline: "Pipeline",
  coverage: "Coverage",
  charts: "Charts",
  chats: "Chat Sessions",
  "multi-query": "Multi Query",
  consistency: "Data Consistency",
  crawler: "Crawler",
  upload: "Upload",
};

// Lazy load tab components
const OverviewTab = dynamic(() => import("./components/overview-tab"), {
  ssr: false,
});
const PipelineTab = dynamic(() => import("./components/pipeline-tab"), {
  ssr: false,
});
const CoverageTab = dynamic(() => import("./components/coverage-tab"), {
  ssr: false,
});
const ChatSessionsTab = dynamic(
  () => import("./components/chat-sessions-tab"),
  { ssr: false },
);
const ChartsTab = dynamic(() => import("./components/charts-tab"), {
  ssr: false,
});
const MultiQueryTab = dynamic(() => import("./components/multi-query-tab"), {
  ssr: false,
});
const DataConsistencyTab = dynamic(
  () => import("./components/data-consistency-tab"),
  { ssr: false },
);
const CrawlerTab = dynamic(() => import("./components/crawler-tab"), {
  ssr: false,
});
const UploadTab = dynamic(() => import("./components/upload-tab"), {
  ssr: false,
});

export default function AdminDashboard() {
  const params = useParams<{ secret: string }>();
  const searchParams = useSearchParams();
  const router = useRouter();
  const secret = decodeURIComponent(params.secret).replace(/\s+/g, "");

  const rawTab = searchParams.get("tab") as TabId | null;
  const initialTab: TabId =
    rawTab && TABS.includes(rawTab) ? rawTab : "overview";
  const [activeTab, setActiveTab] = useState<TabId>(initialTab);
  const [activatedTabs, setActivatedTabs] = useState<Set<TabId>>(
    new Set([initialTab]),
  );
  const [warningCounts, setWarningCounts] = useState({
    critical: 0,
    warning: 0,
    info: 0,
  });
  const [timeRange, setTimeRange] = useState(24); // hours
  const [authorized, setAuthorized] = useState<boolean | null>(null);
  const [maintenanceEnabled, setMaintenanceEnabled] = useState<boolean | null>(
    null,
  );
  const [maintenanceLoading, setMaintenanceLoading] = useState(false);
  const [resettingRateLimit, setResettingRateLimit] = useState(false);
  const [rateLimitMsg, setRateLimitMsg] = useState<string | null>(null);

  // Validate secret on mount
  useEffect(() => {
    fetch(`${API_URL}/api/v1/admin/data-sources/status`, {
      headers: { "X-Admin-Secret": secret },
    })
      .then((r) => setAuthorized(r.ok))
      .catch(() => setAuthorized(false));
  }, [secret]);

  // Fetch maintenance status on mount
  useEffect(() => {
    fetch(`${API_URL}/api/v1/admin/maintenance`, {
      headers: { "X-Admin-Secret": secret },
    })
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (data) setMaintenanceEnabled(Boolean(data.enabled));
      })
      .catch(() => {});
  }, [secret]);

  const toggleMaintenance = useCallback(async () => {
    const next = !maintenanceEnabled;
    if (
      next &&
      !window.confirm(
        "Activer le mode maintenance ? Les utilisateurs verront une page de maintenance.",
      )
    ) {
      return;
    }
    setMaintenanceLoading(true);
    try {
      const res = await fetch(`${API_URL}/api/v1/admin/maintenance`, {
        method: "PUT",
        headers: {
          "X-Admin-Secret": secret,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ enabled: next, message: "" }),
      });
      if (res.ok) {
        setMaintenanceEnabled(next);
      }
    } catch {
      // ignore
    } finally {
      setMaintenanceLoading(false);
    }
  }, [maintenanceEnabled, secret]);

  const resetRateLimit = useCallback(async () => {
    setResettingRateLimit(true);
    setRateLimitMsg(null);
    try {
      const res = await fetch(`${API_URL}/api/v1/admin/reset-rate-limit`, {
        method: "POST",
        headers: { "X-Admin-Secret": secret },
      });
      const data = await res.json();
      if (res.ok) {
        setRateLimitMsg("Rate limit reset");
      } else {
        setRateLimitMsg(`Error: ${data.message || res.status}`);
      }
    } catch (err: unknown) {
      setRateLimitMsg(
        `Error: ${err instanceof Error ? err.message : String(err)}`,
      );
    } finally {
      setResettingRateLimit(false);
      setTimeout(() => setRateLimitMsg(null), 5000);
    }
  }, [secret]);

  const switchTab = useCallback(
    (tab: TabId) => {
      setActiveTab(tab);
      setActivatedTabs((prev) => {
        if (prev.has(tab)) return prev;
        const next = new Set(prev);
        next.add(tab);
        return next;
      });
      router.replace(`/admin/dashboard/${secret}?tab=${tab}`, {
        scroll: false,
      });
    },
    [secret, router],
  );

  if (authorized === null) {
    return (
      <div className="bg-background flex min-h-screen items-center justify-center">
        <div className="text-muted-foreground text-sm">Loading...</div>
      </div>
    );
  }

  if (!authorized) {
    return (
      <div className="bg-background flex min-h-screen items-center justify-center">
        <div className="text-sm text-red-500">Unauthorized</div>
      </div>
    );
  }

  return (
    <div
      className="bg-background min-h-screen overflow-auto"
      style={{ height: "100vh" }}
    >
      {/* Header */}
      <div className="bg-card flex items-center justify-between border-b px-6 py-4">
        <h1 className="text-foreground text-xl font-bold">Admin Dashboard</h1>
        <div className="flex items-center gap-4">
          {/* AI Config */}
          <a
            href={`/admin/ai-config/${secret}`}
            className="flex items-center gap-1.5 rounded border border-blue-500/40 bg-blue-500/10 px-3 py-1.5 text-xs font-medium text-blue-400 transition-colors hover:bg-blue-500/20"
          >
            AI Config
          </a>
          {/* Reset Rate Limit */}
          <button
            type="button"
            onClick={resetRateLimit}
            disabled={resettingRateLimit}
            title="Reset rate limit (memory + Firestore)"
            className="flex items-center gap-1.5 rounded border border-amber-500/40 bg-amber-500/10 px-3 py-1.5 text-xs font-medium text-amber-400 transition-colors hover:bg-amber-500/20 disabled:opacity-50"
          >
            {resettingRateLimit ? (
              <span className="h-3 w-3 animate-spin rounded-full border-2 border-amber-400 border-t-transparent" />
            ) : (
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="h-3 w-3"><path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/><path d="m14.5 9.5-5 5"/><path d="m9.5 9.5 5 5"/></svg>
            )}
            Reset Rate Limit
          </button>
          {rateLimitMsg && (
            <span className={`text-xs ${rateLimitMsg.startsWith("Error") ? "text-red-400" : "text-green-400"}`}>
              {rateLimitMsg}
            </span>
          )}
          {/* Maintenance toggle */}
          {maintenanceEnabled !== null && (
            <button
              type="button"
              onClick={toggleMaintenance}
              disabled={maintenanceLoading}
              title={
                maintenanceEnabled
                  ? "Désactiver la maintenance"
                  : "Activer la maintenance"
              }
              className={`flex items-center gap-2 rounded border px-3 py-1.5 text-sm font-medium transition-colors disabled:opacity-50 ${
                maintenanceEnabled
                  ? "border-red-500/40 bg-red-500/10 text-red-400 hover:bg-red-500/20"
                  : "border-green-500/40 bg-green-500/10 text-green-400 hover:bg-green-500/20"
              }`}
            >
              <span
                className={`h-2 w-2 rounded-full ${
                  maintenanceEnabled ? "bg-red-500" : "bg-green-500"
                }`}
              />
              {maintenanceEnabled ? "Maintenance ON" : "Live"}
            </button>
          )}
          <select
            value={timeRange}
            onChange={(e) => setTimeRange(Number(e.target.value))}
            className="border-border-subtle bg-card text-foreground focus:ring-ring rounded border px-3 py-1.5 text-sm focus:ring-1 focus:outline-none"
          >
            <option value={1}>Last 1h</option>
            <option value={24}>Last 24h</option>
            <option value={168}>Last 7d</option>
            <option value={720}>Last 30d</option>
            <option value={0}>All time</option>
          </select>
        </div>
      </div>

      {/* Tab bar */}
      <div className="bg-card flex gap-0 border-b px-6">
        {TABS.map((tab) => (
          <button
            key={tab}
            type="button"
            onClick={() => switchTab(tab)}
            className={`border-b-2 px-4 py-3 text-sm font-medium transition-colors ${
              activeTab === tab
                ? "border-blue-600 text-blue-400"
                : "text-muted-foreground hover:text-foreground border-transparent"
            }`}
          >
            {TAB_LABELS[tab]}
            {tab === "overview" && warningCounts.critical > 0 && (
              <span className="ml-2 rounded-full bg-red-500/100 px-1.5 py-0.5 text-xs text-white">
                {warningCounts.critical}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="p-6">
        <Suspense
          fallback={
            <div className="text-muted-foreground py-8 text-center text-sm">
              Loading...
            </div>
          }
        >
          {activatedTabs.has("overview") && (
            <div className={activeTab !== "overview" ? "hidden" : undefined}>
              <OverviewTab
                secret={secret}
                apiUrl={API_URL}
                timeRange={timeRange}
                onWarningCounts={setWarningCounts}
              />
            </div>
          )}
          {activatedTabs.has("pipeline") && (
            <div className={activeTab !== "pipeline" ? "hidden" : undefined}>
              <PipelineTab
                secret={secret}
                apiUrl={API_URL}
                active={activeTab === "pipeline"}
              />
            </div>
          )}
          {activatedTabs.has("coverage") && (
            <div className={activeTab !== "coverage" ? "hidden" : undefined}>
              <CoverageTab secret={secret} apiUrl={API_URL} />
            </div>
          )}
          {activatedTabs.has("charts") && (
            <div className={activeTab !== "charts" ? "hidden" : undefined}>
              <ChartsTab secret={secret} apiUrl={API_URL} />
            </div>
          )}
          {activatedTabs.has("chats") && (
            <div className={activeTab !== "chats" ? "hidden" : undefined}>
              <ChatSessionsTab
                secret={secret}
                apiUrl={API_URL}
                timeRange={timeRange}
                active={activeTab === "chats"}
              />
            </div>
          )}
          {activatedTabs.has("multi-query") && (
            <div className={activeTab !== "multi-query" ? "hidden" : undefined}>
              <MultiQueryTab secret={secret} apiUrl={API_URL} />
            </div>
          )}
          {activatedTabs.has("consistency") && (
            <div className={activeTab !== "consistency" ? "hidden" : undefined}>
              <DataConsistencyTab secret={secret} apiUrl={API_URL} />
            </div>
          )}
          {activatedTabs.has("crawler") && (
            <div className={activeTab !== "crawler" ? "hidden" : undefined}>
              <CrawlerTab
                secret={secret}
                apiUrl={API_URL}
                active={activeTab === "crawler"}
              />
            </div>
          )}
          {activatedTabs.has("upload") && (
            <div className={activeTab !== "upload" ? "hidden" : undefined}>
              <UploadTab
                secret={secret}
                apiUrl={API_URL}
                active={activeTab === "upload"}
              />
            </div>
          )}
        </Suspense>
      </div>
    </div>
  );
}

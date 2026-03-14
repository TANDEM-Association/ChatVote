"use client";

import { useParams, useSearchParams, useRouter } from "next/navigation";
import { useState, useEffect, useCallback, Suspense } from "react";
import dynamic from "next/dynamic";

const API_URL =
  process.env.NEXT_PUBLIC_API_URL ||
  process.env.NEXT_PUBLIC_SOCKET_URL ||
  "http://localhost:8080";

const TABS = ["overview", "pipeline", "coverage", "charts", "chats", "multi-query", "consistency", "crawler", "observability", "logs", "alerts"] as const;
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
  observability: "Observability",
  logs: "Logs",
  alerts: "Alerts",
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
const ObservabilityTab = dynamic(
  () => import("./components/observability-tab"),
  { ssr: false },
);
const LogsTab = dynamic(() => import("./components/logs-tab"), {
  ssr: false,
});
const AlertsTab = dynamic(() => import("./components/alerts-tab"), {
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
  const [activatedTabs, setActivatedTabs] = useState<Set<TabId>>(new Set([initialTab]));
  const [warningCounts, setWarningCounts] = useState({
    critical: 0,
    warning: 0,
    info: 0,
  });
  const [timeRange, setTimeRange] = useState(24); // hours
  const [authorized, setAuthorized] = useState<boolean | null>(null);
  const [maintenanceEnabled, setMaintenanceEnabled] = useState<boolean | null>(null);
  const [maintenanceLoading, setMaintenanceLoading] = useState(false);

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
      .then((data) => { if (data) setMaintenanceEnabled(Boolean(data.enabled)); })
      .catch(() => {});
  }, [secret]);

  const toggleMaintenance = useCallback(async () => {
    const next = !maintenanceEnabled;
    if (next && !window.confirm("Activer le mode maintenance ? Les utilisateurs verront une page de maintenance.")) {
      return;
    }
    setMaintenanceLoading(true);
    try {
      const res = await fetch(`${API_URL}/api/v1/admin/maintenance`, {
        method: "PUT",
        headers: { "X-Admin-Secret": secret, "Content-Type": "application/json" },
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
      <div className="flex min-h-screen items-center justify-center bg-background">
        <div className="text-sm text-muted-foreground">Loading...</div>
      </div>
    );
  }

  if (!authorized) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background">
        <div className="text-sm text-red-500">Unauthorized</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background overflow-auto" style={{ height: "100vh" }}>
      {/* Header */}
      <div className="border-b bg-card px-6 py-4 flex items-center justify-between">
        <h1 className="text-xl font-bold text-foreground">Admin Dashboard</h1>
        <div className="flex items-center gap-4">
          {/* Maintenance toggle */}
          {maintenanceEnabled !== null && (
            <button
              type="button"
              onClick={toggleMaintenance}
              disabled={maintenanceLoading}
              title={maintenanceEnabled ? "Désactiver la maintenance" : "Activer la maintenance"}
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
            className="rounded border border-border-subtle px-3 py-1.5 text-sm bg-card text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
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
      <div className="border-b bg-card px-6 flex gap-0 overflow-x-auto">
        {TABS.map((tab) => (
          <button
            key={tab}
            type="button"
            onClick={() => switchTab(tab)}
            className={`px-4 py-3 text-sm font-medium border-b-2 transition-colors whitespace-nowrap ${
              activeTab === tab
                ? "border-blue-600 text-blue-400"
                : "border-transparent text-muted-foreground hover:text-foreground"
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
            <div className="py-8 text-center text-sm text-muted-foreground">
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
              <PipelineTab secret={secret} apiUrl={API_URL} active={activeTab === "pipeline"} />
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
              <CrawlerTab secret={secret} apiUrl={API_URL} active={activeTab === "crawler"} />
            </div>
          )}
          {activatedTabs.has("observability") && (
            <div className={activeTab !== "observability" ? "hidden" : undefined}>
              <ObservabilityTab secret={secret} apiUrl={API_URL} active={activeTab === "observability"} />
            </div>
          )}
          {activatedTabs.has("logs") && (
            <div className={activeTab !== "logs" ? "hidden" : undefined}>
              <LogsTab secret={secret} apiUrl={API_URL} active={activeTab === "logs"} />
            </div>
          )}
          {activatedTabs.has("alerts") && (
            <div className={activeTab !== "alerts" ? "hidden" : undefined}>
              <AlertsTab secret={secret} apiUrl={API_URL} active={activeTab === "alerts"} />
            </div>
          )}
        </Suspense>
      </div>
    </div>
  );
}

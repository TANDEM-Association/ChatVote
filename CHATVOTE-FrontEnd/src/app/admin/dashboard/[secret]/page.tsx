"use client";

import { useParams, useSearchParams, useRouter } from "next/navigation";
import { useState, useEffect, useCallback, Suspense } from "react";
import dynamic from "next/dynamic";

const API_URL =
  process.env.NEXT_PUBLIC_API_URL ||
  process.env.NEXT_PUBLIC_SOCKET_URL ||
  "http://localhost:8080";

const TABS = ["overview", "pipeline", "coverage", "chats"] as const;
type TabId = (typeof TABS)[number];

const TAB_LABELS: Record<TabId, string> = {
  overview: "Overview",
  pipeline: "Pipeline",
  coverage: "Coverage",
  chats: "Chat Sessions",
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

export default function AdminDashboard() {
  const params = useParams<{ secret: string }>();
  const searchParams = useSearchParams();
  const router = useRouter();
  const secret = params.secret;

  const rawTab = searchParams.get("tab") as TabId | null;
  const initialTab: TabId =
    rawTab && TABS.includes(rawTab) ? rawTab : "overview";
  const [activeTab, setActiveTab] = useState<TabId>(initialTab);
  const [warningCounts, setWarningCounts] = useState({
    critical: 0,
    warning: 0,
    info: 0,
  });
  const [timeRange, setTimeRange] = useState(24); // hours
  const [authorized, setAuthorized] = useState<boolean | null>(null);

  // Validate secret on mount
  useEffect(() => {
    fetch(`${API_URL}/api/v1/admin/data-sources/status`, {
      headers: { "X-Admin-Secret": secret },
    })
      .then((r) => setAuthorized(r.ok))
      .catch(() => setAuthorized(false));
  }, [secret]);

  const switchTab = useCallback(
    (tab: TabId) => {
      setActiveTab(tab);
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
      <div className="border-b bg-card px-6 flex gap-0">
        {TABS.map((tab) => (
          <button
            key={tab}
            type="button"
            onClick={() => switchTab(tab)}
            className={`px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
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
          {activeTab === "overview" && (
            <OverviewTab
              secret={secret}
              apiUrl={API_URL}
              timeRange={timeRange}
              onWarningCounts={setWarningCounts}
            />
          )}
          {activeTab === "pipeline" && (
            <PipelineTab secret={secret} apiUrl={API_URL} />
          )}
          {activeTab === "coverage" && (
            <CoverageTab secret={secret} apiUrl={API_URL} />
          )}
          {activeTab === "chats" && (
            <ChatSessionsTab
              secret={secret}
              apiUrl={API_URL}
              timeRange={timeRange}
            />
          )}
        </Suspense>
      </div>
    </div>
  );
}

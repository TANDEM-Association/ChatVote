"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";

import { Badge } from "@components/ui/badge";
import { Button } from "@components/ui/button";
import { Separator } from "@components/ui/separator";
import {
  BarChart3Icon,
  BrainCircuitIcon,
  ChevronDownIcon,
  ChevronRightIcon,
  FlaskConicalIcon,
  Loader2Icon,
  MessageSquareIcon,
} from "lucide-react";

import { FiabiliteBadge, SourceDocBadge, ThemeBadge } from "./metadata-badge";

// ─── Fixed taxonomy types ───

type ThemeStat = {
  theme: string;
  count: number;
  percentage: number;
  by_party: Record<string, number>;
  by_source: Record<string, number>;
  by_fiabilite: Record<string, number>;
  sub_themes: Array<{
    name: string;
    count: number;
    by_party: Record<string, number>;
  }>;
};

type TopicStatsResponse = {
  total_chunks: number;
  classified_chunks: number;
  unclassified_chunks: number;
  themes: ThemeStat[];
  collections: Record<string, { total: number; classified: number }>;
};

// ─── BERTopic types ───

type BERTopicWord = { word: string; weight: number };
type BERTopicMessage = {
  text: string;
  session_id: string;
  chat_title: string;
};
type BERTopicTopic = {
  topic_id: number;
  label: string;
  count: number;
  percentage: number;
  words: BERTopicWord[];
  representative_messages: BERTopicMessage[];
  by_party: Record<string, number>;
};
type BERTopicResponse = {
  status: string;
  message?: string;
  total_messages: number;
  num_topics: number;
  topics: BERTopicTopic[];
};

// ─── Tabs ───

type Tab = "taxonomy" | "bertopic";

export default function TopicInsights() {
  const [tab, setTab] = useState<Tab>("taxonomy");
  const [data, setData] = useState<TopicStatsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // BERTopic state
  const [btData, setBtData] = useState<BERTopicResponse | null>(null);
  const [btLoading, setBtLoading] = useState(false);
  const [btError, setBtError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/experiment/topics")
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  const runBERTopic = useCallback(async () => {
    setBtLoading(true);
    setBtError(null);
    try {
      const r = await fetch("/api/experiment/bertopic");
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const result = await r.json();
      if (result.status === "error") throw new Error(result.message);
      setBtData(result);
    } catch (e) {
      setBtError((e as Error).message);
    } finally {
      setBtLoading(false);
    }
  }, []);

  return (
    <div className="mx-auto flex w-full max-w-7xl flex-col gap-6 p-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <BarChart3Icon className="text-muted-foreground size-6" />
          <div>
            <h1 className="text-2xl font-bold">Topic Insights</h1>
            <p className="text-muted-foreground text-sm">
              Explore themes in the knowledge base and emergent topics from user chats.
            </p>
          </div>
        </div>
        <Link
          href="/experiment"
          className="text-muted-foreground hover:text-foreground flex items-center gap-1 text-sm transition-colors"
        >
          <FlaskConicalIcon className="size-4" />
          Chunk Explorer
        </Link>
      </div>

      {/* Tab bar */}
      <div className="flex gap-1 rounded-lg border p-1">
        <button
          type="button"
          className={`flex items-center gap-2 rounded-md px-4 py-2 text-sm font-medium transition-colors ${
            tab === "taxonomy"
              ? "bg-primary text-primary-foreground"
              : "hover:bg-muted text-muted-foreground"
          }`}
          onClick={() => setTab("taxonomy")}
        >
          <BarChart3Icon className="size-4" />
          Fixed Taxonomy
        </button>
        <button
          type="button"
          className={`flex items-center gap-2 rounded-md px-4 py-2 text-sm font-medium transition-colors ${
            tab === "bertopic"
              ? "bg-primary text-primary-foreground"
              : "hover:bg-muted text-muted-foreground"
          }`}
          onClick={() => setTab("bertopic")}
        >
          <BrainCircuitIcon className="size-4" />
          BERTopic (User Chats)
        </button>
      </div>

      <Separator />

      {tab === "taxonomy" && (
        <TaxonomyView data={data} loading={loading} error={error} />
      )}

      {tab === "bertopic" && (
        <BERTopicView
          data={btData}
          loading={btLoading}
          error={btError}
          onRun={runBERTopic}
        />
      )}
    </div>
  );
}

// ─── Fixed Taxonomy View ───

function TaxonomyView({
  data,
  loading,
  error,
}: {
  data: TopicStatsResponse | null;
  loading: boolean;
  error: string | null;
}) {
  if (loading) {
    return (
      <div className="flex min-h-[30vh] items-center justify-center">
        <Loader2Icon className="text-muted-foreground size-8 animate-spin" />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="flex min-h-[30vh] items-center justify-center">
        <p className="text-destructive">Failed to load topic stats: {error}</p>
      </div>
    );
  }

  const maxCount = data.themes[0]?.count ?? 1;

  return (
    <div className="flex flex-col gap-6">
      {/* Summary stats */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatCard label="Total Chunks" value={data.total_chunks} />
        <StatCard
          label="Classified"
          value={data.classified_chunks}
          sub={`${data.total_chunks ? Math.round((data.classified_chunks / data.total_chunks) * 100) : 0}%`}
        />
        <StatCard label="Unclassified" value={data.unclassified_chunks} />
        <StatCard label="Themes Found" value={data.themes.length} />
      </div>

      {/* Collection breakdown */}
      <div className="flex flex-wrap gap-3">
        {Object.entries(data.collections).map(([name, stats]) => (
          <div
            key={name}
            className="bg-muted/40 flex items-center gap-2 rounded-md border px-3 py-2 text-xs"
          >
            <span className="font-mono font-medium">{name}</span>
            <span className="text-muted-foreground">
              {stats.classified}/{stats.total} classified
            </span>
          </div>
        ))}
      </div>

      <Separator />

      {/* Bar chart */}
      <div>
        <h2 className="mb-3 text-lg font-semibold">Distribution</h2>
        <div className="flex flex-col gap-1.5">
          {data.themes.map((t) => (
            <div key={t.theme} className="flex items-center gap-2">
              <span className="w-40 shrink-0 truncate text-right text-sm">
                {t.theme}
              </span>
              <div className="relative h-7 flex-1 overflow-hidden rounded bg-neutral-100 dark:bg-neutral-800">
                <div
                  className="absolute inset-y-0 left-0 rounded bg-blue-500/80 transition-all dark:bg-blue-400/70"
                  style={{ width: `${(t.count / maxCount) * 100}%` }}
                />
                <span className="relative z-10 flex h-full items-center px-2 text-xs font-medium">
                  {t.count} ({t.percentage}%)
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>

      <Separator />

      {/* Theme cards */}
      <div>
        <h2 className="mb-3 text-lg font-semibold">Theme Details</h2>
        <div className="grid gap-3 sm:grid-cols-2">
          {data.themes.map((t) => (
            <ThemeCard key={t.theme} theme={t} />
          ))}
        </div>
      </div>

      {/* Unclassified */}
      {data.unclassified_chunks > 0 && (
        <>
          <Separator />
          <div className="bg-muted/30 rounded-lg border border-dashed p-4">
            <h3 className="font-semibold">Unclassified Chunks</h3>
            <p className="text-muted-foreground text-sm">
              {data.unclassified_chunks} chunks (
              {data.total_chunks
                ? Math.round(
                    (data.unclassified_chunks / data.total_chunks) * 100,
                  )
                : 0}
              %) have no theme assigned.
            </p>
          </div>
        </>
      )}
    </div>
  );
}

// ─── BERTopic View ───

function BERTopicView({
  data,
  loading,
  error,
  onRun,
}: {
  data: BERTopicResponse | null;
  loading: boolean;
  error: string | null;
  onRun: () => void;
}) {
  if (!data && !loading && !error) {
    return (
      <div className="flex min-h-[30vh] flex-col items-center justify-center gap-4">
        <BrainCircuitIcon className="text-muted-foreground size-12" />
        <div className="text-center">
          <h3 className="text-lg font-semibold">BERTopic Clustering</h3>
          <p className="text-muted-foreground mt-1 max-w-md text-sm">
            Run unsupervised topic modeling on all user chat messages to discover
            emergent themes. This may take a moment.
          </p>
        </div>
        <Button onClick={onRun} size="lg">
          <BrainCircuitIcon className="mr-2 size-4" />
          Run Analysis
        </Button>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex min-h-[30vh] flex-col items-center justify-center gap-3">
        <Loader2Icon className="text-muted-foreground size-8 animate-spin" />
        <p className="text-muted-foreground text-sm">
          Running BERTopic on user messages... This can take 30-60s.
        </p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex min-h-[30vh] flex-col items-center justify-center gap-3">
        <p className="text-destructive">BERTopic analysis failed: {error}</p>
        <Button variant="outline" onClick={onRun}>
          Retry
        </Button>
      </div>
    );
  }

  if (!data) return null;

  if (data.status === "insufficient_data") {
    return (
      <div className="flex min-h-[30vh] flex-col items-center justify-center gap-3">
        <MessageSquareIcon className="text-muted-foreground size-12" />
        <p className="text-muted-foreground text-sm">{data.message}</p>
      </div>
    );
  }

  const maxCount = data.topics[0]?.count ?? 1;

  return (
    <div className="flex flex-col gap-6">
      {/* Summary */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <StatCard label="User Messages" value={data.total_messages} />
        <StatCard label="Topics Discovered" value={data.num_topics} />
        <StatCard
          label="Outlier Messages"
          value={
            data.topics.find((t) => t.topic_id === -1)?.count ??
            0
          }
        />
      </div>

      <div className="flex justify-end">
        <Button variant="outline" size="sm" onClick={onRun} disabled={loading}>
          Re-run Analysis
        </Button>
      </div>

      <Separator />

      {/* Bar chart */}
      <div>
        <h2 className="mb-3 text-lg font-semibold">Topic Distribution</h2>
        <div className="flex flex-col gap-1.5">
          {data.topics.map((t) => (
            <div key={t.topic_id} className="flex items-center gap-2">
              <span className="w-48 shrink-0 truncate text-right text-sm">
                {t.label}
              </span>
              <div className="relative h-7 flex-1 overflow-hidden rounded bg-neutral-100 dark:bg-neutral-800">
                <div
                  className={`absolute inset-y-0 left-0 rounded transition-all ${
                    t.topic_id === -1
                      ? "bg-neutral-400/50 dark:bg-neutral-600/50"
                      : "bg-emerald-500/80 dark:bg-emerald-400/70"
                  }`}
                  style={{ width: `${(t.count / maxCount) * 100}%` }}
                />
                <span className="relative z-10 flex h-full items-center px-2 text-xs font-medium">
                  {t.count} ({t.percentage}%)
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>

      <Separator />

      {/* Topic cards */}
      <div>
        <h2 className="mb-3 text-lg font-semibold">Topic Details</h2>
        <div className="grid gap-3 sm:grid-cols-2">
          {data.topics
            .filter((t) => t.topic_id !== -1)
            .map((t) => (
              <BERTopicCard key={t.topic_id} topic={t} />
            ))}
        </div>
      </div>
    </div>
  );
}

// ─── BERTopic Card ───

function BERTopicCard({ topic }: { topic: BERTopicTopic }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="rounded-lg border transition-colors">
      <button
        type="button"
        className="flex w-full items-center gap-3 p-4 text-left"
        onClick={() => setExpanded(!expanded)}
      >
        {expanded ? (
          <ChevronDownIcon className="text-muted-foreground size-4 shrink-0" />
        ) : (
          <ChevronRightIcon className="text-muted-foreground size-4 shrink-0" />
        )}
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <Badge variant="secondary" className="text-[10px]">
              Topic {topic.topic_id}
            </Badge>
            <span className="text-muted-foreground text-xs">
              {topic.count} messages · {topic.percentage}%
            </span>
          </div>
          {/* Top words preview */}
          <p className="text-muted-foreground mt-1 truncate text-xs">
            {topic.words
              .slice(0, 5)
              .map((w) => w.word)
              .join(", ")}
          </p>
        </div>
      </button>

      {expanded && (
        <div className="flex flex-col gap-3 border-t px-4 pb-4 pt-3">
          {/* Keywords with weights */}
          <div>
            <p className="text-muted-foreground mb-1.5 text-[10px] font-semibold uppercase tracking-wider">
              Keywords
            </p>
            <div className="flex flex-wrap gap-1">
              {topic.words.map((w) => (
                <Badge
                  key={w.word}
                  variant="outline"
                  className="text-[10px] font-mono"
                >
                  {w.word}{" "}
                  <span className="text-muted-foreground ml-0.5">
                    {w.weight.toFixed(3)}
                  </span>
                </Badge>
              ))}
            </div>
          </div>

          {/* Representative messages */}
          {topic.representative_messages.length > 0 && (
            <div>
              <p className="text-muted-foreground mb-1.5 text-[10px] font-semibold uppercase tracking-wider">
                Representative Messages
              </p>
              <div className="flex flex-col gap-1.5">
                {topic.representative_messages.map((msg, i) => (
                  <div
                    key={i}
                    className="bg-muted/30 rounded border px-2.5 py-2 text-xs"
                  >
                    <p className="leading-relaxed">{msg.text}</p>
                    {msg.chat_title && (
                      <p className="text-muted-foreground mt-1 text-[10px]">
                        Chat: {msg.chat_title}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Party distribution */}
          {Object.keys(topic.by_party).length > 0 && (
            <div>
              <p className="text-muted-foreground mb-1.5 text-[10px] font-semibold uppercase tracking-wider">
                Parties Discussed
              </p>
              <div className="flex flex-wrap gap-1.5">
                {Object.entries(topic.by_party)
                  .sort(([, a], [, b]) => b - a)
                  .map(([party, count]) => (
                    <Badge
                      key={party}
                      variant="outline"
                      className="text-[10px]"
                    >
                      {party} ({count})
                    </Badge>
                  ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Shared components ───

function StatCard({
  label,
  value,
  sub,
}: {
  label: string;
  value: number;
  sub?: string;
}) {
  return (
    <div className="bg-muted/30 rounded-lg border p-3">
      <p className="text-muted-foreground text-xs">{label}</p>
      <p className="text-2xl font-bold tabular-nums">
        {value.toLocaleString()}
        {sub && (
          <span className="text-muted-foreground ml-1 text-sm font-normal">
            {sub}
          </span>
        )}
      </p>
    </div>
  );
}

function ThemeCard({ theme }: { theme: ThemeStat }) {
  const [expanded, setExpanded] = useState(false);
  const partyEntries = Object.entries(theme.by_party).sort(
    ([, a], [, b]) => b - a,
  );
  const maxPartyCount = partyEntries[0]?.[1] ?? 1;

  return (
    <div className="rounded-lg border transition-colors">
      <button
        type="button"
        className="flex w-full items-center gap-3 p-4 text-left"
        onClick={() => setExpanded(!expanded)}
      >
        {expanded ? (
          <ChevronDownIcon className="text-muted-foreground size-4 shrink-0" />
        ) : (
          <ChevronRightIcon className="text-muted-foreground size-4 shrink-0" />
        )}
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <ThemeBadge theme={theme.theme} />
            <span className="text-muted-foreground text-xs">
              {theme.count} chunks · {theme.percentage}%
            </span>
          </div>
        </div>
      </button>

      {expanded && (
        <div className="flex flex-col gap-3 border-t px-4 pb-4 pt-3">
          {/* Party breakdown */}
          {partyEntries.length > 0 && (
            <div>
              <p className="text-muted-foreground mb-1.5 text-[10px] font-semibold uppercase tracking-wider">
                By Party / Namespace
              </p>
              <div className="flex flex-col gap-1">
                {partyEntries.map(([party, count]) => (
                  <div key={party} className="flex items-center gap-2 text-xs">
                    <span className="w-28 shrink-0 truncate text-right">
                      {party}
                    </span>
                    <div className="relative h-4 flex-1 overflow-hidden rounded bg-neutral-100 dark:bg-neutral-800">
                      <div
                        className="absolute inset-y-0 left-0 rounded bg-violet-400/70 dark:bg-violet-500/60"
                        style={{
                          width: `${(count / maxPartyCount) * 100}%`,
                        }}
                      />
                      <span className="relative z-10 flex h-full items-center px-1.5 text-[10px]">
                        {count}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Source type breakdown */}
          {Object.keys(theme.by_source).length > 0 && (
            <div>
              <p className="text-muted-foreground mb-1.5 text-[10px] font-semibold uppercase tracking-wider">
                By Source Type
              </p>
              <div className="flex flex-wrap gap-1.5">
                {Object.entries(theme.by_source)
                  .sort(([, a], [, b]) => b - a)
                  .map(([src, count]) => (
                    <div key={src} className="flex items-center gap-1">
                      <SourceDocBadge sourceDoc={src} />
                      <span className="text-muted-foreground text-[10px]">
                        ({count})
                      </span>
                    </div>
                  ))}
              </div>
            </div>
          )}

          {/* Fiabilite breakdown */}
          {Object.keys(theme.by_fiabilite).length > 0 && (
            <div>
              <p className="text-muted-foreground mb-1.5 text-[10px] font-semibold uppercase tracking-wider">
                By Fiabilité
              </p>
              <div className="flex flex-wrap gap-1.5">
                {Object.entries(theme.by_fiabilite)
                  .sort(([a], [b]) => Number(a) - Number(b))
                  .map(([level, count]) => (
                    <div key={level} className="flex items-center gap-1">
                      <FiabiliteBadge level={Number(level)} />
                      <span className="text-muted-foreground text-[10px]">
                        ({count})
                      </span>
                    </div>
                  ))}
              </div>
            </div>
          )}

          {/* Sub-themes */}
          {theme.sub_themes.length > 0 && (
            <div>
              <p className="text-muted-foreground mb-1.5 text-[10px] font-semibold uppercase tracking-wider">
                Sub-themes
              </p>
              <div className="flex flex-col gap-1.5">
                {theme.sub_themes.map((st) => {
                  const maxSt = theme.sub_themes[0]?.count ?? 1;
                  const partyPairs = Object.entries(st.by_party).sort(([, a], [, b]) => b - a);
                  return (
                    <div key={st.name} className="flex flex-col gap-0.5">
                      <div className="flex items-center gap-2">
                        <span className="w-36 shrink-0 truncate text-right text-xs">
                          {st.name}
                        </span>
                        <div className="relative h-4 flex-1 overflow-hidden rounded bg-neutral-100 dark:bg-neutral-800">
                          <div
                            className="absolute inset-y-0 left-0 rounded bg-indigo-400/70 dark:bg-indigo-500/60"
                            style={{ width: `${(st.count / maxSt) * 100}%` }}
                          />
                          <span className="relative z-10 flex h-full items-center px-1.5 text-[10px] font-medium">
                            {st.count}
                          </span>
                        </div>
                      </div>
                      {partyPairs.length > 0 && (
                        <div className="ml-[9.5rem] flex flex-wrap gap-1">
                          {partyPairs.map(([party, count]) => (
                            <span
                              key={party}
                              className="inline-flex items-center gap-0.5 rounded border px-1 py-0 text-[9px] text-muted-foreground"
                            >
                              {party} <span className="font-semibold">{count}</span>
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

"use client";

import React, { useState } from "react";

import {
  FiabiliteBadge,
  SourceDocBadge,
  ThemeBadge,
} from "@components/experiment/metadata-badge";
import { useChatStore } from "@components/providers/chat-store-provider";
import { Badge } from "@components/ui/badge";
import { Button } from "@components/ui/button";
import { type DebugLlmCallPayload } from "@lib/stores/chat-store.types";
import { type Source } from "@lib/stores/chat-store.types";
import { cn } from "@lib/utils";
import {
  BugIcon,
  ChevronDownIcon,
  ChevronRightIcon,
  XIcon,
} from "lucide-react";

export default function DevMetadataSidebar() {
  // Must check before any hooks to avoid conditional hook calls
  if (process.env.NODE_ENV !== "development") return null;

  return <DevMetadataSidebarInner />;
}

function DevMetadataSidebarInner() {
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState<"sources" | "llm">("llm");

  const currentStreaming = useChatStore((s) => s.currentStreamingMessages);
  const messages = useChatStore((s) => s.messages);
  const debugLlmCalls = useChatStore((s) => s.debugLlmCalls);
  const clearDebugLlmCalls = useChatStore((s) => s.clearDebugLlmCalls);

  // Collect all sources from streaming or last assistant message
  const allSources: { partyId: string; sources: Source[] }[] = [];

  if (currentStreaming?.messages) {
    for (const [partyId, msg] of Object.entries(currentStreaming.messages)) {
      if (msg.sources?.length) {
        allSources.push({ partyId, sources: msg.sources });
      }
    }
  }

  if (allSources.length === 0 && messages.length > 0) {
    const lastGroup = [...messages]
      .reverse()
      .find((g) => g.role === "assistant");
    if (lastGroup) {
      for (const msg of lastGroup.messages) {
        if (msg.sources?.length && msg.party_id) {
          allSources.push({ partyId: msg.party_id, sources: msg.sources });
        }
      }
    }
  }

  return (
    <>
      {/* Toggle button */}
      <Button
        variant="ghost"
        size="icon"
        className="fixed right-3 bottom-3 z-50 size-8 rounded-full opacity-60 hover:opacity-100"
        onClick={() => setOpen(!open)}
        title="Dev: Toggle metadata sidebar"
      >
        {open ? <XIcon className="size-4" /> : <BugIcon className="size-4" />}
      </Button>

      {/* Sidebar panel */}
      {open && (
        <div className="bg-background fixed top-0 right-0 z-40 flex h-full w-80 flex-col border-l shadow-lg">
          <div className="flex items-center justify-between border-b p-3">
            <div className="flex items-center gap-2">
              <BugIcon className="text-muted-foreground size-4" />
              <h2 className="text-sm font-semibold">Dev Metadata</h2>
            </div>
            <Badge variant="outline" className="text-[10px]">
              DEV
            </Badge>
          </div>

          {/* Tab bar */}
          <div className="flex gap-1 border-b px-3 py-1">
            <button
              className={cn(
                "rounded px-2 py-0.5 text-[11px] font-medium transition-colors",
                tab === "llm" ? "bg-muted" : "hover:bg-muted/50",
              )}
              onClick={() => setTab("llm")}
            >
              LLM Calls
              {debugLlmCalls.length > 0 && (
                <Badge
                  variant="secondary"
                  className="ml-1 px-1 py-0 text-[9px]"
                >
                  {debugLlmCalls.length}
                </Badge>
              )}
            </button>
            <button
              className={cn(
                "rounded px-2 py-0.5 text-[11px] font-medium transition-colors",
                tab === "sources" ? "bg-muted" : "hover:bg-muted/50",
              )}
              onClick={() => setTab("sources")}
            >
              Sources
            </button>
          </div>

          <div className="flex-1 overflow-y-auto p-3">
            {tab === "llm" && (
              <div className="flex flex-col gap-1.5">
                {debugLlmCalls.length === 0 ? (
                  <p className="text-muted-foreground py-8 text-center text-sm">
                    No LLM calls yet. Ask a question to see tool calls.
                  </p>
                ) : (
                  <>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-6 self-end text-[10px]"
                      onClick={() => clearDebugLlmCalls()}
                    >
                      Clear
                    </Button>
                    {debugLlmCalls.map((call, i) => (
                      <DebugLlmCallCard key={i} call={call} />
                    ))}
                  </>
                )}
              </div>
            )}

            {tab === "sources" && (
              <>
                {allSources.length === 0 ? (
                  <p className="text-muted-foreground py-8 text-center text-sm">
                    No sources available. Ask a question to see metadata.
                  </p>
                ) : (
                  <div className="flex flex-col gap-3">
                    {allSources.map(({ partyId, sources }) => (
                      <PartySourceGroup
                        key={partyId}
                        partyId={partyId}
                        sources={sources}
                      />
                    ))}
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      )}
    </>
  );
}

const stageConfig: Record<string, { label: string; color: string }> = {
  question_routing: {
    label: "Question Routing",
    color: "bg-blue-500/20 text-blue-700 dark:text-blue-300",
  },
  rag_query_improvement: {
    label: "RAG Query Improve",
    color: "bg-purple-500/20 text-purple-700 dark:text-purple-300",
  },
  rag_search_rerank: {
    label: "RAG Search",
    color: "bg-green-500/20 text-green-700 dark:text-green-300",
  },
  rag_vector_search: {
    label: "Vector Search",
    color: "bg-emerald-500/20 text-emerald-700 dark:text-emerald-300",
  },
  rag_vector_results: {
    label: "Vector Results",
    color: "bg-teal-500/20 text-teal-700 dark:text-teal-300",
  },
  rag_rerank_results: {
    label: "Rerank Results",
    color: "bg-lime-500/20 text-lime-700 dark:text-lime-300",
  },
  response_generation_start: {
    label: "Response Gen",
    color: "bg-orange-500/20 text-orange-700 dark:text-orange-300",
  },
  title_and_quick_replies: {
    label: "Title & Replies",
    color: "bg-cyan-500/20 text-cyan-700 dark:text-cyan-300",
  },
  chat_summary: {
    label: "Chat Summary",
    color: "bg-yellow-500/20 text-yellow-700 dark:text-yellow-300",
  },
  pro_con_perspective: {
    label: "Pro/Con",
    color: "bg-pink-500/20 text-pink-700 dark:text-pink-300",
  },
  voting_behavior_rag: {
    label: "Voting RAG",
    color: "bg-red-500/20 text-red-700 dark:text-red-300",
  },
};

function DebugLlmCallCard({ call }: { call: DebugLlmCallPayload }) {
  const [expanded, setExpanded] = useState(false);
  const time = new Date(call.timestamp * 1000).toLocaleTimeString();

  const config = stageConfig[call.stage] ?? {
    label: call.stage,
    color: "bg-gray-500/20 text-gray-700 dark:text-gray-300",
  };

  const details = Object.entries(call).filter(
    ([k]) => !["session_id", "stage", "timestamp"].includes(k),
  );

  return (
    <div
      className="hover:bg-muted/30 cursor-pointer rounded border p-2 text-xs transition-colors"
      onClick={() => setExpanded(!expanded)}
    >
      <div className="flex items-center gap-1.5">
        <span
          className={cn(
            "rounded px-1.5 py-0.5 text-[10px] font-medium",
            config.color,
          )}
        >
          {config.label}
        </span>
        <span className="text-muted-foreground ml-auto text-[10px]">
          {time}
        </span>
      </div>
      {expanded && details.length > 0 && (
        <div className="bg-muted/20 mt-1.5 rounded border p-1.5">
          {details.map(([key, value]) => (
            <div key={key} className="flex gap-1 text-[10px]">
              <span className="text-muted-foreground shrink-0 font-mono">
                {key}:
              </span>
              <span className="truncate font-mono">
                {typeof value === "object"
                  ? JSON.stringify(value)
                  : String(value)}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function PartySourceGroup({
  partyId,
  sources,
}: {
  partyId: string;
  sources: Source[];
}) {
  const [expanded, setExpanded] = useState(true);

  return (
    <div className="rounded-md border">
      <button
        type="button"
        className="flex w-full items-center gap-2 p-2 text-left text-sm font-medium"
        onClick={() => setExpanded(!expanded)}
      >
        {expanded ? (
          <ChevronDownIcon className="size-3.5" />
        ) : (
          <ChevronRightIcon className="size-3.5" />
        )}
        <span className="font-mono text-xs">{partyId}</span>
        <Badge variant="secondary" className="ml-auto text-[10px]">
          {sources.length}
        </Badge>
      </button>

      {expanded && (
        <div className="flex flex-col gap-1 border-t px-2 py-1">
          {sources.map((source, i) => (
            <SourceMetadataCard key={i} source={source} index={i} />
          ))}
        </div>
      )}
    </div>
  );
}

function SourceMetadataCard({
  source,
  index,
}: {
  source: Source;
  index: number;
}) {
  const [showAll, setShowAll] = useState(false);

  return (
    <div
      className={cn(
        "rounded border p-2 text-xs",
        "hover:bg-muted/30 cursor-pointer transition-colors",
      )}
      onClick={() => setShowAll(!showAll)}
    >
      {/* Badges row */}
      <div className="mb-1 flex flex-wrap items-center gap-1">
        <span className="bg-muted inline-flex size-4 items-center justify-center rounded-full text-[9px] font-bold">
          {index}
        </span>
        <FiabiliteBadge level={source.fiabilite} />
        <ThemeBadge theme={source.theme} />
        <SourceDocBadge sourceDoc={source.source_document} />
      </div>

      {/* Preview */}
      <p className="text-muted-foreground line-clamp-2 text-[11px] leading-tight">
        {source.content_preview}
      </p>

      {/* Full metadata */}
      {showAll && (
        <div className="bg-muted/20 mt-1 rounded border p-1.5">
          <MetadataRow label="source" value={source.source} />
          <MetadataRow label="page" value={source.page} />
          <MetadataRow label="url" value={source.url} />
          <MetadataRow label="party_id" value={source.party_id} />
          <MetadataRow label="fiabilite" value={source.fiabilite} />
          <MetadataRow label="theme" value={source.theme} />
          <MetadataRow label="sub_theme" value={source.sub_theme} />
          <MetadataRow label="source_type" value={source.source_type} />
          <MetadataRow label="candidate_name" value={source.candidate_name} />
          <MetadataRow
            label="municipality_name"
            value={source.municipality_name}
          />
          <MetadataRow
            label="publish_date"
            value={source.document_publish_date}
          />
        </div>
      )}
    </div>
  );
}

function MetadataRow({
  label,
  value,
}: {
  label: string;
  value: string | number | undefined;
}) {
  if (value === undefined || value === null) return null;
  return (
    <div className="flex gap-1 text-[10px]">
      <span className="text-muted-foreground shrink-0 font-mono">{label}:</span>
      <span className="truncate font-mono">{String(value)}</span>
    </div>
  );
}

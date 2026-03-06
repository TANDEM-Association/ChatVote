"use client";

import React, { useState } from "react";

import { Badge } from "@components/ui/badge";
import { Button } from "@components/ui/button";
import {
  FiabiliteBadge,
  ThemeBadge,
  SourceDocBadge,
} from "@components/experiment/metadata-badge";
import { useChatStore } from "@components/providers/chat-store-provider";
import { type Source } from "@lib/stores/chat-store.types";
import { BugIcon, XIcon, ChevronDownIcon, ChevronRightIcon } from "lucide-react";
import { cn } from "@lib/utils";

export default function DevMetadataSidebar() {
  const [open, setOpen] = useState(false);

  const currentStreaming = useChatStore((s) => s.currentStreamingMessages);
  const messages = useChatStore((s) => s.messages);

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
    const lastGroup = [...messages].reverse().find((g) => g.role === "assistant");
    if (lastGroup) {
      for (const msg of lastGroup.messages) {
        if (msg.sources?.length && msg.party_id) {
          allSources.push({ partyId: msg.party_id, sources: msg.sources });
        }
      }
    }
  }

  if (process.env.NODE_ENV !== "development") return null;

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
              <h2 className="text-sm font-semibold">Source Metadata</h2>
            </div>
            <Badge variant="outline" className="text-[10px]">
              DEV
            </Badge>
          </div>

          <div className="flex-1 overflow-y-auto p-3">
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
          </div>
        </div>
      )}
    </>
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
          <MetadataRow label="publish_date" value={source.document_publish_date} />
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

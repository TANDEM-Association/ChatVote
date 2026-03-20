"use client";

import { useMemo } from "react";

import { type Source } from "@lib/stores/chat-store.types";
import { cn } from "@lib/utils";
import { getToolName, isToolUIPart, type UIMessage } from "ai";

import ChatMarkdown from "../chat-markdown";

import AiSdkSourceChip from "./ai-sdk-source-chip";
import AiSdkToolResult from "./ai-sdk-tool-result";

type Props = {
  message: UIMessage;
  onSendMessage?: (text: string) => void;
};

/**
 * Collect all sources from search tool results in this message for inline [1],[2] badges.
 *
 * Sources are accumulated in part-traversal order (same order the LLM sees them).
 * The LLM uses 1-based citations [1], [2], etc. The frontend resolves them via
 * `sources[number - 1]` (see chat-markdown.tsx).
 *
 * For multi-tool calls (e.g. searchCandidateWebsite × 3), sources from all tools
 * are concatenated sequentially. The prompt instructs the LLM to number citations
 * globally across all tool results.
 */
function collectSources(parts: UIMessage["parts"]): Source[] {
  const sources: Source[] = [];
  for (const part of parts) {
    if (
      isToolUIPart(part) &&
      (part as { state?: string }).state === "output-available" &&
      (getToolName(part) === "searchPartyManifesto" ||
        getToolName(part) === "searchCandidateWebsite" ||
        getToolName(part) === "searchAllCandidates" ||
        getToolName(part) === "searchVotingRecords" ||
        getToolName(part) === "searchParliamentaryQuestions")
    ) {
      const result = (part as { output?: unknown }).output as {
        results?: Array<{
          id: number;
          content: string;
          source: string;
          url: string;
          page: number | string;
          party_id: string;
          candidate_name?: string;
        }>;
      };
      if (result?.results) {
        for (const r of result.results) {
          sources.push({
            source: r.source,
            content_preview: r.content.slice(0, 200),
            page:
              typeof r.page === "number"
                ? r.page
                : parseInt(String(r.page)) || 0,
            url: r.url,
            source_document: r.source,
            document_publish_date: "",
            party_id: r.party_id,
          });
        }
      }
    }
  }

  if (sources.length > 0 && process.env.NODE_ENV === "development") {
    console.log(
      `[collectSources] ${sources.length} sources collected:`,
      sources.map((s, i) => `[${i + 1}] ${s.source} (${s.party_id}) → ${s.url?.slice(0, 60)}`),
    );
  }

  return sources;
}

export default function AiSdkMessage({ message, onSendMessage }: Props) {
  const isUser = message.role === "user";

  // Collect sources from tool results for inline reference badges
  const sources = useMemo(() => collectSources(message.parts), [message.parts]);

  // In multi-step tool flows, the AI SDK creates a text part and suggestFollowUps
  // tool call per step. Only render the last of each to avoid duplicate content.
  const { lastTextIndex, lastSuggestFollowUpsIndex } = useMemo(() => {
    if (isUser) return { lastTextIndex: -1, lastSuggestFollowUpsIndex: -1 };
    let lastText = -1;
    let lastSuggest = -1;
    for (let i = 0; i < message.parts.length; i++) {
      const p = message.parts[i];
      if (p.type === "text") lastText = i;
      if (isToolUIPart(p) && getToolName(p) === "suggestFollowUps") lastSuggest = i;
    }
    return { lastTextIndex: lastText, lastSuggestFollowUpsIndex: lastSuggest };
  }, [isUser, message.parts]);

  return (
    <article
      className={cn("flex gap-3", isUser ? "justify-end" : "justify-start")}
    >
      <div
        className={cn(
          "max-w-[85%] rounded-2xl px-4 py-3",
          isUser
            ? "bg-primary text-primary-foreground"
            : "border border-white/10 bg-white/5 backdrop-blur-sm",
        )}
      >
        {message.parts.map((part, index) => {
          switch (part.type) {
            case "text":
              // Skip intermediate text parts for assistant (multi-step dedup)
              if (!isUser && index !== lastTextIndex) return null;
              return (
                <div key={index}>
                  <ChatMarkdown
                    message={{ content: part.text, sources }}
                    oneBasedCitations
                  />
                </div>
              );
            case "source-url":
              return (
                <AiSdkSourceChip
                  key={index}
                  source={{
                    url: part.url,
                    title: part.title,
                    id: part.sourceId,
                  }}
                />
              );
            case "source-document":
              return (
                <AiSdkSourceChip
                  key={index}
                  source={{ title: part.title, id: part.sourceId }}
                />
              );
            default:
              if (isToolUIPart(part)) {
                // Skip intermediate suggestFollowUps (multi-step dedup)
                if (
                  !isUser &&
                  getToolName(part) === "suggestFollowUps" &&
                  index !== lastSuggestFollowUpsIndex
                ) return null;
                return (
                  <AiSdkToolResult
                    key={index}
                    part={part}
                    onSendMessage={onSendMessage}
                  />
                );
              }
              return null;
          }
        })}
      </div>
    </article>
  );
}

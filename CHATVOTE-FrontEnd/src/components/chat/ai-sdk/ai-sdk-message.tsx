'use client';

import { type UIMessage, isToolUIPart, getToolName } from 'ai';
import { useMemo } from 'react';
import { cn } from '@lib/utils';
import { type Source } from '@lib/stores/chat-store.types';
import ChatMarkdown from '../chat-markdown';
import AiSdkSourceChip from './ai-sdk-source-chip';
import AiSdkToolResult from './ai-sdk-tool-result';

type Props = {
  message: UIMessage;
  onSendMessage?: (text: string) => void;
};

/** Collect all sources from search tool results in this message for inline [0],[1] badges */
function collectSources(parts: UIMessage['parts']): Source[] {
  const sources: Source[] = [];
  for (const part of parts) {
    if (
      isToolUIPart(part) &&
      (part as any).state === 'output-available' &&
      (getToolName(part) === 'searchPartyManifesto' ||
        getToolName(part) === 'searchCandidateWebsite' ||
        getToolName(part) === 'searchAllCandidates')
    ) {
      const result = (part as any).output as {
        results?: Array<{
          id: number;
          content: string;
          source: string;
          url: string;
          page: number | string;
          party_id: string;
        }>;
      };
      if (result?.results) {
        for (const r of result.results) {
          sources.push({
            source: r.source,
            content_preview: r.content.slice(0, 200),
            page: typeof r.page === 'number' ? r.page : parseInt(String(r.page)) || 0,
            url: r.url,
            source_document: r.source,
            document_publish_date: '',
            party_id: r.party_id,
          });
        }
      }
    }
  }
  return sources;
}

export default function AiSdkMessage({ message, onSendMessage }: Props) {
  const isUser = message.role === 'user';

  // Collect sources from tool results for inline reference badges
  const sources = useMemo(() => collectSources(message.parts), [message.parts]);

  return (
    <article className={cn('flex gap-3', isUser ? 'justify-end' : 'justify-start')}>
      <div
        className={cn(
          'max-w-[85%] rounded-2xl px-4 py-3',
          isUser ? 'bg-primary text-primary-foreground' : 'bg-muted',
        )}
      >
{message.parts.map((part, index) => {
          switch (part.type) {
            case 'text':
              return (
                <div key={index}>
                  <ChatMarkdown message={{ content: part.text, sources }} />
                </div>
              );
            case 'source-url':
              return (
                <AiSdkSourceChip
                  key={index}
                  source={{ url: part.url, title: part.title, id: part.sourceId }}
                />
              );
            case 'source-document':
              return (
                <AiSdkSourceChip
                  key={index}
                  source={{ title: part.title, id: part.sourceId }}
                />
              );
            default:
              if (isToolUIPart(part)) {
                return <AiSdkToolResult key={index} part={part} onSendMessage={onSendMessage} />;
              }
              return null;
          }
        })}
      </div>
    </article>
  );
}

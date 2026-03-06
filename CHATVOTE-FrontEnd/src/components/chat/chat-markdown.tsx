"use client";

import { Markdown } from "@components/markdown";
import { type Source } from "@lib/stores/chat-store.types";
import { buildPdfUrl, unescapeString } from "@lib/utils";

type Props = {
  message: {
    content?: string;
    sources?: Source[];
  };
};

function ChatMarkdown({ message }: Props) {
  const onReferenceClick = (number: number) => {
    if (!message.sources) {
      return;
    }

    if (number < 0 || number >= message.sources.length) {
      return;
    }

    const source = message.sources[number];
    if (!source?.url) return;

    const isPdfLink = source.url.includes(".pdf");

    if (isPdfLink && window) {
      const url = buildPdfUrl(source);
      if (url) return window.open(url.toString(), "_blank");
    }

    window.open(source.url, "_blank");
  };

  const getReferenceTooltip = (number: number) => {
    if (!message.sources) {
      return null;
    }

    if (number < 0 || number >= message.sources.length) {
      return null;
    }

    const source = message.sources[number];
    if (!source) {
      return null;
    }

    return `${source.source} - Page: ${source.page}`;
  };

  const getReferenceName = (number: number) => {
    if (message.sources === undefined) {
      return null;
    }

    if (number < 0 || number >= message.sources.length) {
      return null;
    }

    const source = message.sources[number];
    if (!source) {
      return null;
    }

    return `${number + 1}`;
  };

  const normalizedContent = unescapeString(message.content ?? "")
    // Remove malformed reference patterns like [, 123] or [   ,  123]
    .replace(/\[\s*,\s*\d+\s*\]/g, "")
    // Remove redundant "Références" section (sources are shown via Sources button)
    .replace(/#{1,6}\s*Références\s*\n[\s\S]*?(?=#{1,6}\s|\s*$)/, "");

  return (
    <Markdown
      onReferenceClick={onReferenceClick}
      getReferenceTooltip={getReferenceTooltip}
      getReferenceName={getReferenceName}
    >
      {normalizedContent}
    </Markdown>
  );
}

export default ChatMarkdown;

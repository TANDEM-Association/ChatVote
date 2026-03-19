"use client";

import { Markdown } from "@components/markdown";
import { type Source } from "@lib/stores/chat-store.types";
import { buildPdfUrl, unescapeString } from "@lib/utils";

type Props = {
  message: {
    content?: string;
    sources?: Source[];
  };
  /**
   * When true, LLM citations are 1-based ([1], [2], …) and need -1 to map to
   * the 0-based sources array. Used by the AI SDK path where tool results have
   * `id: idx + 1`.
   *
   * When false (default), citations are 0-based ([0], [1], …) matching the
   * Socket.IO backend convention.
   */
  oneBasedCitations?: boolean;
};

function ChatMarkdown({ message, oneBasedCitations = false }: Props) {
  /** Convert the citation number the LLM wrote to a 0-based array index. */
  const toIndex = (number: number) =>
    oneBasedCitations ? number - 1 : number;

  const onReferenceClick = (number: number) => {
    if (!message.sources) {
      return;
    }

    const index = toIndex(number);

    if (index < 0 || index >= message.sources.length) {
      return;
    }

    const source = message.sources[index];
    if (!source) return;

    if (process.env.NODE_ENV === "development") {
      console.log(
        `[source-click] Citation [${number}] → index ${index} → source:`,
        source.source,
        `party: ${source.party_id}`,
        `url: ${source.url?.slice(0, 80)}`,
      );
    }

    const url = source.url;
    // Only open real HTTP URLs — skip .md filenames or empty values
    if (!url || !url.startsWith("http")) return;

    // Detect PDF by URL or source document name
    const isPdf =
      url.includes(".pdf") ||
      source.source?.toLowerCase().endsWith(".pdf") ||
      source.source_document?.toLowerCase().endsWith(".pdf");

    if (isPdf) {
      const pdfUrl = buildPdfUrl(source);
      if (pdfUrl) return window.open(pdfUrl.toString(), "_blank");
    }

    window.open(url, "_blank");
  };

  const getReferenceTooltip = (number: number) => {
    if (!message.sources) {
      return null;
    }

    const index = toIndex(number);

    if (index < 0 || index >= message.sources.length) {
      return null;
    }

    const source = message.sources[index];
    if (!source) {
      return null;
    }

    return `${source.source} - Page: ${source.page}`;
  };

  const getReferenceName = (number: number) => {
    if (message.sources === undefined) {
      return null;
    }

    const index = toIndex(number);

    if (index < 0 || index >= message.sources.length) {
      return null;
    }

    const source = message.sources[index];
    if (!source) {
      return null;
    }

    // Display the user-facing number (1-based for readability)
    return `${oneBasedCitations ? number : number + 1}`;
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

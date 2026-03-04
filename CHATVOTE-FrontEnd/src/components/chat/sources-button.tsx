"use client";

import React, { useMemo, useState } from "react";

import { Button } from "@components/ui/button";
import { Modal } from "@components/ui/modal";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@components/ui/tooltip";
import { type Source } from "@lib/stores/chat-store.types";
import { buildPdfUrl, cn, prettyDate } from "@lib/utils";
import { BookMarkedIcon } from "lucide-react";
import { useTranslations } from "next-intl";

import { ChatMessageIcon } from "./chat-message-icon";

type Props = {
  sources: Source[];
  messageContent: string;
};

type SourceWithIndex = Source & { index: number };

const SourcesButton = ({ sources, messageContent }: Props) => {
  const t = useTranslations("chat.sources");
  const tCommon = useTranslations("common");
  const [isOpen, setIsOpen] = useState(false);

  const buildSourceKey = (source: Source, index: number) =>
    `${source.source}-${source.page}-${index}`;

  const [sourcesReferenced, sourcesNotReferenced] = useMemo(() => {
    const regex = /\[(\d+(?:\s*,\s*\d+)*)\]/g;
    const matches = messageContent.match(regex);

    const numbers = matches?.flatMap((match) => {
      const numbers = match.match(/^\[(\d+(?:\s*,\s*\d+)*)\]$/);

      if (!numbers) {
        return [];
      }
      const numbersArray = numbers[1].split(",");
      return numbersArray.map((number) => Number.parseInt(number));
    });

    const uniqueNumbers = [...new Set(numbers)];

    const sourcesReferenced = uniqueNumbers.map((number) => ({
      ...sources[number],
      index: number,
    }));

    const notReferencedNumbers = sources
      .map((_, index) => index)
      .filter((number) => !uniqueNumbers.includes(number));

    const sourcesNotReferenced = notReferencedNumbers.map((number) => ({
      ...sources[number],
      index: number,
    }));

    return [
      sourcesReferenced.sort((a, b) => a.index - b.index),
      sourcesNotReferenced.sort((a, b) => a.index - b.index),
    ];
  }, [messageContent, sources]);

  if (sourcesReferenced.length === 0 && sourcesNotReferenced.length === 0) {
    return null;
  }

  return (
    <React.Fragment>
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            variant="outline"
            className="h-8 px-2 text-xs group-data-has-message-background:bg-zinc-100 group-data-has-message-background:hover:bg-zinc-200 group-data-has-message-background:dark:bg-zinc-900 group-data-has-message-background:dark:hover:bg-zinc-800"
            onClick={() => setIsOpen(true)}
          >
            <BookMarkedIcon />
            {tCommon("sources")}
          </Button>
        </TooltipTrigger>
        <TooltipContent>{tCommon("sources")}</TooltipContent>
      </Tooltip>

      <Modal
        isOpen={isOpen}
        onClose={() => {
          setIsOpen(false);
        }}
        className="flex max-h-[85dvh] w-full max-w-lg flex-col p-6"
      >
        <div className="mb-4">
          <h2 className="text-lg font-semibold">{t("title")}</h2>
          <p className="text-muted-foreground text-sm">{t("description")}</p>
        </div>

        <div className={cn("flex grow flex-col overflow-y-auto")}>
          {sourcesReferenced.length > 0 ? (
            <p className="text-sm font-bold">{t("referencedInText")}</p>
          ) : null}
          {sourcesReferenced.map((source, index) => {
            return (
              <SourceItem key={buildSourceKey(source, index)} source={source} />
            );
          })}
          {sourcesNotReferenced.length > 0 ? (
            <p
              className={cn(
                "text-sm font-bold",
                sourcesReferenced.length > 0 && "mt-4",
              )}
            >
              {t("additionallyAnalyzed")}
            </p>
          ) : null}
          {sourcesNotReferenced.map((source, index) => {
            return (
              <SourceItem key={buildSourceKey(source, index)} source={source} />
            );
          })}
        </div>
      </Modal>
    </React.Fragment>
  );
};

const SourceItem = ({ source }: { source: SourceWithIndex }) => {
  const t = useTranslations("chat.sources");
  const tCommon = useTranslations("common");

  const onSourceClick = (source: Source) => {
    const url = buildPdfUrl(source);
    if (!url) return;
    return window.open(url.toString(), "_blank");
  };

  return (
    <button
      className="hover:bg-muted/50 flex cursor-pointer flex-row items-center justify-between gap-2 rounded-md p-2 transition-colors"
      onClick={() => onSourceClick(source)}
      type="button"
    >
      <div className="flex grow flex-col justify-start overflow-hidden">
        <div className="flex grow flex-row items-center gap-2">
          <div className="bg-muted inline-flex size-5 items-center justify-center rounded-full text-xs">
            {source.index + 1}
          </div>{" "}
          <p className="grow truncate text-start">{source.content_preview}</p>
        </div>
        {source.document_publish_date && (
          <span className="text-muted-foreground text-left text-xs">
            {t("publishedOn")}{" "}
            <span className="font-bold">
              {prettyDate(source.document_publish_date)}
            </span>
          </span>
        )}
      </div>
      <p className="bg-muted text-muted-foreground flex h-8 items-center justify-center rounded-md px-2 text-xs whitespace-nowrap">
        {tCommon("page", { page: source.page })}
      </p>
      {source.party_id !== undefined ? <ChatMessageIcon /> : null}
    </button>
  );
};

export default SourcesButton;

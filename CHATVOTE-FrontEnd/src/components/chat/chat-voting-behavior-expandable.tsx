"use client";

import { useEffect, useRef, useState } from "react";

import { useChatStore } from "@components/providers/chat-store-provider";
import { Button } from "@components/ui/button";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@components/ui/collapsible";
import { Separator } from "@components/ui/separator";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@components/ui/tooltip";
import { buildVotingBehaviorSeparatorId } from "@lib/scroll-constants";
import {
  chatViewScrollToVotingBehaviorContainer,
  scrollMessageIntoView,
} from "@lib/scroll-utils";
import { type StreamingMessage } from "@lib/socket.types";
import { type MessageItem } from "@lib/stores/chat-store.types";
import { cn } from "@lib/utils";
import { Eye, EyeClosed, SparkleIcon } from "lucide-react";
import { useTranslations } from "next-intl";

import { Markdown } from "../markdown";

import AnimatedMessageSequence from "./animated-message-sequence";
import ChatGroupVotingBehaviorEmblaReinit from "./chat-group-voting-behavior-embla-reinit";
import ChatVotingBehaviorDetailButton from "./chat-voting-behavior-detail-button";
import { type ChatVotingBehaviorDetailButtonRef } from "./chat-voting-behavior-detail-button";

type Props = {
  message: MessageItem | StreamingMessage;
  isGroupChat?: boolean;
};

const ChatVotingBehaviorExpandable = ({ message, isGroupChat }: Props) => {
  const t = useTranslations("chat.votingBehavior");
  const [isExpanded, setIsExpanded] = useState(!message.voting_behavior);
  const isLoadingVotingBehaviorSummary = useChatStore(
    (state) => state.loading.votingBehaviorSummary === message.id,
  );
  const shouldShowVotingBehaviorSummary = useChatStore(
    (state) =>
      state.currentStreamedVotingBehavior?.requestId === message.id ||
      message.voting_behavior?.summary,
  );
  const votingBehavior = useChatStore((state) =>
    state.currentStreamedVotingBehavior?.requestId === message.id
      ? state.currentStreamedVotingBehavior
      : message.voting_behavior,
  );
  const [
    prevIsLoadingVotingBehaviorSummary,
    setPrevIsLoadingVotingBehaviorSummary,
  ] = useState(isLoadingVotingBehaviorSummary);
  const votingBehaviorDetailButtonRef =
    useRef<ChatVotingBehaviorDetailButtonRef>(null);

  const isFirstRender = useRef(true);

  // Adjust state during render (React-recommended pattern for prop/state transitions)
  if (prevIsLoadingVotingBehaviorSummary !== isLoadingVotingBehaviorSummary) {
    setPrevIsLoadingVotingBehaviorSummary(isLoadingVotingBehaviorSummary);
    if (!prevIsLoadingVotingBehaviorSummary && isLoadingVotingBehaviorSummary) {
      setIsExpanded(true);
    }
  }

  useEffect(() => {
    if (isFirstRender.current) {
      isFirstRender.current = false;
      return;
    }

    if (isExpanded) {
      chatViewScrollToVotingBehaviorContainer(message.id);
    } else {
      scrollMessageIntoView(message.id);
    }
  }, [isExpanded, message.id]);

  if (!shouldShowVotingBehaviorSummary) {
    return null;
  }

  const emblaReinitComponent = isGroupChat ? (
    <ChatGroupVotingBehaviorEmblaReinit
      messageId={message.id}
      isExpanded={isExpanded}
    />
  ) : null;

  if (isLoadingVotingBehaviorSummary && !votingBehavior?.summary) {
    return (
      <>
        <Separator />
        <div className="flex items-center gap-4">
          <SparkleIcon className="text-muted-foreground size-4 animate-spin [animation-duration:4s]" />

          <AnimatedMessageSequence
            className="text-muted-foreground"
            messages={[
              t("searchingMotions"),
              t("searchingRecords"),
              t("analyzingSubmitters"),
              t("comparingInfo"),
              t("summarizingResults"),
            ]}
          />
        </div>
        {emblaReinitComponent}
      </>
    );
  }

  const onReferenceClick = (voteId: number) => {
    votingBehaviorDetailButtonRef.current?.open(voteId.toString());
  };

  const getReferenceTooltip = (voteId: number) => {
    const voteIdString = voteId.toString();
    return (
      votingBehavior?.votes?.find((vote) => vote.id === voteIdString)?.title ??
      null
    );
  };

  const getReferenceName = (voteId: number) => {
    return `Vote ${voteId}`;
  };

  return (
    <>
      <Separator id={buildVotingBehaviorSeparatorId(message.id)} />
      <Collapsible open={isExpanded} onOpenChange={setIsExpanded}>
        <CollapsibleContent>
          <Markdown
            onReferenceClick={onReferenceClick}
            getReferenceTooltip={getReferenceTooltip}
            getReferenceName={getReferenceName}
          >
            {votingBehavior?.summary ?? ""}
          </Markdown>
        </CollapsibleContent>
        <div
          className={cn(
            "mt-0 flex flex-row items-center justify-between",
            isExpanded && "mt-4",
          )}
        >
          {!isExpanded ? (
            <p className="text-muted-foreground text-xs">
              {t("containsVotingInfo")}{" "}
              <span className="font-bold">{t("partyVotingBehavior")}</span>{" "}
              {t("ofTheParty")}
            </p>
          ) : message.voting_behavior ? (
            <ChatVotingBehaviorDetailButton
              votingBehavior={message.voting_behavior}
              ref={votingBehaviorDetailButtonRef}
              partyId={message.party_id ?? ""}
            />
          ) : (
            <div />
          )}
          <Tooltip>
            <CollapsibleTrigger asChild>
              <TooltipTrigger asChild>
                <Button variant="ghost" size="icon" className="aspect-square">
                  {isExpanded ? <EyeClosed /> : <Eye />}
                </Button>
              </TooltipTrigger>
            </CollapsibleTrigger>
            <TooltipContent>
              {isExpanded ? t("hide") : t("show")}
            </TooltipContent>
          </Tooltip>
        </div>
      </Collapsible>
      {emblaReinitComponent}
    </>
  );
};

export default ChatVotingBehaviorExpandable;

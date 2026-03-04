import { Separator } from "@components/ui/separator";
import { ASSISTANT_ID } from "@lib/constants";
import { type StreamingMessage } from "@lib/socket.types";
import { type MessageItem } from "@lib/stores/chat-store.types";

import { useChatStore } from "../providers/chat-store-provider";

import ChatMessageLikeDislikeButtons from "./chat-message-like-dislike-buttons";
import ChatProConButton from "./chat-pro-con-button";
import ChatVotingBehaviorSummaryButton from "./chat-voting-behavior-summary-button";
import CopyButton from "./copy-button";
import SourcesButton from "./sources-button";

type Props = {
  message: MessageItem | StreamingMessage;
  isLastMessage?: boolean;
  showMessageActions?: boolean;
  partyId?: string;
  candidateId?: string;
  isGroupChat?: boolean;
};

function ChatSingleMessageActions({
  isLastMessage,
  message,
  showMessageActions,
  partyId,
  candidateId,
}: Props) {
  const isLoadingProConPerspective = useChatStore(
    (state) => state.loading.proConPerspective === message.id,
  );
  const isLoadingVotingBehaviorSummary = useChatStore(
    (state) => state.loading.votingBehaviorSummary === message.id,
  );

  if (!showMessageActions) return null;

  const isAssistantMessage = partyId === ASSISTANT_ID;

  const showProConButton =
    (partyId || candidateId) &&
    !message.pro_con_perspective &&
    !isLoadingProConPerspective &&
    !isAssistantMessage;

  const showVotingBehaviorSummaryButton =
    partyId &&
    !message.voting_behavior &&
    !isLoadingVotingBehaviorSummary &&
    !isAssistantMessage;

  const showSeparator = showProConButton || showVotingBehaviorSummaryButton;

  return (
    <div className="text-muted-foreground flex flex-wrap items-center gap-2">
      <SourcesButton
        sources={message.sources ?? []}
        messageContent={message.content ?? ""}
      />
      {showProConButton && (
        <ChatProConButton
          partyId={partyId}
          candidateId={candidateId}
          message={message}
          isLastMessage={isLastMessage}
        />
      )}

      {showVotingBehaviorSummaryButton && (
        <ChatVotingBehaviorSummaryButton
          partyId={partyId}
          message={message}
          isLastMessage={isLastMessage}
        />
      )}

      {showSeparator && (
        <Separator
          orientation="vertical"
          className="ml-2 hidden h-6 sm:block"
        />
      )}

      <div className="flex items-center">
        <CopyButton
          text={message.content ?? ""}
          variant="ghost"
          size="icon"
          className="size-8"
        />
        <ChatMessageLikeDislikeButtons message={message} />
      </div>
    </div>
  );
}

export default ChatSingleMessageActions;

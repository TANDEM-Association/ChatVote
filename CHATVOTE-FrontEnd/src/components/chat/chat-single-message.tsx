import { useChatStore } from "@components/providers/chat-store-provider";
import { type MessageItem } from "@lib/stores/chat-store.types";
import { cn } from "@lib/utils";

import ChatMarkdown from "./chat-markdown";
import { ChatMessageIcon } from "./chat-message-icon";
import ChatProConExpandable from "./chat-pro-con-expandable";
import ChatSingleMessageActions from "./chat-single-message-actions";
import ChatSingleUserMessage from "./chat-single-user-message";
import ChatVotingBehaviorExpandable from "./chat-voting-behavior-expandable";
import MessageLoadingBorderTrail from "./message-loading-border-trail";
import SurveyBanner from "./survey-banner";

type Props = {
  message: MessageItem;
  partyId?: string;
  candidateId?: string;
  isLastMessage?: boolean;
  showAssistantIcon?: boolean;
  showMessageActions?: boolean;
  isGroupChat?: boolean;
};

function ChatSingleMessage({
  message,
  partyId,
  candidateId,
  isLastMessage,
  showAssistantIcon = true,
  showMessageActions = true,
  isGroupChat = false,
}: Props) {
  const isLoadingAnyAction = useChatStore(
    (state) =>
      state.loading.proConPerspective === message.id ||
      state.loading.votingBehaviorSummary === message.id,
  );

  const shouldHaveBackground =
    message.pro_con_perspective ||
    message.voting_behavior ||
    isLoadingAnyAction;

  const content = (
    <div className="flex flex-col gap-4">
      <ChatMarkdown message={message} />
    </div>
  );

  if (message.role === "user") {
    return (
      <ChatSingleUserMessage
        message={message}
        isLastMessage={isLastMessage ?? false}
      />
    );
  }

  if (message.role === "assistant") {
    return (
      <article
        id={message.id}
        className={cn(
          "relative flex flex-col gap-4 transition-all duration-200 ease-out",
          shouldHaveBackground
            ? "group bg-zinc-100 dark:bg-zinc-900"
            : undefined,
          isGroupChat === false && shouldHaveBackground === true
            ? "border-muted rounded-lg border p-3 md:p-4"
            : undefined,
        )}
        data-has-message-background={Boolean(shouldHaveBackground)}
      >
        <div className={cn("flex items-start justify-start gap-3 md:gap-4")}>
          {showAssistantIcon === true ? <ChatMessageIcon /> : null}
          <div className="flex flex-col gap-2">
            {content}
            {isLastMessage === true ? <SurveyBanner /> : null}
            <ChatSingleMessageActions
              isLastMessage={isLastMessage}
              message={message}
              partyId={partyId}
              candidateId={candidateId}
              showMessageActions={showMessageActions}
              isGroupChat={isGroupChat}
            />
          </div>
        </div>
        <ChatProConExpandable message={message} isGroupChat={isGroupChat} />
        <ChatVotingBehaviorExpandable
          message={message}
          isGroupChat={isGroupChat}
        />
        {isLoadingAnyAction === true && isGroupChat === false ? (
          <MessageLoadingBorderTrail />
        ) : null}
      </article>
    );
  }

  return <ChatMarkdown message={message} />;
}

ChatSingleMessage.displayName = "ChatSingleMessage";

export default ChatSingleMessage;

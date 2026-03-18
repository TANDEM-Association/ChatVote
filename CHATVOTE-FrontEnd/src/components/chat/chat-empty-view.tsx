"use client";

import { useAnonymousAuth } from "@components/anonymous-auth";
import { useChatStore } from "@components/providers/chat-store-provider";
import { trackInitialSuggestionClicked } from "@lib/firebase/analytics";
import { type ProposedQuestion } from "@lib/firebase/firebase.types";
import { type PartyDetails } from "@lib/party-details";
import { useTranslations } from "next-intl";

import GroupChatEmptyView from "./group-chat-empty-view";
import InitialSuggestionBubble from "./initial-suggestion-bubble";

type Props = {
  parties?: PartyDetails[];
  proposedQuestions?: ProposedQuestion[];
  municipalityCode?: string;
};

const ChatEmptyView = ({
  parties,
  proposedQuestions,
  municipalityCode,
}: Props) => {
  const t = useTranslations("chat.emptyView");
  const { user } = useAnonymousAuth();
  const addUserMessage = useChatStore((state) => state.addUserMessage);

  function handleSuggestionClick(suggestion: string) {
    if (!user?.uid) {
      return;
    }

    trackInitialSuggestionClicked({ suggestion_text: suggestion });
    addUserMessage(user.uid, suggestion);
  }

  if (parties && parties.length > 1) {
    return (
      <GroupChatEmptyView
        parties={parties}
        proposedQuestions={proposedQuestions}
      />
    );
  }

  const party = parties?.[0];

  return (
    <div className="flex grow flex-col gap-6 px-2 md:px-8">
      {/* Description as another assistant bubble */}
      {!!municipalityCode && (
        <div className="flex max-w-2xl items-start gap-3">
          <div className="size-10 shrink-0" />{" "}
          {/* spacer to align with icon above */}
          <div className="text-foreground text-sm">
            {party ? (
              <p>{t("partyDescription", { party: party.name })}</p>
            ) : (
              <p>{t("genericDescription")}</p>
            )}
          </div>
        </div>
      )}

      {/* Proposed questions as suggestion chips */}
      {!!municipalityCode && (
        <div className="flex max-w-2xl flex-wrap gap-2 pl-[52px]">
          {proposedQuestions?.map((question) => (
            <InitialSuggestionBubble
              key={question.id}
              onClick={() => handleSuggestionClick(question.content)}
            >
              {question.content}
            </InitialSuggestionBubble>
          ))}
        </div>
      )}

    </div>
  );
};

export default ChatEmptyView;

"use client";

import Image from "next/image";

import { useAnonymousAuth } from "@components/anonymous-auth";
import ChatPostcodePrompt from "@components/chat/chat-postcode-prompt";
import { useChatStore } from "@components/providers/chat-store-provider";
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
    <div className="flex grow flex-col items-center justify-center gap-4 px-8">
      <div className="relative flex size-28 items-center justify-center rounded-md border-2 border-purple-400 md:size-36">
        {party ? (
          <Image
            alt={party.name}
            src={party.logo_url}
            fill
            sizes="(max-width: 768px) 40vw, 20vw"
            className="object-contain p-4"
          />
        ) : (
          <Image
            src="/images/logos/chatvote.svg"
            alt="chatvote"
            width={0}
            height={0}
            sizes="100vw"
            className="size-full p-4"
          />
        )}
      </div>
      <ChatPostcodePrompt />
      {!!municipalityCode ? (
        <div>
          {party ? (
            <p className="text-center">
              {t("partyDescription", { party: party.name })}
            </p>
          ) : (
            <p className="text-center">{t("genericDescription")}</p>
          )}
        </div>
      ) : null}
      <div className="flex max-w-xl flex-wrap justify-center gap-2">
        {proposedQuestions?.map((question) => (
          <InitialSuggestionBubble
            key={question.id}
            onClick={() => handleSuggestionClick(question.content)}
          >
            {question.content}
          </InitialSuggestionBubble>
        ))}
      </div>
    </div>
  );
};

export default ChatEmptyView;

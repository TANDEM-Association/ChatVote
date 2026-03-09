"use client";

import React from "react";

import Image from "next/image";

import { useAnonymousAuth } from "@components/anonymous-auth";
import { trackInitialSuggestionClicked } from "@lib/firebase/analytics";
import { useChatStore } from "@components/providers/chat-store-provider";
import { type ProposedQuestion } from "@lib/firebase/firebase.types";
import { type PartyDetails } from "@lib/party-details";
import { toTitleCase } from "@lib/utils";
import { CheckCircle2 } from "lucide-react";
import { useTranslations } from "next-intl";

import ChatPostcodePrompt from "./chat-postcode-prompt";
import InitialSuggestionBubble from "./initial-suggestion-bubble";

type Props = {
  parties: PartyDetails[];
  proposedQuestions?: ProposedQuestion[];
};

const GroupChatEmptyView = ({ parties, proposedQuestions }: Props) => {
  const t = useTranslations("chat.emptyView");
  const { user } = useAnonymousAuth();
  const addUserMessage = useChatStore((state) => state.addUserMessage);
  const selectedElectoralLists = useChatStore(
    (state) => state.selectedElectoralLists,
  );
  const electoralListsData = useChatStore(
    (state) => state.electoralListsData,
  );
  const selectedLists = electoralListsData.filter((l) =>
    selectedElectoralLists.includes(l.panel_number),
  );

  function handleSuggestionClick(suggestion: string) {
    if (!user?.uid) {
      return;
    }

    trackInitialSuggestionClicked({ suggestion_text: suggestion });
    addUserMessage(user.uid, suggestion);
  }

  const imageSize = 75;

  return (
    <React.Fragment>
      <div className="flex grow flex-col items-center justify-center gap-4 px-8">
        <div
          className="relative flex flex-col items-center justify-center"
          style={{
            height: imageSize,
            width: (imageSize * (parties?.length ? parties.length + 1 : 0)) / 2,
          }}
        >
          {parties?.map((party, index) => (
            <Image
              key={party.party_id}
              alt={party.name}
              src={party.logo_url}
              width={imageSize}
              height={imageSize}
              className="border-background absolute top-0 aspect-square rounded-full border-2 bg-neutral-100 object-contain p-2 transition-transform duration-200 ease-in-out hover:z-30 hover:-translate-y-4 hover:scale-125"
              style={{
                left: `${(index * imageSize) / 2}px`,
              }}
            />
          ))}
        </div>
        <ChatPostcodePrompt />
        <p className="text-center">
          {t("groupDescription")}
          <br />
          {parties?.map((party, index) => (
            <span key={party.party_id} className="font-semibold">
              {toTitleCase(party.name)}
              {parties.length > 1 && index < parties.length - 1 && ", "}
            </span>
          ))}
        </p>
        {selectedLists.length > 0 && (
          <div className="flex max-w-xl flex-wrap items-center justify-center gap-2">
            <span className="text-muted-foreground text-xs">
              {t("selectedLists")}
            </span>
            {selectedLists.map((list) => (
              <span
                key={list.panel_number}
                className="bg-primary/10 text-primary inline-flex items-center gap-1 rounded-full px-3 py-1 text-xs font-medium"
              >
                <CheckCircle2 className="size-3" />
                {list.list_short_label || list.list_label}
              </span>
            ))}
          </div>
        )}
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
    </React.Fragment>
  );
};

export default GroupChatEmptyView;

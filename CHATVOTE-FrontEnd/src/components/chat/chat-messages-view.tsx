"use client";

import { useEffect, useMemo, useRef } from "react";

import Image from "next/image";

import { useAnonymousAuth } from "@components/anonymous-auth";
import { useAppContext } from "@components/providers/app-provider";
import { useChatStore } from "@components/providers/chat-store-provider";
import { useTenant } from "@components/providers/tenant-provider";
import {
  type ChatSession,
  type ProposedQuestion,
} from "@lib/firebase/firebase.types";
import { type PartyDetails } from "@lib/party-details";
import { type GroupedMessage } from "@lib/stores/chat-store.types";

import ChatEmptyView from "./chat-empty-view";
import ChatGroupedMessages from "./chat-grouped-messages";
import SponsorPartners from "./sponsor-partners";
import ChatMessagesScrollView from "./chat-messages-scroll-view";
import ChatPartyHeader from "./chat-party-header";
import ChatPostcodePrompt from "./chat-postcode-prompt";
import { INITIAL_MESSAGE_ID } from "./chat-single-user-message";
import CurrentStreamingMessages from "./current-streaming-messages";
import DemographicBubble, {
  getNextDemographicQuestion,
} from "./demographic-bubble";

type Props = {
  chatId?: string;
  chatSession?: ChatSession;
  messages?: GroupedMessage[];
  parties?: PartyDetails[];
  allParties?: PartyDetails[];
  proposedQuestions?: ProposedQuestion[];
  initialQuestion?: string;
  municipalityCode?: string;
};

function ChatMessagesView({
  chatId,
  chatSession,
  messages,
  parties,
  allParties,
  proposedQuestions,
  initialQuestion,
  municipalityCode,
}: Props) {
  const hasFetched = useRef(false);
  const storeMessages = useChatStore((state) => state.messages);
  const hydrateChatSession = useChatStore((state) => state.hydrateChatSession);
  const { user } = useAnonymousAuth();
  const tenant = useTenant();
  const { locale } = useAppContext();

  const hasCurrentStreamingMessages = useChatStore(
    (state) => state.currentStreamingMessages !== undefined,
  );
  const userDemographics = useChatStore((s) => s.userDemographics);
  const demographicsLoaded = useChatStore((s) => s.demographicsLoaded);
  const loadUserDemographics = useChatStore((s) => s.loadUserDemographics);

  // Load demographics on mount
  useEffect(() => {
    if (user?.uid && !demographicsLoaded) {
      void loadUserDemographics(user.uid);
    }
  }, [user?.uid, demographicsLoaded, loadUserDemographics]);

  useEffect(() => {
    if (!user?.uid) return;

    hydrateChatSession({
      chatSession,
      chatId,
      messages,
      preSelectedPartyIds: parties?.map((party) => party.party_id),
      initialQuestion,
      userId: user.uid,
      tenant,
      municipalityCode,
      locale,
    });

    hasFetched.current = true;
  }, [
    chatId,
    user?.uid,
    chatSession,
    hydrateChatSession,
    messages,
    parties,
    initialQuestion,
    tenant,
    municipalityCode,
    locale,
  ]);

  const normalizedMessages = useMemo(() => {
    if (messages && !storeMessages.length) {
      return messages;
    }

    if (!storeMessages.length && initialQuestion) {
      return [
        {
          id: INITIAL_MESSAGE_ID,
          messages: [
            {
              role: "user",
              content: initialQuestion,
              id: INITIAL_MESSAGE_ID,
              sources: [],
            },
          ],
          role: "user",
        } satisfies GroupedMessage,
      ];
    }

    return storeMessages;
  }, [messages, storeMessages, initialQuestion]);

  return (
    <ChatMessagesScrollView hasMessages={normalizedMessages.length > 0}>
      {/* Sticky party header when there are messages */}
      {normalizedMessages.length > 0 && <ChatPartyHeader parties={parties} />}

      {normalizedMessages.length === 0 ? (
        /* Empty state: logo → city input → sponsors → suggestions, all in one container */
        <div className="flex flex-col items-center gap-4 px-3 py-4 md:gap-5 md:py-8 md:px-9">
          <Image src="/images/logos/chatvote.svg" alt="ChatVote" width={260} height={87} priority className="w-40 md:w-52 lg:w-[260px] h-auto" />
          <ChatPostcodePrompt />
          <SponsorPartners />
          <ChatEmptyView
            parties={parties}
            proposedQuestions={proposedQuestions}
            municipalityCode={municipalityCode}
          />
        </div>
      ) : (
        <>
          {/* City input above messages */}
          <div className="flex justify-center px-3 pt-4 md:px-9">
            <div className="w-full max-w-2xl">
              <ChatPostcodePrompt />
            </div>
          </div>

          <div className="flex flex-col gap-6 px-3 py-4 md:px-9">
            {normalizedMessages.map((m, index) => {
              // Count user messages up to this point (inclusive)
              const userMessageCount = normalizedMessages
                .slice(0, index + 1)
                .filter((msg) => msg.role === "user").length;

              // Show demographic question after assistant response to specific user message counts
              const demographicQuestion =
                demographicsLoaded && m.role !== "user"
                  ? getNextDemographicQuestion(userMessageCount, userDemographics)
                  : null;

              return (
                <div key={m.id}>
                  <ChatGroupedMessages
                    message={m}
                    isLastMessage={index === normalizedMessages.length - 1}
                    parties={allParties?.filter((p) =>
                      m.messages.some((msg) => msg.party_id === p.party_id),
                    )}
                  />
                  {demographicQuestion && (
                    <DemographicBubble
                      question={demographicQuestion}
                      messageNumber={userMessageCount}
                    />
                  )}
                </div>
              );
            })}

            {hasCurrentStreamingMessages && <CurrentStreamingMessages />}
          </div>
        </>
      )}
    </ChatMessagesScrollView>
  );
}

export default ChatMessagesView;

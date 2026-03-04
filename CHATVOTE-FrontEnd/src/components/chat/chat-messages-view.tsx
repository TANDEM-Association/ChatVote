"use client";

import { useEffect, useMemo, useRef } from "react";

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
import ChatMessagesScrollView from "./chat-messages-scroll-view";
import ChatPartyHeader from "./chat-party-header";
import { INITIAL_MESSAGE_ID } from "./chat-single-user-message";
import CurrentStreamingMessages from "./current-streaming-messages";

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
    <ChatMessagesScrollView>
      {/* Sticky party header when there are messages */}
      {normalizedMessages.length > 0 && <ChatPartyHeader parties={parties} />}

      <div className="flex flex-col gap-6 px-3 py-4 md:px-9">
        {normalizedMessages.length === 0 && (
          <div className="mt-12 flex h-full grow justify-center">
            <ChatEmptyView
              parties={parties}
              proposedQuestions={proposedQuestions}
              municipalityCode={municipalityCode}
            />
          </div>
        )}

        {normalizedMessages.map((m, index) => (
          <ChatGroupedMessages
            key={m.id}
            message={m}
            isLastMessage={index === normalizedMessages.length - 1}
            parties={allParties?.filter((p) =>
              m.messages.some((m) => m.party_id === p.party_id),
            )}
          />
        ))}

        {hasCurrentStreamingMessages && <CurrentStreamingMessages />}
      </div>
    </ChatMessagesScrollView>
  );
}

export default ChatMessagesView;

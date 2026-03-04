import { type ChatStoreActionHandlerFor } from "@lib/stores/chat-store.types";
import { generateUuid } from "@lib/utils";

export const initializeChatSession: ChatStoreActionHandlerFor<
  "initializeChatSession"
> = (get, set) => async () => {
  const {
    chatId,
    socket,
    messages,
    currentChatTitle,
    partyIds,
    localPreliminaryChatId,
    getLLMSize,
    scope,
    municipalityCode,
    locale,
  } = get();

  if (!socket.io?.connected) {
    return;
  }

  if (!chatId && !localPreliminaryChatId) {
    set({
      localPreliminaryChatId: generateUuid(),
    });
  }

  const chatHistory = messages.flatMap((message) =>
    message.messages.map((innerMessage) => ({
      ...innerMessage,
      role: innerMessage.role,
      created_at: message.created_at,
      quick_replies: message.quick_replies,
    })),
  );

  const lastQuickReplies = chatHistory.findLast(
    (message) => message.role === "assistant",
  )?.quick_replies;

  socket.io.initializeChatSession({
    session_id: chatId ?? get().localPreliminaryChatId ?? generateUuid(),
    party_ids: [...partyIds],
    chat_history: chatHistory,
    last_quick_replies: lastQuickReplies ?? [],
    current_title: currentChatTitle ?? [...partyIds].join(", ") ?? "no-title",
    chat_response_llm_size: getLLMSize(),
    scope,
    municipality_code: municipalityCode,
    locale,
  });
};

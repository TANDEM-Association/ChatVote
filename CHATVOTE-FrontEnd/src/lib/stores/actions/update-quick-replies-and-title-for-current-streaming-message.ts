import {
  updateQuickRepliesOfMessage,
  updateTitleOfMessage,
} from "@lib/firebase/firebase";
import { type ChatStoreActionHandlerFor } from "@lib/stores/chat-store.types";

export const updateQuickRepliesAndTitleForCurrentStreamingMessage: ChatStoreActionHandlerFor<
  "updateQuickRepliesAndTitleForCurrentStreamingMessage"
> = (get, set) => async (sessionId, quickReplies, title) => {
  const { chatId, messages } = get();

  if (!chatId) return;
  if (chatId !== sessionId) {
    await updateTitleOfMessage(sessionId, title);

    return;
  }

  const lastMessage = messages[messages.length - 1];

  set((state) => {
    state.loading.newMessage = false;
    state.currentQuickReplies = quickReplies;
    state.currentChatTitle = title;
  });

  await Promise.all([
    updateQuickRepliesOfMessage(chatId, lastMessage.id, quickReplies),
    updateTitleOfMessage(chatId, title),
  ]);
};

import { type ChatStoreActionHandlerFor } from "@lib/stores/chat-store.types";

export const initializedChatSession: ChatStoreActionHandlerFor<
  "initializedChatSession"
> = (get, set) => async (sessionId: string) => {
  const { pendingInitialQuestion, addUserMessage, userId } = get();

  set((state) => {
    state.chatId = sessionId;
    state.localPreliminaryChatId = sessionId;
    state.loading.initializingChatSocketSession = false;
  });

  if (pendingInitialQuestion && userId) {
    addUserMessage(userId, pendingInitialQuestion);
  }
};

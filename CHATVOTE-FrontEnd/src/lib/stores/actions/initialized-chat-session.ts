import { type ChatStoreActionHandlerFor } from "@lib/stores/chat-store.types";

export const initializedChatSession: ChatStoreActionHandlerFor<
  "initializedChatSession"
> = (get, set) => async (sessionId: string) => {
  const { pendingInitialQuestion, addUserMessage, userId } = get();

  // Ignore stale chat_session_initialized responses that arrive during
  // active streaming with a mismatched session ID. Multiple chat_session_init
  // events are emitted on page load (socket connect, hydrate, re-renders),
  // each with a different UUID. If a late callback overwrites chatId while
  // streaming is active, all streaming events are silently dropped by the
  // session_id !== chatId guards (selectRespondingParties, sourcesReady, etc.)
  // causing a frontend timeout on the first request.
  const isActivelyStreaming =
    get().loading.newMessage || get().currentStreamingMessages !== undefined;
  const currentChatId = get().chatId;

  if (isActivelyStreaming && currentChatId && currentChatId !== sessionId) {
    return;
  }

  set((state) => {
    state.chatId = sessionId;
    state.localPreliminaryChatId = sessionId;
  });

  if (pendingInitialQuestion && userId) {
    addUserMessage(userId, pendingInitialQuestion);
  }
};

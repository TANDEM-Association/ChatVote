import { type ChatStoreActionHandlerFor } from "@lib/stores/chat-store.types";

export const newChat: ChatStoreActionHandlerFor<"newChat"> =
  (get, set) => () => {
    set({
      chatId: undefined,
      messages: [],
      input: "",
      error: undefined,
      currentQuickReplies: [],
      currentChatTitle: undefined,
    });
  };

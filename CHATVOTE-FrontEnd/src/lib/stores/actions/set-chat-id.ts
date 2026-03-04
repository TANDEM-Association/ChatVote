import { type ChatStoreActionHandlerFor } from "@lib/stores/chat-store.types";

export const setChatId: ChatStoreActionHandlerFor<"setChatId"> =
  (get, set) => (chatId) => {
    set({ chatId });
  };

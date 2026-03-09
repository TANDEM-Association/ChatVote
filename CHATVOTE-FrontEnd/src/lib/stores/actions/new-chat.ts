import { trackNewChatStarted } from "@lib/firebase/analytics";
import { type ChatStoreActionHandlerFor } from "@lib/stores/chat-store.types";

export const newChat: ChatStoreActionHandlerFor<"newChat"> =
  (get, set) => () => {
    const { scope, partyIds } = get();

    set({
      chatId: undefined,
      messages: [],
      input: "",
      error: undefined,
      currentQuickReplies: [],
      currentChatTitle: undefined,
      municipalityCode: undefined,
      scope: "national",
      selectedElectoralLists: [],
    });

    trackNewChatStarted({
      scope,
      party_count: partyIds.size,
    });
  };

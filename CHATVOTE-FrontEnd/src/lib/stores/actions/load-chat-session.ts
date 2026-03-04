import { getChatSession, getChatSessionMessages } from "@lib/firebase/firebase";
import { type ChatStoreActionHandlerFor } from "@lib/stores/chat-store.types";

export const loadChatSession: ChatStoreActionHandlerFor<"loadChatSession"> =
  (get, set) => async (chatId) => {
    set((state) => {
      state.loading.chatSession = true;
      state.error = undefined;
      state.chatId = chatId;
    });

    try {
      const session = await getChatSession(chatId);
      const messages = await getChatSessionMessages(chatId);

      return set((state) => ({
        messages,
        currentQuickReplies:
          messages.length > 0
            ? (messages[messages.length - 1].quick_replies ?? [])
            : [],
        currentChatTitle: session.title,
        chatSessionIsPublic: session.is_public,
        partyIds: new Set(session.party_ids ?? []),
        preSelectedPartyIds: new Set(session.party_ids ?? []),
        currentStreamingMessages: undefined,
        loading: {
          ...state.loading,
          chatSession: false,
          initializingChatSession: false,
          newMessage: false,
        },
      }));
    } catch (error) {
      console.error(error);

      set((state) => {
        state.loading.chatSession = false;
        state.loading.newMessage = false;
        state.error = "Failed to load chat session";
        state.messages = [];
      });

      return Promise.reject(error);
    }
  };

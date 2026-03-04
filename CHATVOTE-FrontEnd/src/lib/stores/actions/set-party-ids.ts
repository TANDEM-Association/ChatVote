import { updateChatSession } from "@lib/firebase/firebase";
import { type ChatStoreActionHandlerFor } from "@lib/stores/chat-store.types";

export const setPartyIds: ChatStoreActionHandlerFor<"setPartyIds"> =
  (get, set) => async (partyIds: string[]) => {
    const { chatId } = get();
    if (!chatId) return;

    set((state) => {
      state.partyIds = new Set([...partyIds]);
    });

    await updateChatSession(chatId, {
      party_ids: Array.from(get().partyIds),
    });
  };

import { updateChatSession } from "@lib/firebase/firebase";
import { type ChatStoreActionHandlerFor } from "@lib/stores/chat-store.types";

export const setChatSessionIsPublic: ChatStoreActionHandlerFor<
  "setChatSessionIsPublic"
> = (get, set) => async (isPublic) => {
  const { chatId } = get();

  if (!chatId) return;

  await updateChatSession(chatId, {
    is_public: isPublic,
  });

  return set({ chatSessionIsPublic: isPublic });
};

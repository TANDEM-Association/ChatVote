import { type ChatStoreActionHandlerFor } from "@lib/stores/chat-store.types";
import { toast } from "sonner";

export const resetStreamingMessage: ChatStoreActionHandlerFor<
  "resetStreamingMessage"
> = (get, set) => (sessionId, partyId, reason) => {
  toast.info(`Stream reset: ${reason}`);

  set((state) => {
    if (state.chatId !== sessionId) {
      return;
    }

    if (!state.currentStreamingMessages) {
      return;
    }

    const currentStreamingMessage =
      state.currentStreamingMessages.messages[partyId];

    if (!currentStreamingMessage) {
      return;
    }

    // Clear the content for this party's streaming message
    state.currentStreamingMessages.messages[partyId].content = "";
  });
};

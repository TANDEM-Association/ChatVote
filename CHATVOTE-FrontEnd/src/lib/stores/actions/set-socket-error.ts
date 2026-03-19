import { trackErrorOccurred } from "@lib/firebase/analytics";
import { type ChatStoreActionHandlerFor } from "@lib/stores/chat-store.types";

export const setSocketError: ChatStoreActionHandlerFor<"setSocketError"> =
  (get, set) => (error) => {
    set((state) => {
      state.socket.error = error;
    });
    trackErrorOccurred({
      error_type: "socket_error",
      error_context: typeof error === "string" ? error : undefined,
    });
  };

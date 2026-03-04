import { addProConPerspectiveToMessage } from "@lib/firebase/firebase";
import {
  type ChatStoreActionHandlerFor,
  type MessageItem,
} from "@lib/stores/chat-store.types";

export const completeCandidateProConPerspective: ChatStoreActionHandlerFor<
  "completeCandidateProConPerspective"
> =
  (get, set) =>
  async (requestId: string, candidateId: string, message: MessageItem) => {
    const { chatId, messages } = get();

    if (!chatId) {
      return;
    }

    const indexOfProConPerspectiveGroupedMessage = messages.findIndex((m) =>
      m.messages.find((m) => m.id === requestId),
    );
    if (indexOfProConPerspectiveGroupedMessage === -1) {
      return;
    }

    const indexOfProConPerspectiveMessage = messages[
      indexOfProConPerspectiveGroupedMessage
    ].messages.findIndex((m) => m.id === requestId);

    if (indexOfProConPerspectiveMessage === -1) {
      return;
    }

    set((state) => {
      state.messages[indexOfProConPerspectiveGroupedMessage].messages[
        indexOfProConPerspectiveMessage
      ].pro_con_perspective = message;
      state.loading.proConPerspective = undefined;
    });

    await addProConPerspectiveToMessage(
      chatId,
      messages[indexOfProConPerspectiveGroupedMessage].id,
      requestId,
      message,
    );
  };

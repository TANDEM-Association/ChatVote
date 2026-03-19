import { trackChatMessageSent, trackErrorOccurred } from "@lib/firebase/analytics";
import {
  addUserMessageToChatSession,
  createChatSession,
} from "@lib/firebase/firebase";
import { chatViewScrollToBottom } from "@lib/scroll-utils";
import { type ChatStoreActionHandlerFor } from "@lib/stores/chat-store.types";
import { generateUuid } from "@lib/utils";
import { Timestamp } from "firebase/firestore";
import { toast } from "sonner";

export const chatAddUserMessage: ChatStoreActionHandlerFor<"addUserMessage"> =
  (get, set) =>
  async (userId: string, message: string, fromInitialQuestion?: boolean) => {
    const {
      isAnonymous,
      chatId: _chatId,
      localPreliminaryChatId: _localPreliminaryChatId,
      socket,
      partyIds,
      initializeChatSession,
      startTimeoutForStreamingMessages,
    } = get();

    if (!socket.io?.connected) {
      if (!fromInitialQuestion) toast.error("chatvote n'est pas connecté.");
      else
        set((state) => {
          state.initialQuestionError = message;
        });
      trackErrorOccurred({ error_type: "socket_disconnected" });
      return;
    }

    // Always re-initialize the session so the backend has the latest context
    // (e.g. electoral list selection changes since last init).
    initializeChatSession();

    chatViewScrollToBottom();

    const safeSessionId = get().chatId ?? get().localPreliminaryChatId;

    if (!safeSessionId) {
      toast.error("Chat Session out of sync");

      return;
    }

    let messages = get().messages;
    const lastMessage = messages[messages.length - 1];
    const isMessageResend =
      messages.length > 0 &&
      lastMessage.role === "user" &&
      lastMessage.messages[0].content === message;

    set((state) => {
      if (!isMessageResend) {
        state.messages.push({
          id: generateUuid(),
          role: "user",
          messages: [
            {
              id: generateUuid(),
              content: message,
              sources: [],
              role: "user",
              created_at: Timestamp.now(),
            },
          ],
          quick_replies: [],
          created_at: Timestamp.now(),
        });

        state.input = "";
      }
      state.loading.newMessage = true;
    });

    messages = get().messages;
    const { tenant, municipalityCode } = get();

    try {
      if (messages.length < 2 && !isMessageResend) {
        // Eagerly set chatId in the store so that streaming socket events
        // (responding_parties_selected, party_response_chunk_ready, etc.)
        // are not dropped by their `state.chatId !== session_id` guards.
        // This also ensures hydrateChatSession sees changedPage=false, so it
        // will not clear currentStreamingMessages when the navigation to
        // /chat/[chatId] triggers a re-render.
        set((state) => {
          state.chatId = safeSessionId;
        });

        if (typeof window !== "undefined") {
          const url = new URL(window.location.href);

          if (url.pathname === "/chat") {
            url.searchParams.set("chat_id", safeSessionId);
            window.history.replaceState({}, "", url);
          }
        }

        // Persist to Firestore without blocking the socket emit — the
        // streaming response must not wait for the Firestore write to settle
        // (in dev the emulator can be slow to accept writes after a reset).
        createChatSession(
          userId,
          [...partyIds],
          safeSessionId,
          tenant?.id,
          municipalityCode,
        ).catch(console.error);
      }

      if (!isMessageResend) {
        // Same rationale: persist without blocking the socket emit.
        addUserMessageToChatSession(safeSessionId, message).catch(
          console.error,
        );
      }

      socket.io?.addUserMessage({
        session_id: safeSessionId,
        user_message: message,
        party_ids: Array.from(partyIds),
        user_is_logged_in: !isAnonymous,
      });

      trackChatMessageSent({
        session_id: safeSessionId,
        message_length: message.length,
        has_demographics: false,
      });

      const currentStreamingMessageId = generateUuid();

      set((state) => {
        state.currentStreamingMessages = {
          id: currentStreamingMessageId,
          messages: {},
        };

        state.initialQuestionError = undefined;
        state.pendingInitialQuestion = undefined;
      });

      startTimeoutForStreamingMessages(currentStreamingMessageId);

      chatViewScrollToBottom();
    } catch (error) {
      console.error(error);
      trackErrorOccurred({
        error_type: "message_failed",
        error_context: error instanceof Error ? error.message : undefined,
      });
      set((state) => {
        state.loading.newMessage = false;
        state.error = "Failed to get chat answer";
      });
    }
  };

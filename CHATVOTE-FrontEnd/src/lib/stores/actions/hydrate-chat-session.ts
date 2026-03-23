import { chatViewScrollToBottom } from "@lib/scroll-utils";
import { type ChatStoreActionHandlerFor } from "@lib/stores/chat-store.types";
import { areSetsEqual, generateUuid } from "@lib/utils";
import { toast } from "sonner";

export const hydrateChatSession: ChatStoreActionHandlerFor<
  "hydrateChatSession"
> =
  (get, set) =>
  async ({
    chatSession,
    chatId,
    messages,
    preSelectedPartyIds,
    initialQuestion,
    userId,
    tenant,
    municipalityCode,
    locale,
  }) => {
    const {
      chatId: currentChatId,
      partyIds: currentPartyIds,
      loadChatSession,
    } = get();

    const partyIds = new Set(preSelectedPartyIds ?? []);

    // When the first message is sent on /chat (no [chatId] route), addUserMessage
    // sets store.chatId to the session UUID while the SSR chatId prop stays
    // undefined.  If the useEffect re-fires later (tenant / locale dep change),
    // we'd see chatId(undefined) !== currentChatId(UUID) → changedPage=true,
    // which would clobber chatId back to undefined and clear messages.
    // Guard: only treat it as a page change when the prop actually carries a
    // *different* value, not when it's just missing.
    const hasActiveSession =
      currentChatId !== undefined && get().messages.length > 0;
    const changedPage =
      (chatId !== currentChatId &&
        !(chatId === undefined && hasActiveSession)) ||
      !areSetsEqual(partyIds, currentPartyIds);

    // Determine scope based on municipality code presence
    const scope = municipalityCode !== undefined ? "local" : "national";

    set((state) => {
      // During active streaming, do NOT overwrite chatId — the store's
      // chatId was set by addUserMessage and all streaming event handlers
      // rely on it matching the session_id from the backend.  When the
      // useEffect re-fires (e.g. locale/tenant dependency change) with the
      // SSR chatId prop still undefined, changedPage becomes true and would
      // clobber chatId to undefined, silently dropping every socket event.
      const isActivelyStreaming =
        state.loading.newMessage ||
        state.currentStreamingMessages !== undefined;

      if (!isActivelyStreaming) {
        const sessionId = changedPage ? chatId : state.chatId;
        const preliminarySessionId =
          (changedPage ? sessionId : state.localPreliminaryChatId) ??
          generateUuid();

        state.chatId = sessionId;
        state.localPreliminaryChatId = preliminarySessionId;
        state.partyIds = partyIds;
      }

      state.initialQuestionError = undefined;
      state.pendingInitialQuestion = initialQuestion;
      state.userId = userId;
      state.tenant = tenant;
      state.scope = scope;
      if (state.municipalityCode !== municipalityCode) {
        state.selectedElectoralLists = [];
        state.electoralListsData = [];
      }
      state.municipalityCode = municipalityCode;
      state.locale = locale;
    });

    if (initialQuestion && typeof window !== "undefined") {
      const url = new URL(window.location.href);
      url.searchParams.delete("q");
      window.history.replaceState({}, "", url.toString());
    }

    if (chatSession && messages !== undefined) {
      set((state) => {
        const lastMessage = messages[messages.length - 1];
        // Don't clear streaming state if a message is actively being sent
        // (loading.newMessage=true) or streaming is already in progress.
        // This handles the first-message flow where chatId transitions from
        // undefined → session UUID (changedPage=true), but streaming must
        // survive the navigation from /chat → /chat/[chatId].
        const isActivelyStreaming =
          state.loading.newMessage ||
          state.currentStreamingMessages !== undefined;

        return {
          messages,
          chatId: chatSession.id,
          // Only reset streaming-related state when actually navigating to a
          // different session AND no streaming is in progress.
          ...(changedPage && !isActivelyStreaming
            ? {
                currentQuickReplies: lastMessage
                  ? (lastMessage.quick_replies ?? [])
                  : [],
                currentStreamingMessages: undefined,
              }
            : {}),
          currentChatTitle: chatSession.title,
          chatSessionIsPublic: chatSession.is_public,
          partyIds: new Set(chatSession.party_ids ?? []),
          preSelectedPartyIds: new Set(chatSession.party_ids ?? []),
          loading: {
            ...state.loading,
            chatSession: false,
            newMessage: false,
          },
        };
      });

      chatViewScrollToBottom();
    } else if (chatId && changedPage) {
      await toast
        .promise(loadChatSession(chatId), {
          loading: "Loading chat session...",
          success: "Chat session loaded!",
          error: "Failed to load chat session",
        })
        .unwrap();
    } else {
      set((state) => {
        // Don't clear streaming state if a response is actively being
        // streamed.  The else-branch fires when the useEffect re-runs
        // (e.g. locale / tenant dependency change) while no SSR session
        // is present — which is exactly the first-message flow.
        const isActivelyStreaming =
          state.loading.newMessage ||
          state.currentStreamingMessages !== undefined;

        if (isActivelyStreaming) {
          return {
            loading: {
              ...state.loading,
              chatSession: false,
              },
          };
        }

        // Don't clear an active session's messages when the useEffect
        // merely re-fired due to a dependency change (tenant, locale).
        // The store already holds valid messages from addUserMessage +
        // completeStreamingMessage; wiping them causes content to vanish
        // the instant streaming finishes.
        if (state.chatId && state.messages.length > 0) {
          return {
            loading: {
              ...state.loading,
              chatSession: false,
              },
          };
        }

        return {
          messages: [],
          currentQuickReplies: [],
          currentChatTitle: undefined,
          chatSessionIsPublic: false,
          currentStreamingMessages: undefined,
          loading: {
            ...state.loading,
            chatSession: false,
            newMessage: false,
          },
        };
      });
    }

  };

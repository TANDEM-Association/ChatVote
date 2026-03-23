import { DEFAULT_LLM_SIZE } from "@lib/firebase/firebase.types";
import { devtools } from "zustand/middleware";
import { immer } from "zustand/middleware/immer";
import { createStore } from "zustand/vanilla";

import { addVotingBehaviorResult } from "./actions/add-voting-behavior-result";
import { addVotingBehaviorSummaryChunk } from "./actions/add-voting-behavior-summary-chunk";
import { cancelStreamingMessages } from "./actions/cancel-streaming-messages";
import { completeCandidateProConPerspective } from "./actions/complete-candidate-pro-con-perspective";
import { completeProConPerspective } from "./actions/complete-pro-con-perspective";
import { completeStreamingMessage } from "./actions/complete-streaming-message";
import { completeVotingBehavior } from "./actions/complete-voting-behavior";
import { hydrateChatSession } from "./actions/hydrate-chat-session";
import { initializedChatSession } from "./actions/initialized-chat-session";
import { loadChatSession } from "./actions/load-chat-session";
import { mergeStreamingChunkPayloadForMessage } from "./actions/merge-streaming-chunk-payload-for-message";
import { newChat } from "./actions/new-chat";
import { resetStreamingMessage } from "./actions/reset-streaming-message";
import { selectRespondingParties } from "./actions/select-responding-parties";
import { setChatId } from "./actions/set-chat-id";
import { setChatSessionIsPublic } from "./actions/set-chat-session-is-public";
import { setInput } from "./actions/set-input";
import { setMessageFeedback } from "./actions/set-message-feedback";
import { setPartyIds } from "./actions/set-party-ids";
import { setPreSelectedParties } from "./actions/set-pre-selected-parties";
import { startTimeoutForStreamingMessages } from "./actions/start-timeout-for-streaming-messages";
import { streamingMessageSourcesReady } from "./actions/streaming-message-sources-ready";
import { updateQuickRepliesAndTitleForCurrentStreamingMessage } from "./actions/update-quick-replies-and-title-for-current-streaming-message";
import {
  loadUserDemographics,
  setUserDemographic,
} from "./actions/user-demographics";
import { type ChatStore, type ChatStoreState } from "./chat-store.types";

export const SURVEY_BANNER_MIN_MESSAGE_COUNT = 8;

const defaultState: ChatStoreState = {
  userId: undefined,
  isAnonymous: true,
  chatId: undefined,
  localPreliminaryChatId: undefined,
  partyIds: new Set(),
  messages: [],
  input: "",
  loading: {
    general: false,
    chatSession: false,
    proConPerspective: undefined,
    newMessage: false,
    votingBehaviorSummary: undefined,
  },
  pendingStreamingMessageTimeoutHandler: {},
  error: undefined,
  initialQuestionError: undefined,
  currentQuickReplies: [],
  currentChatTitle: undefined,
  chatSessionIsPublic: false,
  preSelectedParties: undefined,
  currentStreamingMessages: undefined,
  tenant: undefined,
  scope: "national",
  municipalityCode: undefined,
  selectedElectoralLists: [],
  electoralListsData: [],
  locale: "fr",
  userDemographics: null,
  demographicsLoaded: false,
  debugLlmCalls: [],
  secondRoundPartyIds: null,
};

export function createChatStore(initialState?: Partial<ChatStore>) {
  return createStore<ChatStore>()(
    devtools(
      immer((set, get) => ({
        ...defaultState,
        ...initialState,
        setIsAnonymous: (isAnonymous: boolean) => set({ isAnonymous }),
        setLocale: (locale: string) => set({ locale }),
        setInput: setInput(get, set),
        addUserMessage: () => {},
        setChatId: setChatId(get, set),
        newChat: newChat(get, set),
        selectRespondingParties: selectRespondingParties(get, set),
        loadChatSession: loadChatSession(get, set),
        hydrateChatSession: hydrateChatSession(get, set),
        generateProConPerspective: async () => {},
        generateCandidateProConPerspective: async () => {},
        completeCandidateProConPerspective: completeCandidateProConPerspective(
          get,
          set,
        ),
        setChatSessionIsPublic: setChatSessionIsPublic(get, set),
        setMessageFeedback: setMessageFeedback(get, set),
        setPreSelectedParties: setPreSelectedParties(get, set),
        initializedChatSession: initializedChatSession(get, set),
        streamingMessageSourcesReady: streamingMessageSourcesReady(get, set),
        mergeStreamingChunkPayloadForMessage:
          mergeStreamingChunkPayloadForMessage(get, set),
        updateQuickRepliesAndTitleForCurrentStreamingMessage:
          updateQuickRepliesAndTitleForCurrentStreamingMessage(get, set),
        completeStreamingMessage: completeStreamingMessage(get, set),
        cancelStreamingMessages: cancelStreamingMessages(get, set),
        startTimeoutForStreamingMessages: startTimeoutForStreamingMessages(
          get,
          set,
        ),
        completeProConPerspective: completeProConPerspective(get, set),
        generateVotingBehaviorSummary: () => {},
        addVotingBehaviorResult: addVotingBehaviorResult(get, set),
        addVotingBehaviorSummaryChunk: addVotingBehaviorSummaryChunk(get, set),
        completeVotingBehavior: completeVotingBehavior(get, set),
        setPartyIds: setPartyIds(get, set),
        setSelectedElectoralLists: (panelNumbers: number[]) =>
          set({ selectedElectoralLists: panelNumbers }),
        setElectoralListsData: (lists) => set({ electoralListsData: lists }),
        toggleElectoralList: (panelNumber: number) =>
          set((state) => {
            const idx = state.selectedElectoralLists.indexOf(panelNumber);
            if (idx >= 0) {
              state.selectedElectoralLists.splice(idx, 1);
            } else {
              state.selectedElectoralLists.push(panelNumber);
            }
          }),
        getLLMSize: () => get().tenant?.llm_size ?? DEFAULT_LLM_SIZE,
        resetStreamingMessage: resetStreamingMessage(get, set),
        setUserDemographic: setUserDemographic(get, set),
        loadUserDemographics: loadUserDemographics(get, set),
        addDebugLlmCall: (payload) =>
          set((state) => {
            state.debugLlmCalls.push(payload);
          }),
        clearDebugLlmCalls: () => set({ debugLlmCalls: [] }),
        setSecondRoundPartyIds: (ids) => set({ secondRoundPartyIds: ids }),
      })),
    ),
  );
}

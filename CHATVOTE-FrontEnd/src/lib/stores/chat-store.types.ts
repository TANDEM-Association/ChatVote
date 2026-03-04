import type ChatSocket from "@lib/chat-socket";
import { type ChatSession, type Tenant } from "@lib/firebase/firebase.types";
import { type PartyDetails } from "@lib/party-details";
import {
  type ChatScope,
  type LLMSize,
  type PartyResponseChunkReadyPayload,
  type StreamingMessage,
  type Vote,
} from "@lib/socket.types";
import { type Timestamp } from "firebase/firestore";
import { type WritableDraft } from "immer";

export type Source = {
  source: string;
  content_preview: string;
  page: number;
  url: string;
  source_document: string;
  document_publish_date: string;
  party_id?: string;
};

export type CurrentStreamingMessages = {
  id: string;
  messages: Record<string, StreamingMessage>;
  chat_title?: string;
  quick_replies?: string[];
  streaming_complete?: boolean;
  responding_party_ids?: string[];
};

export type MessageItem = {
  id: string;
  content: string;
  sources: Source[];
  party_id?: string;
  candidate_id?: string;
  role: "assistant" | "user";
  pro_con_perspective?: MessageItem;
  feedback?: MessageFeedback;
  created_at?: Timestamp;
  voting_behavior?: VotingBehavior;
};

export type CurrentStreamedVotingBehavior = {
  requestId: string;
  summary?: string;
  votes?: Vote[];
};

export type VotingBehavior = {
  summary: string;
  votes: Vote[];
};

export type GroupedMessage = {
  id: string;
  messages: MessageItem[];
  chat_title?: string;
  quick_replies?: string[];
  role: "user" | "assistant";
  created_at?: Timestamp;
};

export type MessageFeedback = {
  feedback: "like" | "dislike";
  detail?: string;
};

export type ChatStoreState = {
  userId?: string;
  isAnonymous?: boolean;
  chatId?: string;
  // We set this when we start the chat session, then also initialize the chat session on the server. When sending messages, the
  // preliminary chat id should be the same as the chat id.
  localPreliminaryChatId?: string;
  partyIds: Set<string>;
  preSelectedParties?: PartyDetails[];
  messages: GroupedMessage[];
  input: string;
  loading: {
    general: boolean;
    newMessage: boolean;
    proConPerspective: string | undefined;
    votingBehaviorSummary: string | undefined;
    chatSession: boolean;
    initializingChatSocketSession: boolean;
  };
  pendingStreamingMessageTimeoutHandler: {
    interval?: NodeJS.Timeout;
    timeout?: NodeJS.Timeout;
  };
  error?: string;
  pendingInitialQuestion?: string;
  initialQuestionError?: string;
  currentQuickReplies: string[];
  currentChatTitle?: string;
  chatSessionIsPublic?: boolean;
  socket: {
    io?: ChatSocket;
    connected?: boolean;
    error?: string;
    isConnecting?: boolean;
  };
  currentStreamingMessages?: CurrentStreamingMessages;
  currentStreamedVotingBehavior?: CurrentStreamedVotingBehavior;
  clickedProConButton?: boolean;
  clickedVotingBehaviorSummaryButton?: boolean;
  tenant?: Tenant;
  scope: ChatScope;
  municipalityCode?: string;
  locale: string;
};

export type ChatStoreActions = {
  setIsAnonymous: (isAnonymous: boolean) => void;
  setLocale: (locale: string) => void;
  setInput: (input: string) => void;
  addUserMessage: (
    userId: string,
    message: string,
    fromInitialQuestion?: boolean,
  ) => void;
  setChatId: (chatId: string) => void;
  newChat: () => void;
  loadChatSession: (chatId: string) => Promise<void>;
  hydrateChatSession: ({
    chatSession,
    messages,
    chatId,
    preSelectedPartyIds,
    initialQuestion,
    userId,
    tenant,
    municipalityCode,
    locale,
  }: {
    chatSession?: ChatSession;
    messages?: GroupedMessage[];
    chatId?: string;
    preSelectedPartyIds?: string[];
    initialQuestion?: string;
    userId: string;
    tenant?: Tenant;
    municipalityCode?: string;
    locale: string;
  }) => void;
  generateProConPerspective: (
    partyId: string,
    message: MessageItem | StreamingMessage,
  ) => Promise<void>;
  generateCandidateProConPerspective: (
    candidateId: string,
    message: MessageItem | StreamingMessage,
  ) => Promise<void>;
  completeCandidateProConPerspective: (
    requestId: string,
    candidateId: string,
    message: MessageItem,
  ) => void;
  setChatSessionIsPublic: (isPublic: boolean) => Promise<void>;
  setMessageFeedback: (messageId: string, feedback: MessageFeedback) => void;
  setPreSelectedParties: (parties: PartyDetails[]) => void;
  setSocket: (socket: ChatSocket) => void;
  setSocketConnecting: (isConnecting: boolean) => void;
  setSocketConnected: (connected: boolean) => void;
  setSocketError: (error: string) => void;
  initializeChatSession: () => Promise<void>;
  initializedChatSession: (sessionId: string) => void;
  selectRespondingParties: (sessionId: string, partyIds: string[]) => void;
  streamingMessageSourcesReady: (
    sessionId: string,
    partyId: string,
    sources: Source[],
  ) => void;
  mergeStreamingChunkPayloadForMessage: (
    sessionId: string,
    partyId: string,
    streamingMessage: PartyResponseChunkReadyPayload,
  ) => void;
  updateQuickRepliesAndTitleForCurrentStreamingMessage: (
    sessionId: string,
    quickReplies: string[],
    title: string,
  ) => void;
  completeStreamingMessage: (
    sessionId: string,
    partyId: string,
    completeMessage: string,
  ) => void;
  startTimeoutForStreamingMessages: (streamingMessageId: string) => void;
  cancelStreamingMessages: (streamingMessageId?: string) => void;
  completeProConPerspective: (requestId: string, message: MessageItem) => void;
  generateVotingBehaviorSummary: (
    partyId: string,
    message: MessageItem | StreamingMessage,
  ) => void;
  addVotingBehaviorResult: (
    requestId: string,
    vote: Vote,
    isEnd: boolean,
  ) => void;
  addVotingBehaviorSummaryChunk: (
    requestId: string,
    chunk: string,
    isEnd: boolean,
  ) => void;
  completeVotingBehavior: (
    requestId: string,
    votes: Vote[],
    message: string,
  ) => void;
  setPartyIds: (partyIds: string[]) => void;
  getLLMSize: () => LLMSize;
  resetStreamingMessage: (
    sessionId: string,
    partyId: string,
    reason: string,
  ) => void;
};

export type ChatStore = ChatStoreState & ChatStoreActions;

export type ChatStoreActionHandlerFor<T extends keyof ChatStoreActions> = (
  get: () => ChatStore,
  set: (
    nextStateOrUpdater:
      | ChatStore
      | Partial<ChatStore>
      | ((state: WritableDraft<ChatStore>) => void),
    shouldReplace?: false,
  ) => void,
) => (
  ...args: Parameters<ChatStoreActions[T]>
) => ReturnType<ChatStoreActions[T]>;

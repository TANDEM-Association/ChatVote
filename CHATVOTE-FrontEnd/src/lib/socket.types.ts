import {
  type MessageFeedback,
  type MessageItem,
  type Source,
  type VotingBehavior,
} from "./stores/chat-store.types";

// Re-export shared enums and domain types from generated backend types.
// These are the single source of truth — any backend change triggers tsc errors.
export type {
  LLMSize,
  ChatScope,
  Vote,
  Link,
  VotingResults,
  VotingResultsOverall,
  VotingResultsByParty,
} from "./generated";

// Re-export generated DTO types used directly by consumers
export type {
  PartyResponseChunkDto,
  QuickRepliesAndTitleDto,
  RespondingPartiesDto,
  ProConPerspectiveRequestDto,
  CandidateProConPerspectiveRequestDto,
  VotingBehaviorRequestDto,
  VotingBehaviorSummaryChunkDto,
} from "./generated";

import type {
  LLMSize,
  ChatScope,
  Vote,
  PartyResponseChunkDto,
  QuickRepliesAndTitleDto,
  RespondingPartiesDto,
  VotingBehaviorRequestDto,
  VotingBehaviorSummaryChunkDto,
} from "./generated";

// ============================================
// Payload type aliases
// ============================================
// Types that match generated DTOs exactly are aliased for backward compatibility.
// Types with frontend-specific differences are defined manually with comments
// indicating the backend source DTO.

// --- Exact matches (aliased from generated) ---

/** @see PartyResponseChunkDto */
export type PartyResponseChunkReadyPayload = PartyResponseChunkDto;

/** @see QuickRepliesAndTitleDto */
export type QuickRepliesAndTitleReadyPayload = QuickRepliesAndTitleDto;

/** @see RespondingPartiesDto */
export type RespondingPartiesSelectedPayload = RespondingPartiesDto;

/** @see VotingBehaviorRequestDto. Adds locale so backend error messages respect user language. */
export type GenerateVotingBehaviorSummaryPayload = VotingBehaviorRequestDto & {
  locale: string;
};

// --- Frontend-adapted types ---
// These intentionally differ from backend DTOs (drop status, use MessageItem,
// use typed Source[], add frontend fields). Comments reference the backend DTO
// so changes there surface during review.

/** Backend: SourcesDto. FE uses typed Source[] and non-nullable party_id. */
export type SourcesReadyPayload = {
  session_id: string;
  sources: Source[];
  party_id: string;
  rag_query: string;
};

/** Backend: PartyResponseCompleteDto. FE drops status field. */
export type PartyResponseCompletePayload = {
  session_id: string;
  party_id: string;
  complete_message: string;
};

/** Backend: ProConPerspectiveDto. FE uses MessageItem, drops status. */
export type ProConPerspectiveReadyPayload = {
  request_id: string;
  message: MessageItem;
};

/** Backend: ChatSessionInitializedDto. FE drops status, uses non-nullable session_id. */
export type ChatSessionInitializedPayload = {
  session_id: string;
};

/** Backend: InitChatSessionDto. FE uses MessageItem[] for chat_history, adds party_ids. */
export type ChatSessionInitPayload = {
  session_id: string;
  party_ids: string[];
  chat_history: MessageItem[];
  current_title: string;
  chat_response_llm_size: LLMSize;
  last_quick_replies: string[];
  scope: ChatScope;
  municipality_code?: string;
  locale: string;
};

/** Backend: ChatUserMessageDto. FE sends a subset of fields. */
export type AddUserMessagePayload = {
  session_id: string;
  user_message: string;
  party_ids: string[];
  user_is_logged_in: boolean;
};

/** Backend: ProConPerspectiveRequestDto (exact match). */
export type ProConPerspectiveRequestPayload = {
  request_id: string;
  party_id: string;
  last_assistant_message: string;
  last_user_message: string;
};

/** Backend: CandidateProConPerspectiveRequestDto (exact match). */
export type CandidateProConPerspectiveRequestPayload = {
  request_id: string;
  candidate_id: string;
  last_assistant_message: string;
  last_user_message: string;
};

/** Backend: CandidateProConPerspectiveDto. FE uses MessageItem, status as string. */
export type CandidateProConPerspectiveReadyPayload = {
  request_id: string;
  candidate_id: string;
  message: MessageItem;
  status: string;
};

/** Backend: VotingBehaviorSummaryChunkDto. FE drops chunk_index. */
export type VotingBehaviorSummaryChunkPayload = Omit<
  VotingBehaviorSummaryChunkDto,
  "chunk_index"
>;

/** Backend: VotingBehaviorVoteDto. FE adds is_end (sent by backend but not in DTO). */
export type VotingBehaviorResultPayload = {
  request_id: string;
  vote: Vote;
  is_end: boolean;
};

/** Backend: VotingBehaviorDto. FE drops status and rag_query. */
export type VotingBehaviorCompletePayload = {
  request_id: string;
  votes: Vote[];
  message: string;
};

/** Backend: StreamResetDto. FE uses non-nullable party_id. */
export type StreamResetPayload = {
  session_id: string;
  party_id: string;
  reason: string;
};

// ============================================
// Frontend-only types (no backend equivalent)
// ============================================

export type CurrentStreamingMessages = {
  id: string;
  messages: Record<string, StreamingMessage>;
  chat_title?: string;
  quick_replies?: string[];
  streaming_complete?: boolean;
};

export type StreamingMessage = {
  id: string;
  role: "assistant";
  content?: string;
  sources?: Source[];
  party_id?: string;
  chunking_complete?: boolean;
  pro_con_perspective?: MessageItem;
  voting_behavior?: VotingBehavior;
  feedback?: MessageFeedback;
};

"use client";

import { useEffect, useRef } from "react";

import { type Locale } from "@i18n/config";
import ChatSocket from "@lib/chat-socket";
import {
  type CandidateProConPerspectiveReadyPayload,
  type ChatResponseCompletePayload,
  type ChatSessionInitializedPayload,
  type DebugLlmCallPayload,
  type PartyResponseChunkReadyPayload,
  type PartyResponseCompletePayload,
  type ProConPerspectiveReadyPayload,
  type QuickRepliesAndTitleReadyPayload,
  type RespondingPartiesSelectedPayload,
  type SourcesReadyPayload,
  type StreamResetPayload,
  type VotingBehaviorCompletePayload,
  type VotingBehaviorResultPayload,
  type VotingBehaviorSummaryChunkPayload,
} from "@lib/socket.types";
import { io, type Socket } from "socket.io-client";

import { useAppContext } from "./app-provider";
import { useChatStore } from "./chat-store-provider";

type Props = {
  children: React.ReactNode;
};

const baseUrl = process.env.NEXT_PUBLIC_API_URL;

function createSocket(locale: Locale): Socket {
  return io(baseUrl, {
    transports: ["websocket"],
    extraHeaders: {
      "Accept-Language": locale,
    },
    auth: {
      locale,
    },
  });
}

// Default socket for initial render (will be replaced with locale-aware socket)
export let socket = createSocket("fr");

function updateSocket(locale: Locale): Socket {
  // Always disconnect — handles both "connected" and "still connecting" states.
  // Without this, a socket that auto-connected but hasn't completed its TCP
  // handshake yet will not be disconnected (socket.connected is false while
  // connecting), causing two sockets to be simultaneously alive.
  socket.disconnect();
  socket = createSocket(locale);
  socket.connect();
  return socket;
}

const chatSocket = new ChatSocket();

function SocketProvider({ children }: Props) {
  const { locale } = useAppContext();
  const previousLocaleRef = useRef<Locale>(locale);
  const setSocketConnected = useChatStore((state) => state.setSocketConnected);
  const setSocket = useChatStore((state) => state.setSocket);
  const setStoreLocale = useChatStore((state) => state.setLocale);
  const selectRespondingParties = useChatStore(
    (state) => state.selectRespondingParties,
  );
  const mergeStreamingChunkPayloadForMessage = useChatStore(
    (state) => state.mergeStreamingChunkPayloadForMessage,
  );
  const updateQuickRepliesAndTitleForCurrentStreamingMessage = useChatStore(
    (state) => state.updateQuickRepliesAndTitleForCurrentStreamingMessage,
  );
  const completeStreamingMessage = useChatStore(
    (state) => state.completeStreamingMessage,
  );
  const streamingMessageSourcesReady = useChatStore(
    (state) => state.streamingMessageSourcesReady,
  );
  const completeProConPerspective = useChatStore(
    (state) => state.completeProConPerspective,
  );
  const completeCandidateProConPerspective = useChatStore(
    (state) => state.completeCandidateProConPerspective,
  );
  const initializedChatSession = useChatStore(
    (state) => state.initializedChatSession,
  );
  const addVotingBehaviorSummaryChunk = useChatStore(
    (state) => state.addVotingBehaviorSummaryChunk,
  );
  const addVotingBehaviorResult = useChatStore(
    (state) => state.addVotingBehaviorResult,
  );
  const completeVotingBehavior = useChatStore(
    (state) => state.completeVotingBehavior,
  );
  const resetStreamingMessage = useChatStore(
    (state) => state.resetStreamingMessage,
  );
  const cancelStreamingMessages = useChatStore(
    (state) => state.cancelStreamingMessages,
  );
  const addDebugLlmCall = useChatStore((state) => state.addDebugLlmCall);

  // Update socket and store locale when locale changes
  useEffect(() => {
    if (previousLocaleRef.current !== locale) {
      setStoreLocale(locale);
      updateSocket(locale);
      previousLocaleRef.current = locale;
    }
  }, [locale, setStoreLocale]);

  useEffect(() => {
    setSocket(chatSocket);

    if (chatSocket.connected) {
      onConnect();
    }

    function onConnect() {
      setSocketConnected(true);
    }

    function onDisconnect() {
      setSocketConnected(false);
    }

    function onRespondingPartiesSelected(
      data: RespondingPartiesSelectedPayload,
    ) {
      selectRespondingParties(data.session_id, data.party_ids);
    }

    function onSourcesReady(data: SourcesReadyPayload) {
      streamingMessageSourcesReady(
        data.session_id,
        data.party_id,
        data.sources,
      );
    }

    function onPartyResponseChunkReady(data: PartyResponseChunkReadyPayload) {
      mergeStreamingChunkPayloadForMessage(
        data.session_id,
        data.party_id ?? "",
        data,
      );
    }

    function onPartyResponseComplete(data: PartyResponseCompletePayload) {
      completeStreamingMessage(
        data.session_id,
        data.party_id,
        data.complete_message,
      );
    }

    function onQuickRepliesAndTitleReady(
      data: QuickRepliesAndTitleReadyPayload,
    ) {
      updateQuickRepliesAndTitleForCurrentStreamingMessage(
        data.session_id,
        data.quick_replies,
        data.title,
      );
    }

    function onProConPerspectiveReady(data: ProConPerspectiveReadyPayload) {
      completeProConPerspective(data.request_id, data.message);
    }

    function onCandidateProConPerspectiveReady(
      data: CandidateProConPerspectiveReadyPayload,
    ) {
      completeCandidateProConPerspective(
        data.request_id,
        data.candidate_id,
        data.message,
      );
    }

    function onChatSessionInitialized(data: ChatSessionInitializedPayload) {
      initializedChatSession(data.session_id);
    }

    function onVotingBehaviorSummaryChunk(
      data: VotingBehaviorSummaryChunkPayload,
    ) {
      addVotingBehaviorSummaryChunk(
        data.request_id,
        data.summary_chunk,
        data.is_end,
      );
    }

    function onVotingBehaviorResult(data: VotingBehaviorResultPayload) {
      addVotingBehaviorResult(data.request_id, data.vote, data.is_end);
    }

    function onVotingBehaviorComplete(data: VotingBehaviorCompletePayload) {
      completeVotingBehavior(data.request_id, data.votes, data.message);
    }

    function onStreamReset(data: StreamResetPayload) {
      resetStreamingMessage(data.session_id, data.party_id, data.reason);
    }

    function onChatResponseComplete(data: ChatResponseCompletePayload) {
      if (data.status.indicator === "error") {
        cancelStreamingMessages();
      }
    }

    function onDebugLlmCall(data: DebugLlmCallPayload) {
      addDebugLlmCall(data);
    }

    chatSocket.on("connect", onConnect);
    chatSocket.on("disconnect", onDisconnect);
    chatSocket.on("responding_parties_selected", onRespondingPartiesSelected);
    chatSocket.on("chat_session_initialized", onChatSessionInitialized);
    chatSocket.on("sources_ready", onSourcesReady);
    chatSocket.on("party_response_chunk_ready", onPartyResponseChunkReady);
    chatSocket.on("party_response_complete", onPartyResponseComplete);
    chatSocket.on("quick_replies_and_title_ready", onQuickRepliesAndTitleReady);
    chatSocket.on("pro_con_perspective_complete", onProConPerspectiveReady);
    chatSocket.on(
      "candidate_pro_con_perspective_complete",
      onCandidateProConPerspectiveReady,
    );
    chatSocket.on(
      "voting_behavior_summary_chunk",
      onVotingBehaviorSummaryChunk,
    );
    chatSocket.on("voting_behavior_result", onVotingBehaviorResult);
    chatSocket.on("voting_behavior_complete", onVotingBehaviorComplete);
    chatSocket.on("stream_reset", onStreamReset);
    chatSocket.on("chat_response_complete", onChatResponseComplete);
    chatSocket.on("debug_llm_call", onDebugLlmCall);

    return () => {
      chatSocket.off("connect", onConnect);
      chatSocket.off("disconnect", onDisconnect);
      chatSocket.off(
        "responding_parties_selected",
        onRespondingPartiesSelected,
      );
      chatSocket.off("chat_session_initialized", onChatSessionInitialized);
      chatSocket.off("sources_ready", onSourcesReady);
      chatSocket.off("party_response_chunk_ready", onPartyResponseChunkReady);
      chatSocket.off("party_response_complete", onPartyResponseComplete);
      chatSocket.off(
        "quick_replies_and_title_ready",
        onQuickRepliesAndTitleReady,
      );
      chatSocket.off("pro_con_perspective_complete", onProConPerspectiveReady);
      chatSocket.off(
        "candidate_pro_con_perspective_complete",
        onCandidateProConPerspectiveReady,
      );
      chatSocket.off(
        "voting_behavior_summary_chunk",
        onVotingBehaviorSummaryChunk,
      );
      chatSocket.off("voting_behavior_result", onVotingBehaviorResult);
      chatSocket.off("voting_behavior_complete", onVotingBehaviorComplete);
      chatSocket.off("stream_reset", onStreamReset);
      chatSocket.off("chat_response_complete", onChatResponseComplete);
      chatSocket.off("debug_llm_call", onDebugLlmCall);
    };
  }, [
    locale,
    selectRespondingParties,
    mergeStreamingChunkPayloadForMessage,
    setSocket,
    setSocketConnected,
    updateQuickRepliesAndTitleForCurrentStreamingMessage,
    completeStreamingMessage,
    streamingMessageSourcesReady,
    completeProConPerspective,
    completeCandidateProConPerspective,
    initializedChatSession,
    addVotingBehaviorSummaryChunk,
    addVotingBehaviorResult,
    completeVotingBehavior,
    resetStreamingMessage,
    cancelStreamingMessages,
    addDebugLlmCall,
  ]);

  return children;
}

export default SocketProvider;

"use client";

import { useEffect, useState } from "react";

import { useAnonymousAuth } from "@components/anonymous-auth";
import { listenToSystemStatus } from "@lib/firebase/firebase";
import { type LlmSystemStatus } from "@lib/firebase/firebase.types";

import ChatInput from "./chat-input";
import ChatInputRateLimit from "./chat-input-rate-limit";

type Props = {
  initialSystemStatus: LlmSystemStatus;
  hasValidServerUser?: boolean;
  municipalityCode?: string;
  sessionId?: string;
};

function ChatDynamicChatInput({
  initialSystemStatus,
  hasValidServerUser,
  municipalityCode,
  sessionId,
}: Props) {
  const { session } = useAnonymousAuth();
  const [isAtRateLimit, setIsAtRateLimit] = useState(
    initialSystemStatus.is_at_rate_limit,
  );

  useEffect(() => {
    const unsubscribe = listenToSystemStatus((status) => {
      setIsAtRateLimit(status.is_at_rate_limit);
    });

    return unsubscribe;
  }, []);

  const isPriorityUser = session ? !session.isAnonymous : false;
  const canAccessChatInput =
    isPriorityUser || !isAtRateLimit || hasValidServerUser;

  if (!canAccessChatInput) {
    return <ChatInputRateLimit />;
  }

  return <ChatInput disabled={!municipalityCode && !sessionId} />;
}

export default ChatDynamicChatInput;

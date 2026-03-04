"use client";

import { useEffect } from "react";

import { useAnonymousAuth } from "@components/anonymous-auth";
import { useChatStore } from "@components/providers/chat-store-provider";

function AnonymousUserChatStoreUpdater() {
  const { session } = useAnonymousAuth();
  const setIsAnonymous = useChatStore((state) => state.setIsAnonymous);

  useEffect(() => {
    if (session) {
      setIsAnonymous(session.isAnonymous);
    }
  }, [session, setIsAnonymous]);

  return null;
}

export default AnonymousUserChatStoreUpdater;

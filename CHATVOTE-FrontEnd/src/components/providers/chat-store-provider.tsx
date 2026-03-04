"use client";

import { createContext, type ReactNode, useContext, useRef } from "react";

import { useChatParam } from "@lib/hooks/use-chat-param";
import { createChatStore } from "@lib/stores/chat-store";
import { type ChatStore } from "@lib/stores/chat-store.types";
import { useStore } from "zustand";

export type ChatStoreApi = ReturnType<typeof createChatStore>;

export const ChatStoreContext = createContext<ChatStoreApi | undefined>(
  undefined,
);

type Props = {
  children: ReactNode;
};

export const ChatStoreProvider = ({ children }: Props) => {
  const chatId = useChatParam();

  const storeRef = useRef<ChatStoreApi>(null);
  if (!storeRef.current) {
    storeRef.current = createChatStore({
      chatId,
    });
  }

  return (
    <ChatStoreContext.Provider value={storeRef.current}>
      {children}
    </ChatStoreContext.Provider>
  );
};

export const useChatStore = <T,>(selector: (store: ChatStore) => T): T => {
  const chatStoreContext = useContext(ChatStoreContext);

  if (!chatStoreContext) {
    throw new Error(`useChatStore must be used within ChatStoreProvider`);
  }

  return useStore(chatStoreContext, selector);
};

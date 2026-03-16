import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export type ChatMode = 'classic' | 'ai-sdk';

type ChatModeStore = {
  chatMode: ChatMode;
  setChatMode: (mode: ChatMode) => void;
};

export const useChatModeStore = create<ChatModeStore>()(
  persist(
    (set) => ({
      chatMode: 'classic',
      setChatMode: (mode) => set({ chatMode: mode }),
    }),
    {
      name: 'chat-mode',
    },
  ),
);
